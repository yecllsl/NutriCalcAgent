# src/nutricalc_mcp/knowledge_map.py
"""营养知识图谱 — 食物分类、餐次、烹饪法、RNI 表、膳食指南常量

数据来源：
- 《中国居民膳食营养素参考摄入量（2023 版）》
- 《中国居民膳食指南（2022）》
- 中国食物成分表第 6 版食物分类

提供常量定义与 RNI 查询函数，供 tools 层和 web 层复用。
对齐 DeepReview knowledge_map.py 的"常量 + 查询/校验函数"模式。
"""
from __future__ import annotations

# ──────────────────────────────────────────
# 食物分类（对齐中国食物成分表分类）
# ──────────────────────────────────────────

FOOD_CATEGORIES = [
    "谷薯类", "蔬菜类", "水果类", "肉禽蛋类",
    "奶豆类", "水产类", "坚果类", "油脂类",
    "调味品", "混合菜", "饮料类", "其他",
]

# 餐次
MEAL_TYPES = ["早餐", "午餐", "晚餐", "加餐"]

# 烹饪法（影响油脂/营养素流失估算）
COOKING_METHODS = ["蒸", "煮", "炒", "炸", "烤", "炖", "凉拌", "生食", "卤", "煎"]

# 录入来源
FOOD_SOURCES = ["manual", "photo", "barcode", "ocr"]

# 生命阶段
LIFE_STAGES = ["儿童", "青少年", "成人", "孕妇", "乳母", "老年"]

# 活动水平
ACTIVITY_LEVELS = ["久坐", "轻度", "中度", "重度"]

# 性别
GENDERS = ["male", "female"]

# 健康目标
GOALS = [
    "maintain",              # 维持
    "lose",                  # 减脂
    "gain",                  # 增肌
    "control_diabetes",      # 控糖（糖尿病）
    "control_hypertension",  # 控压（高血压）
    "control_cholesterol",   # 降脂
    "pregnancy",             # 孕期
    "lactation",             # 哺乳期
]

# AI 营养师人设
PERSONAS = ["professional", "gentle", "strict"]


# ──────────────────────────────────────────
# 营养素元数据（中文名 / 单位 / NutritionFacts 字段名）
# 用于 RNI 查询、雷达图、缺口分析、统计展示
# ──────────────────────────────────────────

# 每项: (字段名, 中文名, 单位, 是否参与平衡评分)
NUTRIENT_META: list[dict] = [
    {"key": "calories_kcal", "name": "能量", "unit": "kcal", "score": True},
    {"key": "protein_g", "name": "蛋白质", "unit": "g", "score": True},
    {"key": "carbohydrate_g", "name": "碳水化合物", "unit": "g", "score": True},
    {"key": "fat_g", "name": "脂肪", "unit": "g", "score": True},
    {"key": "fiber_g", "name": "膳食纤维", "unit": "g", "score": True},
    {"key": "vitamin_a_ug", "name": "维生素A", "unit": "μg", "score": True},
    {"key": "vitamin_c_mg", "name": "维生素C", "unit": "mg", "score": True},
    {"key": "vitamin_e_mg", "name": "维生素E", "unit": "mg", "score": True},
    {"key": "thiamin_mg", "name": "硫胺素VB1", "unit": "mg", "score": True},
    {"key": "riboflavin_mg", "name": "核黄素VB2", "unit": "mg", "score": True},
    {"key": "niacin_mg", "name": "烟酸", "unit": "mg", "score": True},
    {"key": "calcium_mg", "name": "钙", "unit": "mg", "score": True},
    {"key": "iron_mg", "name": "铁", "unit": "mg", "score": True},
    {"key": "zinc_mg", "name": "锌", "unit": "mg", "score": True},
    {"key": "selenium_ug", "name": "硒", "unit": "μg", "score": True},
    {"key": "sodium_mg", "name": "钠", "unit": "mg", "score": True},
    {"key": "potassium_mg", "name": "钾", "unit": "mg", "score": True},
    {"key": "cholesterol_mg", "name": "胆固醇", "unit": "mg", "score": False},
]

# 雷达图推荐维度（10 个核心营养素）
RADAR_NUTRIENTS = [
    "protein_g", "fiber_g", "calcium_mg", "iron_mg", "zinc_mg",
    "vitamin_a_ug", "vitamin_c_mg", "thiamin_mg", "riboflavin_mg", "potassium_mg",
]

NUTRIENT_NAME_MAP = {n["key"]: n["name"] for n in NUTRIENT_META}
NUTRIENT_UNIT_MAP = {n["key"]: n["unit"] for n in NUTRIENT_META}


# ──────────────────────────────────────────
# 推荐摄入量 RNI 表（中国居民膳食营养素参考摄入量 2023 版）
# 按 [性别][生命阶段] 索引，值为 {营养素字段名: RNI 日值}
# 钠/钾为 PI（预防慢病建议值）；能量按轻体力活动估算
# ──────────────────────────────────────────

# 成年男性（18-49 岁，轻体力）
_RNI_MALE_ADULT = {
    "calories_kcal": 2250, "protein_g": 65, "carbohydrate_g": 130,
    "fat_g": 75, "fiber_g": 30,
    "vitamin_a_ug": 800, "vitamin_c_mg": 100, "vitamin_e_mg": 14,
    "thiamin_mg": 1.4, "riboflavin_mg": 1.4, "niacin_mg": 14,
    "calcium_mg": 800, "iron_mg": 12, "zinc_mg": 12.5, "selenium_ug": 60,
    "sodium_mg": 1500, "potassium_mg": 2000, "cholesterol_mg": 300,
}

# 成年女性（18-49 岁，轻体力；铁需求因育龄上调）
_RNI_FEMALE_ADULT = {
    "calories_kcal": 1800, "protein_g": 55, "carbohydrate_g": 130,
    "fat_g": 60, "fiber_g": 25,
    "vitamin_a_ug": 700, "vitamin_c_mg": 100, "vitamin_e_mg": 14,
    "thiamin_mg": 1.2, "riboflavin_mg": 1.2, "niacin_mg": 12,
    "calcium_mg": 800, "iron_mg": 18, "zinc_mg": 7.5, "selenium_ug": 53,
    "sodium_mg": 1500, "potassium_mg": 2000, "cholesterol_mg": 300,
}

# 老年男性（≥50 岁）：钙/VA/VD 上调，能量略降
_RNI_MALE_ELDERLY = {
    "calories_kcal": 2050, "protein_g": 72, "carbohydrate_g": 130,
    "fat_g": 68, "fiber_g": 30,
    "vitamin_a_ug": 800, "vitamin_c_mg": 100, "vitamin_e_mg": 14,
    "thiamin_mg": 1.4, "riboflavin_mg": 1.4, "niacin_mg": 14,
    "calcium_mg": 1000, "iron_mg": 12, "zinc_mg": 12.5, "selenium_ug": 60,
    "sodium_mg": 1400, "potassium_mg": 2000, "cholesterol_mg": 300,
}

# 老年女性（≥50 岁，绝经后铁需求下降）
_RNI_FEMALE_ELDERLY = {
    "calories_kcal": 1700, "protein_g": 62, "carbohydrate_g": 130,
    "fat_g": 57, "fiber_g": 25,
    "vitamin_a_ug": 700, "vitamin_c_mg": 100, "vitamin_e_mg": 14,
    "thiamin_mg": 1.2, "riboflavin_mg": 1.2, "niacin_mg": 12,
    "calcium_mg": 1000, "iron_mg": 10, "zinc_mg": 7.5, "selenium_ug": 53,
    "sodium_mg": 1400, "potassium_mg": 2000, "cholesterol_mg": 300,
}

# 孕妇（中晚期叠加）：能量+340kcal，蛋白+15g，叶酸/铁/钙显著上调
_RNI_FEMALE_PREGNANCY = {
    "calories_kcal": 2140, "protein_g": 70, "carbohydrate_g": 130,
    "fat_g": 71, "fiber_g": 28,
    "vitamin_a_ug": 770, "vitamin_c_mg": 115, "vitamin_e_mg": 14,
    "thiamin_mg": 1.4, "riboflavin_mg": 1.4, "niacin_mg": 12,
    "calcium_mg": 1000, "iron_mg": 24, "zinc_mg": 9.5, "selenium_ug": 56,
    "sodium_mg": 1500, "potassium_mg": 2000, "cholesterol_mg": 300,
}

# 乳母：能量+500kcal，蛋白+25g，钙/VA/VC 上调
_RNI_FEMALE_LACTATION = {
    "calories_kcal": 2300, "protein_g": 80, "carbohydrate_g": 130,
    "fat_g": 77, "fiber_g": 28,
    "vitamin_a_ug": 1300, "vitamin_c_mg": 150, "vitamin_e_mg": 17,
    "thiamin_mg": 1.5, "riboflavin_mg": 1.5, "niacin_mg": 15,
    "calcium_mg": 1000, "iron_mg": 24, "zinc_mg": 12, "selenium_ug": 65,
    "sodium_mg": 1500, "potassium_mg": 2400, "cholesterol_mg": 300,
}

# RNI 总表：[gender][life_stage] → RNI dict
RNI_TABLE: dict[str, dict[str, dict[str, float]]] = {
    "male": {
        "成人": _RNI_MALE_ADULT,
        "老年": _RNI_MALE_ELDERLY,
        "青少年": _RNI_MALE_ADULT,  # 简化：青少年近似成人
        "儿童": _RNI_MALE_ADULT,   # 简化
    },
    "female": {
        "成人": _RNI_FEMALE_ADULT,
        "老年": _RNI_FEMALE_ELDERLY,
        "青少年": _RNI_FEMALE_ADULT,
        "儿童": _RNI_FEMALE_ADULT,
        "孕妇": _RNI_FEMALE_PREGNANCY,
        "乳母": _RNI_FEMALE_LACTATION,
    },
}


def get_rni(gender: str, life_stage: str = "成人") -> dict[str, float]:
    """查询指定性别+生命阶段的 RNI 推荐摄入量表

    Args:
        gender: male / female
        life_stage: 成人/老年/孕妇/乳母/青少年/儿童

    Returns:
        {营养素字段名: RNI 日值}，未命中时回退到成人默认。
    """
    gender_table = RNI_TABLE.get(gender) or RNI_TABLE["male"]
    return gender_table.get(life_stage) or gender_table.get("成人") or _RNI_MALE_ADULT


# ──────────────────────────────────────────
# 《中国居民膳食指南（2022）》核心准则 — 用于规则化建议生成
# ──────────────────────────────────────────

DIETARY_GUIDELINES = [
    "食物多样，合理搭配——每天 12 种以上、每周 25 种以上食物",
    "多吃蔬果、奶类、全谷、大豆——蔬菜 ≥300g/天，水果 200-350g/天",
    "适量吃鱼、禽、蛋、瘦肉——每周鱼类 2 次，蛋类 7 个",
    "少盐少油，控糖限酒——盐 <5g，油 25-30g，添加糖 <25g/天",
    "规律进餐，足量饮水——每日饮水 1500-1700ml",
    "会烹会选，会看标签——优先选择低钠、低糖食品",
    "分餐公筷，杜绝浪费",
    "公筷分餐，饮食卫生",
]

# 慢病人群膳食要点
CHRONIC_DISEASE_TIPS = {
    "control_diabetes": [
        "控糖：主食粗细搭配，优选低 GI 食物（GI<55）",
        "定时定量，少食多餐，避免单次大量碳水",
        "蔬菜先吃，延缓糖分吸收",
        "避免含糖饮料、精制糕点",
    ],
    "control_hypertension": [
        "DASH 饮食：多蔬果、全谷、低脂奶",
        "限钠 <5g/天，钾摄入 ≥2000mg/天",
        "限酒，戒烟",
        "减少加工肉、腌制食品",
    ],
    "control_cholesterol": [
        "限制饱和脂肪 <10% 总能量，反式脂肪 <1%",
        "增加可溶性纤维（燕麦、豆类、果蔬）",
        "用不饱和脂肪替代饱和脂肪（鱼、坚果、橄榄油）",
        "限制胆固醇 <300mg/天",
    ],
    "pregnancy": [
        "孕中晚期每日 +340kcal，蛋白 +15g",
        "叶酸 600μg/天，铁 24mg/天，钙 1000mg/天",
        "每周吃鱼类 2-3 次补充 DHA",
        "禁忌：生食、高汞鱼、酒精、未杀菌奶",
    ],
    "lactation": [
        "哺乳期每日 +500kcal，蛋白 +25g",
        "钙 1000mg/天，VA 1300μg/天",
        "足量饮水，保证泌乳",
        "避免回奶食物（大量韭菜、麦芽等，个体差异）",
    ],
}

# 营养素缺口/过量的阈值（达成率 ratio = actual/target）
GAP_THRESHOLDS = {
    "deficient": 0.8,    # <80% 视为不足
    "excessive": 1.5,    # 钠/胆固醇等超过 150% 视为过量（部分营养素另设）
}

# 需要监控"过量"的营养素（钠、胆固醇）
EXCESSIVE_NUTRIENTS = {"sodium_mg", "cholesterol_mg"}


def get_nutrient_name(key: str) -> str:
    """营养素字段名 → 中文名"""
    return NUTRIENT_NAME_MAP.get(key, key)


def get_nutrient_unit(key: str) -> str:
    """营养素字段名 → 单位"""
    return NUTRIENT_UNIT_MAP.get(key, "")


def validate_food_category(category: str) -> bool:
    return category in FOOD_CATEGORIES


def validate_meal_type(meal_type: str) -> bool:
    return meal_type in MEAL_TYPES
