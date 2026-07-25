# tests/test_models.py
"""数据模型校验测试"""
import pytest
from pydantic import ValidationError

from nutricalc_mcp.models import (
    NutritionFacts, FoodItem, FoodLog, UserProfile,
    NutrientGap, BalanceAssessment,
)


class TestNutritionFacts:
    """营养成分模型测试"""

    def test_default_values(self):
        """默认值全为 0，避免聚合时 NaN 污染"""
        n = NutritionFacts()
        assert n.calories_kcal == 0.0
        assert n.protein_g == 0.0
        assert n.gi is None  # GI 是可选字段

    def test_scale(self):
        """按系数缩放营养素（份量换算）"""
        n = NutritionFacts(calories_kcal=100, protein_g=5, gi=50)
        scaled = n.scale(2.0)
        assert scaled.calories_kcal == 200.0
        assert scaled.protein_g == 10.0
        assert scaled.gi == 50  # GI 不随份量变化

    def test_add(self):
        """累加两份营养素"""
        a = NutritionFacts(calories_kcal=100, protein_g=5)
        b = NutritionFacts(calories_kcal=200, protein_g=10)
        total = a.add(b)
        assert total.calories_kcal == 300.0
        assert total.protein_g == 15.0


class TestFoodItem:
    """食物项模型测试"""

    def test_valid_item(self):
        item = FoodItem(name="米饭", amount_g=200, category="谷薯类")
        assert item.source == "manual"  # 默认来源
        assert item.food_id == ""  # 默认空

    def test_invalid_source(self):
        """source 必须是 manual/photo/barcode/ocr 之一"""
        with pytest.raises(ValidationError):
            FoodItem(name="米饭", amount_g=200, source="invalid")


class TestFoodLog:
    """饮食记录模型测试"""

    def test_valid_log(self, sample_food_log_data):
        log = FoodLog.model_validate(sample_food_log_data)
        assert log.meal_type == "午餐"
        assert len(log.items) == 2
        assert log.confirmed is True

    def test_invalid_meal_type(self, sample_food_log_data):
        """meal_type 必须是 早餐/午餐/晚餐/加餐"""
        sample_food_log_data["meal_type"] = "夜宵"
        with pytest.raises(ValidationError):
            FoodLog.model_validate(sample_food_log_data)


class TestUserProfile:
    """用户档案模型测试"""

    def test_valid_profile(self, sample_profile_data):
        profile = UserProfile.model_validate(sample_profile_data)
        assert profile.gender == "female"
        assert profile.goal == "lose"

    def test_invalid_gender(self, sample_profile_data):
        sample_profile_data["gender"] = "other"
        with pytest.raises(ValidationError):
            UserProfile.model_validate(sample_profile_data)

    def test_age_range(self, sample_profile_data):
        """年龄必须在 1-120 之间"""
        sample_profile_data["age"] = 0
        with pytest.raises(ValidationError):
            UserProfile.model_validate(sample_profile_data)
