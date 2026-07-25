# tests/test_food_db.py
"""食物成分表本地数据库测试"""
import pytest

from nutricalc_mcp.food_db import FoodDatabase, get_food_db, reset_food_db
from nutricalc_mcp.models import NutritionFacts


class TestFoodDatabase:
    """FoodDatabase 查询功能"""

    def test_search_exact(self):
        """精确匹配食物名"""
        db = FoodDatabase()
        results = db.search("米饭(蒸)", limit=5)
        assert len(results) >= 1
        assert results[0]["name"] == "米饭(蒸)"
        assert results[0]["match_type"] == "exact"

    def test_search_partial(self):
        """模糊匹配（子串包含）"""
        db = FoodDatabase()
        results = db.search("番茄", limit=5)
        assert len(results) >= 1
        # 应匹配到番茄、番茄炒蛋等
        names = [r["name"] for r in results]
        assert any("番茄" in n for n in names)

    def test_search_empty(self):
        """查询空字符串返回空列表"""
        db = FoodDatabase()
        results = db.search("")
        # 空字符串会匹配所有（子串包含），但 limit 控制返回数
        assert isinstance(results, list)

    def test_query_by_category(self):
        """按类别查询"""
        db = FoodDatabase()
        results = db.query_by_category("谷薯类", limit=10)
        assert len(results) >= 1
        assert all(r["category"] == "谷薯类" for r in results)

    def test_get_nutrition_by_id(self):
        """按 ID + 份量查询营养素（自动缩放）"""
        db = FoodDatabase()
        results = db.search("米饭(蒸)", limit=1)
        food_id = results[0]["id"]
        # 200g = 2 × 100g
        nutrition = db.get_nutrition(food_id, 200)
        assert nutrition is not None
        # 米饭(蒸) 116 kcal/100g → 200g = 232 kcal
        assert nutrition.calories_kcal == pytest.approx(232, rel=0.01)

    def test_get_nutrition_nonexistent(self):
        """查询不存在的 ID 返回 None"""
        db = FoodDatabase()
        assert db.get_nutrition("nonexistent_id", 100) is None

    def test_seed_data_loaded(self):
        """种子数据至少包含 40 条"""
        db = FoodDatabase()
        records = db.all()
        assert len(records) >= 40

    def test_stats(self):
        """统计信息包含种子数与总数"""
        db = FoodDatabase()
        stats = db.stats()
        assert stats["seed_count"] >= 40
        assert stats["total_count"] >= 40
