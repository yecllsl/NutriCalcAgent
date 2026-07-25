# src/nutricalc_mcp/food_db.py
"""中国食物成分表本地数据库 — 加载、查询、份量换算

数据来源：
- 主数据：data/food_db/*.json（来自开源项目 Sanotsu/china-food-composition-data，
  基于《中国食物成分表》第 6 版，1677+ 条，公益教育用途）
- 兜底数据：本文件内置 SEED_FOODS 种子集（~40 条高频中餐食物），
  确保即使外部数据未就绪也能运行。

设计要点（对齐 DeepReview storage/ocr 的懒加载单例模式）：
- FoodDatabase 单例懒加载，首次查询时扫描 data/food_db/ 加载所有 JSON
- 字段映射表兼容中文列名（中国食物成分表原始字段）与 NutritionFacts 字段名
- 支持精确匹配、模糊匹配（子串/包含）、按类别查询、按 ID 查询
- 营养素按"每 100g 可食部"存储，查询时按 amount_g 缩放
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from nutricalc_mcp.models import NutritionFacts
from nutricalc_mcp.knowledge_map import FOOD_CATEGORIES


# ──────────────────────────────────────────
# 字段映射：中国食物成分表中文列名 → NutritionFacts 字段名
# 同时兼容英文键名，提升对外部数据格式的鲁棒性
# ──────────────────────────────────────────

FIELD_ALIASES: dict[str, str] = {
    # 能量
    "能量": "calories_kcal", "energy": "calories_kcal", "energy_kcal": "calories_kcal",
    "热量": "calories_kcal", "energyKCal": "calories_kcal",
    # 宏量
    "蛋白质": "protein_g", "protein": "protein_g", "protein_g": "protein_g",
    "脂肪": "fat_g", "fat": "fat_g", "fat_g": "fat_g", "脂类": "fat_g",
    "碳水化合物": "carbohydrate_g", "carbohydrate": "carbohydrate_g",
    "carb": "carbohydrate_g", "碳水": "carbohydrate_g", "CHO": "carbohydrate_g",
    "膳食纤维": "fiber_g", "fiber": "fiber_g", "fiber_g": "fiber_g", "膳食纤维(g)": "fiber_g",
    "dietaryFiber": "fiber_g",
    # 维生素
    "维生素A": "vitamin_a_ug", "vitamin_a": "vitamin_a_ug",
    "视黄醇当量": "vitamin_a_ug", "维生素A(μgRE)": "vitamin_a_ug",
    "vitaminA": "vitamin_a_ug",
    "维生素C": "vitamin_c_mg", "vitamin_c": "vitamin_c_mg", "抗坏血酸": "vitamin_c_mg",
    "vitaminC": "vitamin_c_mg",
    "维生素E": "vitamin_e_mg", "vitamin_e": "vitamin_e_mg",
    "vitaminETotal": "vitamin_e_mg",
    "硫胺素": "thiamin_mg", "维生素 B1": "thiamin_mg", "维生素b1": "thiamin_mg",
    "thiamin": "thiamin_mg", "vb1": "thiamin_mg",
    "核黄素": "riboflavin_mg", "维生素 B2": "riboflavin_mg", "维生素b2": "riboflavin_mg",
    "riboflavin": "riboflavin_mg", "vb2": "riboflavin_mg",
    "烟酸": "niacin_mg", "niacin": "niacin_mg", "维生素 PP": "niacin_mg", "维生素pp": "niacin_mg",
    # 矿物质
    "钙": "calcium_mg", "calcium": "calcium_mg", "ca": "calcium_mg",
    "Ca": "calcium_mg",
    "铁": "iron_mg", "iron": "iron_mg", "fe": "iron_mg",
    "Fe": "iron_mg",
    "锌": "zinc_mg", "zinc": "zinc_mg", "zn": "zinc_mg",
    "Zn": "zinc_mg",
    "硒": "selenium_ug", "selenium": "selenium_ug", "se": "selenium_ug",
    "Se": "selenium_ug",
    "钠": "sodium_mg", "sodium": "sodium_mg", "na": "sodium_mg",
    "Na": "sodium_mg",
    "钾": "potassium_mg", "potassium": "potassium_mg", "k": "potassium_mg",
    "K": "potassium_mg",
    # 其他
    "胆固醇": "cholesterol_mg", "cholesterol": "cholesterol_mg",
    # 血糖生成指数
    "GI": "gi", "gi": "gi", "血糖生成指数": "gi",
}

# 名称字段别名
NAME_ALIASES = ["食物名称", "name", "名称", "food_name", "食物", "foodName"]
# 类别字段别名
CATEGORY_ALIASES = ["食物类别", "category", "类别", "food_category", "分类"]
# ID 字段别名
ID_ALIASES = ["食物ID", "id", "food_id", "编号", "code", "食物编码", "foodCode"]
# 可食部字段别名（百分比）
EDIBLE_ALIASES = ["可食部", "edible", "edible_part", "可食部分"]


def _to_float(v) -> float:
    """安全转 float：处理 '—'/'-'/'Tr'/'NaN'/None 等缺失值标记"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in ("", "—", "-", "Tr", "tr", "ND", "NaN", "nan", "null", "None", "未检出"):
        # "Tr"（微量）按 0 处理
        return 0.0
    # 去除单位字符（mg/μg/g 等）
    for unit in ("μg", "ug", "mg", "g", "kcal", "kJ", "%"):
        s = s.replace(unit, "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _pick_field(record: dict, aliases: list[str], default=None):
    """从记录中按别名优先级取字段值（兼容多种命名）"""
    for alias in aliases:
        if alias in record:
            return record[alias]
    # 大小写不敏感兜底
    lower_map = {k.lower(): k for k in record.keys()}
    for alias in aliases:
        if alias.lower() in lower_map:
            return record[lower_map[alias.lower()]]
    return default


def _map_to_nutrition(record: dict) -> NutritionFacts:
    """将原始食物记录映射为 NutritionFacts（按每 100g 可食部）"""
    data = {}
    for raw_key, raw_val in record.items():
        # 归一化 key：去空格、去单位括号
        clean_key = raw_key.strip()
        # 去除尾部括号单位如 "蛋白质(g)"
        if "(" in clean_key:
            clean_key = clean_key.split("(")[0].strip()
        field = FIELD_ALIASES.get(clean_key) or FIELD_ALIASES.get(raw_key)
        if field and field not in data:
            data[field] = _to_float(raw_val)
    return NutritionFacts(**data)


def _guess_category(name: str, record: dict) -> str:
    """推断食物类别：优先取记录中的类别字段，否则按名称关键词猜测"""
    cat = _pick_field(record, CATEGORY_ALIASES)
    if cat and cat in FOOD_CATEGORIES:
        return cat
    if cat:
        # 尝试模糊匹配到标准类别
        for std_cat in FOOD_CATEGORIES:
            if std_cat in str(cat) or str(cat) in std_cat:
                return std_cat
    # 关键词猜测
    name_lower = name.lower()
    rules = [
        (["米", "面", "粉", "麦", "谷", "薯", "馒头", "饼", "粥", "饭", "面包"], "谷薯类"),
        (["菜", "蔬", "白菜", "菠菜", "番茄", "黄瓜", "萝卜", "豆角", "茄子", "椒"], "蔬菜类"),
        (["果", "苹果", "香蕉", "橙", "橘", "葡萄", "西瓜", "梨", "桃", "莓"], "水果类"),
        (["猪", "牛", "羊", "鸡", "鸭", "鹅", "蛋", "肉", "排骨"], "肉禽蛋类"),
        (["鱼", "虾", "蟹", "海带", "紫菜", "贝", "海参"], "水产类"),
        (["奶", "乳", "酪", "豆", "腐", "浆"], "奶豆类"),
        (["花生", "瓜子", "核桃", "杏仁", "腰果", "栗子", "坚果"], "坚果类"),
        (["油", "脂", "黄油", "猪油", "菜籽油"], "油脂类"),
        (["盐", "糖", "醋", "酱油", "酱", "味精", "调料"], "调味品"),
        (["水", "茶", "咖啡", "果汁", "可乐", "饮料", "酒"], "饮料类"),
    ]
    for keywords, cat_name in rules:
        if any(kw in name for kw in keywords) or any(kw in name_lower for kw in keywords):
            return cat_name
    return "其他"


# ──────────────────────────────────────────
# 种子数据（兜底，~40 条高频中餐食物，每 100g 可食部）
# 数据参考《中国食物成分表》第 6 版，公益教育用途
# ──────────────────────────────────────────

SEED_FOODS: list[dict] = [
    {"id": "seed_001", "name": "米饭(蒸)", "category": "谷薯类", "calories_kcal": 116, "protein_g": 2.6, "fat_g": 0.3, "carbohydrate_g": 25.9, "fiber_g": 0.4, "sodium_mg": 2, "potassium_mg": 30, "calcium_mg": 7, "iron_mg": 0.2, "zinc_mg": 0.5, "gi": 83},
    {"id": "seed_002", "name": "馒头", "category": "谷薯类", "calories_kcal": 223, "protein_g": 7.0, "fat_g": 1.1, "carbohydrate_g": 47.0, "fiber_g": 1.3, "sodium_mg": 165, "potassium_mg": 95, "calcium_mg": 38, "iron_mg": 1.8, "zinc_mg": 0.7, "gi": 88},
    {"id": "seed_003", "name": "面条(煮)", "category": "谷薯类", "calories_kcal": 110, "protein_g": 3.5, "fat_g": 0.1, "carbohydrate_g": 24.3, "fiber_g": 0.4, "sodium_mg": 80, "potassium_mg": 15, "calcium_mg": 4, "iron_mg": 0.5, "gi": 82},
    {"id": "seed_004", "name": "燕麦片", "category": "谷薯类", "calories_kcal": 367, "protein_g": 15.0, "fat_g": 6.7, "carbohydrate_g": 61.6, "fiber_g": 5.3, "calcium_mg": 186, "iron_mg": 7.0, "zinc_mg": 2.6, "gi": 55},
    {"id": "seed_005", "name": "红薯", "category": "谷薯类", "calories_kcal": 99, "protein_g": 1.1, "fat_g": 0.2, "carbohydrate_g": 24.7, "fiber_g": 1.6, "potassium_mg": 130, "vitamin_c_mg": 26, "gi": 54},
    {"id": "seed_006", "name": "番茄", "category": "蔬菜类", "calories_kcal": 20, "protein_g": 0.9, "fat_g": 0.2, "carbohydrate_g": 4.0, "fiber_g": 0.5, "vitamin_c_mg": 19, "vitamin_a_ug": 92, "potassium_mg": 237, "gi": 15},
    {"id": "seed_007", "name": "白菜", "category": "蔬菜类", "calories_kcal": 17, "protein_g": 1.5, "fat_g": 0.1, "carbohydrate_g": 3.2, "fiber_g": 0.8, "vitamin_c_mg": 31, "calcium_mg": 50, "potassium_mg": 130, "sodium_mg": 57},
    {"id": "seed_008", "name": "黄瓜", "category": "蔬菜类", "calories_kcal": 16, "protein_g": 0.8, "fat_g": 0.2, "carbohydrate_g": 2.9, "fiber_g": 0.5, "vitamin_c_mg": 9, "potassium_mg": 102, "gi": 15},
    {"id": "seed_009", "name": "菠菜", "category": "蔬菜类", "calories_kcal": 28, "protein_g": 2.6, "fat_g": 0.3, "carbohydrate_g": 4.5, "fiber_g": 1.7, "vitamin_c_mg": 32, "vitamin_a_ug": 487, "calcium_mg": 66, "iron_mg": 2.9, "potassium_mg": 311},
    {"id": "seed_010", "name": "胡萝卜", "category": "蔬菜类", "calories_kcal": 41, "protein_g": 1.0, "fat_g": 0.2, "carbohydrate_g": 9.6, "fiber_g": 1.1, "vitamin_a_ug": 688, "potassium_mg": 320, "gi": 47},
    {"id": "seed_011", "name": "西兰花", "category": "蔬菜类", "calories_kcal": 36, "protein_g": 4.1, "fat_g": 0.6, "carbohydrate_g": 4.3, "fiber_g": 1.6, "vitamin_c_mg": 51, "vitamin_a_ug": 120, "calcium_mg": 67, "potassium_mg": 17},
    {"id": "seed_012", "name": "苹果", "category": "水果类", "calories_kcal": 54, "protein_g": 0.2, "fat_g": 0.2, "carbohydrate_g": 13.5, "fiber_g": 1.2, "vitamin_c_mg": 4, "potassium_mg": 119, "gi": 36},
    {"id": "seed_013", "name": "香蕉", "category": "水果类", "calories_kcal": 93, "protein_g": 1.4, "fat_g": 0.2, "carbohydrate_g": 22.0, "fiber_g": 1.2, "potassium_mg": 256, "vitamin_c_mg": 8, "gi": 52},
    {"id": "seed_014", "name": "橙", "category": "水果类", "calories_kcal": 48, "protein_g": 0.8, "fat_g": 0.2, "carbohydrate_g": 11.1, "fiber_g": 0.6, "vitamin_c_mg": 33, "potassium_mg": 159, "gi": 43},
    {"id": "seed_015", "name": "鸡蛋", "category": "肉禽蛋类", "calories_kcal": 144, "protein_g": 13.3, "fat_g": 8.8, "carbohydrate_g": 2.8, "cholesterol_mg": 585, "vitamin_a_ug": 234, "calcium_mg": 56, "iron_mg": 2.0, "selenium_ug": 14, "gi": 30},
    {"id": "seed_016", "name": "猪肉(瘦)", "category": "肉禽蛋类", "calories_kcal": 143, "protein_g": 20.3, "fat_g": 6.2, "carbohydrate_g": 1.5, "cholesterol_mg": 81, "iron_mg": 3.0, "zinc_mg": 2.9, "selenium_ug": 9.5, "potassium_mg": 305},
    {"id": "seed_017", "name": "猪排骨", "category": "肉禽蛋类", "calories_kcal": 278, "protein_g": 18.3, "fat_g": 23.0, "carbohydrate_g": 1.7, "cholesterol_mg": 105, "iron_mg": 1.4, "zinc_mg": 3.6},
    {"id": "seed_018", "name": "牛肉(瘦)", "category": "肉禽蛋类", "calories_kcal": 106, "protein_g": 20.2, "fat_g": 2.3, "carbohydrate_g": 1.2, "cholesterol_mg": 58, "iron_mg": 2.8, "zinc_mg": 3.7, "selenium_ug": 6.4, "potassium_mg": 284},
    {"id": "seed_019", "name": "鸡胸肉", "category": "肉禽蛋类", "calories_kcal": 133, "protein_g": 19.4, "fat_g": 5.0, "carbohydrate_g": 2.5, "cholesterol_mg": 82, "iron_mg": 1.0, "zinc_mg": 1.1, "potassium_mg": 338},
    {"id": "seed_020", "name": "牛奶", "category": "奶豆类", "calories_kcal": 54, "protein_g": 3.0, "fat_g": 3.2, "carbohydrate_g": 3.4, "calcium_mg": 104, "potassium_mg": 109, "vitamin_a_ug": 24, "cholesterol_mg": 15, "gi": 27},
    {"id": "seed_021", "name": "酸奶", "category": "奶豆类", "calories_kcal": 72, "protein_g": 2.5, "fat_g": 2.7, "carbohydrate_g": 9.3, "calcium_mg": 118, "potassium_mg": 150, "gi": 36},
    {"id": "seed_022", "name": "豆腐", "category": "奶豆类", "calories_kcal": 81, "protein_g": 8.1, "fat_g": 3.7, "carbohydrate_g": 4.2, "calcium_mg": 164, "iron_mg": 1.9, "potassium_mg": 125, "gi": 15},
    {"id": "seed_023", "name": "豆浆", "category": "奶豆类", "calories_kcal": 31, "protein_g": 3.0, "fat_g": 1.6, "carbohydrate_g": 1.2, "calcium_mg": 10, "potassium_mg": 48, "gi": 15},
    {"id": "seed_024", "name": "黄豆", "category": "奶豆类", "calories_kcal": 390, "protein_g": 35.0, "fat_g": 16.0, "carbohydrate_g": 34.2, "fiber_g": 15.5, "calcium_mg": 191, "iron_mg": 8.2, "zinc_mg": 3.3, "gi": 18},
    {"id": "seed_025", "name": "草鱼", "category": "水产类", "calories_kcal": 113, "protein_g": 16.6, "fat_g": 5.2, "cholesterol_mg": 86, "selenium_ug": 6.7, "potassium_mg": 312, "gi": 0},
    {"id": "seed_026", "name": "虾", "category": "水产类", "calories_kcal": 87, "protein_g": 16.4, "fat_g": 2.4, "cholesterol_mg": 117, "calcium_mg": 146, "selenium_ug": 29, "zinc_mg": 1.4, "potassium_mg": 215},
    {"id": "seed_027", "name": "带鱼", "category": "水产类", "calories_kcal": 127, "protein_g": 17.7, "fat_g": 4.9, "cholesterol_mg": 76, "selenium_ug": 36, "potassium_mg": 280},
    {"id": "seed_028", "name": "花生", "category": "坚果类", "calories_kcal": 567, "protein_g": 25.8, "fat_g": 49.2, "carbohydrate_g": 16.1, "fiber_g": 8.5, "vitamin_e_mg": 12.9, "zinc_mg": 3.3, "potassium_mg": 705},
    {"id": "seed_029", "name": "核桃", "category": "坚果类", "calories_kcal": 654, "protein_g": 15.2, "fat_g": 65.2, "carbohydrate_g": 13.7, "fiber_g": 6.7, "vitamin_e_mg": 9.8, "zinc_mg": 2.2, "calcium_mg": 98},
    {"id": "seed_030", "name": "花生油", "category": "油脂类", "calories_kcal": 899, "protein_g": 0, "fat_g": 99.9, "carbohydrate_g": 0, "vitamin_e_mg": 51.6},
    {"id": "seed_031", "name": "酱油", "category": "调味品", "calories_kcal": 63, "protein_g": 5.6, "fat_g": 0.1, "carbohydrate_g": 10.1, "sodium_mg": 5757, "potassium_mg": 110},
    {"id": "seed_032", "name": "食盐", "category": "调味品", "calories_kcal": 0, "sodium_mg": 39300},
    {"id": "seed_033", "name": "麻婆豆腐", "category": "混合菜", "calories_kcal": 130, "protein_g": 9.0, "fat_g": 7.5, "carbohydrate_g": 5.5, "sodium_mg": 580, "calcium_mg": 145, "fiber_g": 1.2, "gi": 30},
    {"id": "seed_034", "name": "番茄炒蛋", "category": "混合菜", "calories_kcal": 110, "protein_g": 7.5, "fat_g": 7.0, "carbohydrate_g": 4.5, "vitamin_c_mg": 12, "vitamin_a_ug": 130, "sodium_mg": 420, "gi": 30},
    {"id": "seed_035", "name": "红烧肉", "category": "混合菜", "calories_kcal": 350, "protein_g": 14.0, "fat_g": 32.0, "carbohydrate_g": 4.5, "cholesterol_mg": 95, "sodium_mg": 650, "gi": 35},
    {"id": "seed_036", "name": "清炒时蔬", "category": "混合菜", "calories_kcal": 60, "protein_g": 2.0, "fat_g": 4.0, "carbohydrate_g": 4.5, "fiber_g": 1.8, "vitamin_c_mg": 25, "sodium_mg": 380, "gi": 15},
    {"id": "seed_037", "name": "米饭(炒)", "category": "混合菜", "calories_kcal": 174, "protein_g": 4.0, "fat_g": 5.0, "carbohydrate_g": 28.0, "sodium_mg": 520, "gi": 75},
    {"id": "seed_038", "name": "绿茶", "category": "饮料类", "calories_kcal": 1, "protein_g": 0.2, "fat_g": 0, "carbohydrate_g": 0.1, "potassium_mg": 8},
    {"id": "seed_039", "name": "玉米", "category": "谷薯类", "calories_kcal": 112, "protein_g": 4.0, "fat_g": 1.2, "carbohydrate_g": 22.8, "fiber_g": 2.9, "vitamin_c_mg": 16, "potassium_mg": 238, "gi": 55},
    {"id": "seed_040", "name": "南瓜", "category": "蔬菜类", "calories_kcal": 23, "protein_g": 0.7, "fat_g": 0.1, "carbohydrate_g": 5.3, "fiber_g": 0.8, "vitamin_a_ug": 148, "potassium_mg": 287, "gi": 65},
]


# ──────────────────────────────────────────
# FoodDatabase 单例
# ──────────────────────────────────────────

# 默认数据目录：项目根 data/food_db
_DEFAULT_FOOD_DB_DIR = Path(__file__).parent.parent.parent.parent / "data" / "food_db"


class FoodDatabase:
    """中国食物成分表本地数据库

    懒加载：首次查询时扫描 data/food_db/*.json 加载所有外部数据，
    并合并内置 SEED_FOODS 种子数据作为兜底。
    每条记录归一化为:
        {id, name, category, nutrition: NutritionFacts(每100g)}
    """

    def __init__(self, db_dir: Optional[Path] = None):
        self.db_dir = db_dir or _DEFAULT_FOOD_DB_DIR
        self._records: list[dict] = []
        self._loaded = False
        self._source_stats: dict = {}

    def _load(self):
        """加载所有食物数据（外部 JSON + 内置种子）"""
        if self._loaded:
            return
        records: list[dict] = []
        external_count = 0
        files_used: list[str] = []

        # 加载外部 JSON 数据
        if self.db_dir.exists():
            for fp in sorted(self.db_dir.glob("*.json")):
                try:
                    raw = json.loads(fp.read_text(encoding="utf-8"))
                    items = raw if isinstance(raw, list) else raw.get("data", raw.get("foods", []))
                    if not isinstance(items, list):
                        continue
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        name = _pick_field(item, NAME_ALIASES, "")
                        if not name:
                            continue
                        food_id = _pick_field(item, ID_ALIASES, "") or f"ext_{len(records)}"
                        category = _guess_category(str(name), item)
                        nutrition = _map_to_nutrition(item)
                        records.append({
                            "id": str(food_id),
                            "name": str(name),
                            "category": category,
                            "nutrition": nutrition,
                        })
                    external_count += len(items)
                    files_used.append(fp.name)
                except (json.JSONDecodeError, OSError):
                    continue

        # 合并种子数据（兜底，确保高频食物始终可用）
        for seed in SEED_FOODS:
            nutrition = NutritionFacts(
                calories_kcal=seed.get("calories_kcal", 0),
                protein_g=seed.get("protein_g", 0),
                fat_g=seed.get("fat_g", 0),
                carbohydrate_g=seed.get("carbohydrate_g", 0),
                fiber_g=seed.get("fiber_g", 0),
                vitamin_a_ug=seed.get("vitamin_a_ug", 0),
                vitamin_c_mg=seed.get("vitamin_c_mg", 0),
                vitamin_e_mg=seed.get("vitamin_e_mg", 0),
                thiamin_mg=seed.get("thiamin_mg", 0),
                riboflavin_mg=seed.get("riboflavin_mg", 0),
                niacin_mg=seed.get("niacin_mg", 0),
                calcium_mg=seed.get("calcium_mg", 0),
                iron_mg=seed.get("iron_mg", 0),
                zinc_mg=seed.get("zinc_mg", 0),
                selenium_ug=seed.get("selenium_ug", 0),
                sodium_mg=seed.get("sodium_mg", 0),
                potassium_mg=seed.get("potassium_mg", 0),
                cholesterol_mg=seed.get("cholesterol_mg", 0),
                gi=seed.get("gi"),
            )
            records.append({
                "id": seed["id"],
                "name": seed["name"],
                "category": seed.get("category", "其他"),
                "nutrition": nutrition,
            })

        self._records = records
        self._source_stats = {
            "external_count": external_count,
            "seed_count": len(SEED_FOODS),
            "total_count": len(records),
            "files_used": files_used,
        }
        self._loaded = True

    def all(self) -> list[dict]:
        """返回所有食物记录"""
        self._load()
        return self._records

    def stats(self) -> dict:
        """返回数据库统计信息"""
        self._load()
        return self._source_stats

    def get_by_id(self, food_id: str) -> Optional[dict]:
        """按 ID 精确查询"""
        self._load()
        for r in self._records:
            if r["id"] == food_id:
                return r
        return None

    def search(self, name: str, limit: int = 10) -> list[dict]:
        """按名称查询：优先精确匹配，其次子串包含，返回候选列表

        Args:
            name: 食物名称关键词
            limit: 最多返回条数

        Returns:
            候选记录列表 [{id, name, category, nutrition, match_type}]
        """
        self._load()
        name_clean = name.strip().lower()
        exact, partial = [], []
        for r in self._records:
            rname = r["name"].lower()
            if rname == name_clean:
                exact.append({**r, "match_type": "exact"})
            elif name_clean in rname or rname in name_clean:
                partial.append({**r, "match_type": "partial"})
        results = exact + partial
        return results[:limit]

    def query_by_category(self, category: str, limit: int = 50) -> list[dict]:
        """按类别查询食物列表"""
        self._load()
        return [r for r in self._records if r["category"] == category][:limit]

    def get_nutrition(self, food_id: str, amount_g: float) -> Optional[NutritionFacts]:
        """按 ID + 份量查询营养素（自动按 100g 基准缩放）

        Args:
            food_id: 食物ID
            amount_g: 实际摄入克数

        Returns:
            缩放后的 NutritionFacts，未找到返回 None
        """
        record = self.get_by_id(food_id)
        if record is None:
            return None
        factor = amount_g / 100.0
        return record["nutrition"].scale(factor)

    def get_nutrition_by_name(self, name: str, amount_g: float) -> Optional[dict]:
        """按名称 + 份量查询营养素（取首个匹配）

        Returns:
            {food_id, name, category, amount_g, nutrition} 或 None
        """
        results = self.search(name, limit=1)
        if not results:
            return None
        r = results[0]
        factor = amount_g / 100.0
        return {
            "food_id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "amount_g": amount_g,
            "nutrition": r["nutrition"].scale(factor),
            "match_type": r.get("match_type", "partial"),
        }


# ──────────────────────────────────────────
# 模块级单例（对齐 DeepReview 的 get_storage 模式）
# ──────────────────────────────────────────

_db_instance: Optional[FoodDatabase] = None


def get_food_db() -> FoodDatabase:
    """获取 FoodDatabase 单例（指向项目 data/food_db 目录）"""
    global _db_instance
    if _db_instance is None:
        _db_instance = FoodDatabase()
    return _db_instance


def reset_food_db():
    """重置单例（测试用）"""
    global _db_instance
    _db_instance = None
