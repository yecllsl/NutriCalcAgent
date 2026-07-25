# src/nutricalc_mcp/models.py
"""数据模型定义 - NutriCalcAgent 营养师 Agent 的核心数据结构

包含: NutritionFacts, FoodItem, FoodLog, UserProfile, BalanceAssessment, NutritionAdvice

设计原则（对齐 DeepReview）:
- Pydantic 2 BaseModel + 嵌套模型
- field_validator 校验枚举值（食物类别/餐次/生命阶段等）
- Optional + 默认值，支持渐进式录入与 AI 二次填充
- 营养素字段覆盖《中国食物成分表》第 6 版核心指标 + 中国居民膳食营养素参考摄入量
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────
# 营养成分模型
# ──────────────────────────────────────────

class NutritionFacts(BaseModel):
    """营养成分（按"每份"或"每 100g"计量，由调用方约定单位）

    字段覆盖中国食物成分表核心营养素：
    - 宏量：能量/蛋白质/脂肪/碳水/膳食纤维
    - 维生素：VA(视黄醇当量)/VC/VE/VB1/VB2/烟酸
    - 矿物质：钙/铁/锌/硒/钠/钾
    - 其他：胆固醇/GI(血糖生成指数)
    缺失值默认 0.0，避免统计聚合时 NaN 污染。
    """
    calories_kcal: float = Field(default=0.0, description="能量 kcal")
    protein_g: float = Field(default=0.0, description="蛋白质 g")
    carbohydrate_g: float = Field(default=0.0, description="碳水化合物 g")
    fat_g: float = Field(default=0.0, description="脂肪 g")
    fiber_g: float = Field(default=0.0, description="膳食纤维 g")
    # 维生素
    vitamin_a_ug: float = Field(default=0.0, description="视黄醇当量 μg")
    vitamin_c_mg: float = Field(default=0.0, description="维生素 C mg")
    vitamin_e_mg: float = Field(default=0.0, description="维生素 E mg")
    thiamin_mg: float = Field(default=0.0, description="硫胺素 VB1 mg")
    riboflavin_mg: float = Field(default=0.0, description="核黄素 VB2 mg")
    niacin_mg: float = Field(default=0.0, description="烟酸 mg")
    # 矿物质
    calcium_mg: float = Field(default=0.0, description="钙 mg")
    iron_mg: float = Field(default=0.0, description="铁 mg")
    zinc_mg: float = Field(default=0.0, description="锌 mg")
    selenium_ug: float = Field(default=0.0, description="硒 μg")
    sodium_mg: float = Field(default=0.0, description="钠 mg")
    potassium_mg: float = Field(default=0.0, description="钾 mg")
    # 其他
    cholesterol_mg: float = Field(default=0.0, description="胆固醇 mg")
    gi: Optional[float] = Field(default=None, description="血糖生成指数 GI（0-100）")

    def scale(self, factor: float) -> "NutritionFacts":
        """按系数缩放所有营养素（用于份量换算：100g → 实际克数）"""
        data = self.model_dump()
        result = {}
        for k, v in data.items():
            if k == "gi":
                result[k] = v  # GI 是食物固有属性，不随份量变化
            elif isinstance(v, (int, float)):
                result[k] = round(v * factor, 3)
            else:
                result[k] = v
        return NutritionFacts(**result)

    def add(self, other: "NutritionFacts") -> "NutritionFacts":
        """累加另一份营养素（用于多食物聚合、日/周/月汇总）"""
        data = {}
        for k in type(self).model_fields:
            a = getattr(self, k)
            b = getattr(other, k, 0)
            if k == "gi":
                # GI 取加权近似：有值优先，都无值则 None
                data[k] = a if a is not None else b
            else:
                data[k] = round((a or 0) + (b or 0), 3)
        return NutritionFacts(**data)


# ──────────────────────────────────────────
# 食物项 / 饮食记录
# ──────────────────────────────────────────

class FoodItem(BaseModel):
    """饮食记录中的单个食物项"""
    food_id: str = Field(default="", description="食物条目ID（对应本地食物库ID或自由编号，手动录入可空）")
    name: str = Field(description="食物名称（如 番茄/麻婆豆腐/牛奶）")
    category: str = Field(default="其他", description="食物类别（见 knowledge_map.FOOD_CATEGORIES）")
    amount_g: float = Field(description="份量（克）")
    source: str = Field(default="manual", description="录入来源：manual/photo/barcode/ocr")
    cooking_method: Optional[str] = Field(default=None, description="烹饪法：蒸/煮/炒/炸/烤/凉拌/生食")
    confidence: Optional[float] = Field(default=None, description="AI 识别置信度 0-1")
    nutrition: Optional[NutritionFacts] = Field(default=None, description="本项营养成分（按 amount_g 计）")

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        valid = {"manual", "photo", "barcode", "ocr"}
        if v not in valid:
            raise ValueError(f"source 必须是 {valid} 之一，收到: {v}")
        return v


class FoodLog(BaseModel):
    """饮食记录核心模型——一次进食（一餐或一次加餐）的完整记录"""
    log_id: str = Field(default="", description="记录唯一ID，格式 fl_YYYYMMDD_NNN，保存时自动生成")
    created_at: datetime = Field(default_factory=datetime.now, description="记录创建时间")
    meal_time: datetime = Field(description="实际进食时间")
    meal_type: str = Field(description="餐次：早餐/午餐/晚餐/加餐")
    image_path: Optional[str] = Field(default=None, description="食物图片本地路径")
    items: list[FoodItem] = Field(default_factory=list, description="本餐食物项列表")
    nutrition: Optional[NutritionFacts] = Field(default=None, description="本餐汇总营养（所有 items 累加）")
    note: str = Field(default="", description="用户备注")
    confirmed: bool = Field(default=False, description="是否经用户确认（识别/分析结果）")

    @field_validator("meal_type")
    @classmethod
    def validate_meal_type(cls, v: str) -> str:
        valid = {"早餐", "午餐", "晚餐", "加餐"}
        if v not in valid:
            raise ValueError(f"meal_type 必须是 {valid} 之一，收到: {v}")
        return v


# ──────────────────────────────────────────
# 用户档案（个性化 RNI 计算）
# ──────────────────────────────────────────

class UserProfile(BaseModel):
    """用户档案——用于计算个性化推荐摄入量（RNI）与营养平衡评估基准"""
    user_id: str = Field(default="default", description="用户ID（本地单用户默认 default）")
    age: int = Field(ge=1, le=120, description="年龄")
    gender: str = Field(description="性别：male/female")
    height_cm: float = Field(gt=0, description="身高 cm")
    weight_kg: float = Field(gt=0, description="体重 kg")
    activity_level: str = Field(default="轻度", description="活动水平：久坐/轻度/中度/重度")
    goal: str = Field(default="maintain", description="目标：maintain/lose/gain/control_diabetes/control_hypertension/pregnancy/lactation")
    life_stage: str = Field(default="成人", description="生命阶段：成人/孕妇/乳母/老年/儿童")
    allergies: list[str] = Field(default_factory=list, description="过敏/忌口食物列表")
    created_at: datetime = Field(default_factory=datetime.now)

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v: str) -> str:
        valid = {"male", "female"}
        if v not in valid:
            raise ValueError(f"gender 必须是 {valid} 之一，收到: {v}")
        return v


# ──────────────────────────────────────────
# 营养平衡评估
# ──────────────────────────────────────────

class NutrientGap(BaseModel):
    """单个营养素的缺口/过量项"""
    nutrient: str = Field(description="营养素名称（中文）")
    nutrient_key: str = Field(description="营养素字段名（对应 NutritionFacts 字段）")
    status: str = Field(description="状态：deficient(不足)/excessive(过量)/adequate(达标)")
    actual: float = Field(description="实际摄入量")
    target: float = Field(description="推荐摄入量 RNI")
    ratio: float = Field(description="达成率 = actual/target")
    unit: str = Field(description="单位")


class BalanceAssessment(BaseModel):
    """营养平衡评估结果——基于日/周/月时序聚合后对 RNI 的达成率分析"""
    assessment_id: str = Field(description="评估ID")
    created_at: datetime = Field(default_factory=datetime.now)
    period: str = Field(description="评估周期：daily/weekly/monthly")
    start_date: str = Field(description="起始日期 YYYY-MM-DD")
    end_date: str = Field(description="结束日期 YYYY-MM-DD")
    days: int = Field(description="覆盖天数")
    total_nutrition: NutritionFacts = Field(description="周期内总摄入")
    avg_daily_nutrition: NutritionFacts = Field(description="日均摄入")
    rni_achievement: dict[str, float] = Field(default_factory=dict, description="各营养素达成率% {nutrient_key: ratio}")
    balance_score: float = Field(default=0.0, description="平衡评分 0-100")
    gaps: list[NutrientGap] = Field(default_factory=list, description="营养缺口/过量清单")
    diversity_score: Optional[float] = Field(default=None, description="饮食多样性评分 0-100（食物种类数）")
    recommendations: list[str] = Field(default_factory=list, description="基于规则的结构化建议")


# ──────────────────────────────────────────
# AI 营养师建议
# ──────────────────────────────────────────

class NutritionAdvice(BaseModel):
    """AI 营养师建议结果"""
    advice_id: str = Field(description="建议ID")
    created_at: datetime = Field(default_factory=datetime.now)
    period: str = Field(description="对应周期：daily/weekly/monthly")
    persona: str = Field(default="professional", description="人设：professional/gentle/strict")
    summary: str = Field(default="", description="一句话总览")
    gaps: list[NutrientGap] = Field(default_factory=list, description="关键营养缺口")
    recommendations: list[str] = Field(default_factory=list, description="具体可执行建议")
    next_meal_suggestion: Optional[str] = Field(default=None, description="下一餐建议")
    caution: str = Field(default="", description="免责声明：非医疗建议，慢病请遵医嘱")
