# tests/test_storage.py
"""存储引擎测试 — FoodLog CRUD / UserProfile / 过滤查询"""
import pytest
from datetime import datetime, timezone, timedelta

from nutricalc_mcp.models import FoodLog, UserProfile
from nutricalc_mcp.storage import Storage, _deep_merge


class TestFoodLogCRUD:
    """饮食记录 CRUD"""

    def test_save_and_load(self, tmp_storage, sample_food_log_data):
        """保存后能正确加载"""
        log = FoodLog.model_validate(sample_food_log_data)
        result = tmp_storage.save_food_log(log)
        assert "log_id" in result

        loaded = tmp_storage.load_food_log(log.log_id)
        assert loaded is not None
        assert loaded.meal_type == "午餐"
        assert len(loaded.items) == 2

    def test_load_nonexistent(self, tmp_storage):
        """加载不存在的记录返回 None"""
        assert tmp_storage.load_food_log("fl_nonexistent") is None

    def test_delete(self, tmp_storage, sample_food_log_data):
        """删除记录后无法加载"""
        log = FoodLog.model_validate(sample_food_log_data)
        tmp_storage.save_food_log(log)
        assert tmp_storage.delete_food_log(log.log_id) is True
        assert tmp_storage.load_food_log(log.log_id) is None

    def test_delete_nonexistent(self, tmp_storage):
        """删除不存在的记录返回 False"""
        assert tmp_storage.delete_food_log("fl_nonexistent") is False

    def test_patch(self, tmp_storage, sample_food_log_data):
        """部分更新（patch）记录"""
        log = FoodLog.model_validate(sample_food_log_data)
        tmp_storage.save_food_log(log)
        updated = tmp_storage.patch_food_log(log.log_id, {"note": "更新后的备注"})
        assert updated is not None
        assert updated.note == "更新后的备注"
        # 原有字段保持不变
        assert updated.meal_type == "午餐"

    def test_patch_nonexistent(self, tmp_storage):
        """patch 不存在的记录返回 None"""
        assert tmp_storage.patch_food_log("fl_nonexistent", {"note": "x"}) is None


class TestQueryFilters:
    """过滤查询"""

    def test_query_all(self, tmp_storage, sample_food_log_data):
        """无过滤条件返回全部"""
        log = FoodLog.model_validate(sample_food_log_data)
        tmp_storage.save_food_log(log)
        result = tmp_storage.query_food_logs(filters={})
        assert result["total_count"] == 1

    def test_filter_by_meal_type(self, tmp_storage, sample_food_log_data):
        """按餐次过滤"""
        log = FoodLog.model_validate(sample_food_log_data)
        tmp_storage.save_food_log(log)
        result = tmp_storage.query_food_logs(filters={"meal_type": "午餐"})
        assert result["total_count"] == 1
        result = tmp_storage.query_food_logs(filters={"meal_type": "早餐"})
        assert result["total_count"] == 0

    def test_filter_by_date_range(self, tmp_storage, sample_food_log_data):
        """按日期范围过滤"""
        log = FoodLog.model_validate(sample_food_log_data)
        tmp_storage.save_food_log(log)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        result = tmp_storage.query_food_logs(
            filters={"date_range": {"start": today, "end": today}}
        )
        assert result["total_count"] == 1
        # 查未来日期应无结果
        future = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")
        result = tmp_storage.query_food_logs(
            filters={"date_range": {"start": future, "end": future}}
        )
        assert result["total_count"] == 0


class TestUserProfile:
    """用户档案"""

    def test_save_and_load(self, tmp_storage, sample_profile_data):
        profile = UserProfile.model_validate(sample_profile_data)
        tmp_storage.save_user_profile(profile)
        loaded = tmp_storage.load_user_profile("default")
        assert loaded is not None
        assert loaded.age == 28

    def test_load_nonexistent(self, tmp_storage):
        """加载不存在的档案返回 None"""
        assert tmp_storage.load_user_profile("nonexistent") is None


class TestDeepMerge:
    """递归合并工具函数"""

    def test_shallow_merge(self):
        base = {"a": 1, "b": 2}
        patch = {"b": 3, "c": 4}
        result = _deep_merge(base, patch)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        patch = {"a": {"y": 3, "z": 4}}
        result = _deep_merge(base, patch)
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}
