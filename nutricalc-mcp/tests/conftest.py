# tests/conftest.py
"""共享测试 fixtures

提供临时数据目录、测试用饮食记录、用户档案等 fixtures，
确保测试隔离（不污染真实 data/ 目录）。
"""
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """临时数据目录（每个测试独立，自动清理）"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def tmp_storage(tmp_data_dir: Path):
    """指向临时目录的 Storage 实例"""
    from nutricalc_mcp.storage import Storage
    return Storage(base_dir=tmp_data_dir)


@pytest.fixture
def patch_storage(tmp_storage, monkeypatch):
    """patch crud.get_storage 与 food_db 默认目录，使所有工具层使用临时存储"""
    from nutricalc_mcp.tools import crud
    monkeypatch.setattr(crud, "get_storage", lambda: tmp_storage)
    # 同时 patch 已导入的引用
    import nutricalc_mcp.tools.balance_assess as ba
    import nutricalc_mcp.tools.statistics as st
    import nutricalc_mcp.tools.nutritionist as nu
    import nutricalc_mcp.tools.export as ex
    monkeypatch.setattr(ba, "get_storage", lambda: tmp_storage)
    monkeypatch.setattr(st, "get_storage", lambda: tmp_storage)
    monkeypatch.setattr(nu, "get_storage", lambda: tmp_storage)
    monkeypatch.setattr(ex, "get_storage", lambda: tmp_storage)
    return tmp_storage


@pytest.fixture
def sample_profile_data() -> dict:
    """测试用用户档案（成年女性，减脂目标）"""
    return {
        "user_id": "default",
        "age": 28,
        "gender": "female",
        "height_cm": 165,
        "weight_kg": 55,
        "activity_level": "轻度",
        "goal": "lose",
        "life_stage": "成人",
        "allergies": [],
    }


@pytest.fixture
def sample_food_items() -> list[dict]:
    """测试用食物项（米饭 + 番茄炒蛋）"""
    return [
        {"name": "米饭(蒸)", "amount_g": 200, "category": "谷薯类"},
        {"name": "番茄炒蛋", "amount_g": 250, "category": "混合菜"},
    ]


@pytest.fixture
def sample_food_log_data() -> dict:
    """测试用饮食记录数据（午餐）"""
    now = datetime.now(timezone.utc)
    return {
        "meal_time": now.isoformat(),
        "meal_type": "午餐",
        "items": [
            {"food_id": "", "name": "米饭(蒸)", "amount_g": 200,
             "category": "谷薯类", "source": "manual"},
            {"food_id": "", "name": "番茄炒蛋", "amount_g": 250,
             "category": "混合菜", "source": "manual"},
        ],
        "note": "测试午餐",
        "confirmed": True,
    }


@pytest.fixture
def seeded_logs(patch_storage, sample_food_log_data) -> list[str]:
    """在临时存储中播种多条饮食记录，返回 log_id 列表

    保存前自动调用 analyze_nutrition 填充营养数据（模拟 services.add_food_log 行为），
    确保后续的平衡评估/统计测试有非零营养数据可用。
    """
    from nutricalc_mcp.tools.crud import save_food_log
    from nutricalc_mcp.tools.nutrition_analyze import analyze_nutrition
    log_ids = []
    base_time = datetime.now(timezone.utc)
    # 播种 3 天的记录
    for day_offset in range(3):
        for meal_type, items, hour in [
            ("早餐", [{"food_id": "", "name": "燕麦片", "amount_g": 50,
                       "category": "谷薯类", "source": "manual"},
                      {"food_id": "", "name": "牛奶", "amount_g": 250,
                       "category": "奶豆类", "source": "manual"}], 8),
            ("午餐", [{"food_id": "", "name": "米饭(蒸)", "amount_g": 150,
                       "category": "谷薯类", "source": "manual"},
                      {"food_id": "", "name": "番茄炒蛋", "amount_g": 200,
                       "category": "混合菜", "source": "manual"}], 12),
        ]:
            # 调用营养分析填充 nutrition 字段
            analyze_result = analyze_nutrition(items)
            analyzed_map = {a.get("name"): a for a in analyze_result.get("items", [])}
            for it in items:
                a = analyzed_map.get(it.get("name"))
                if a and a.get("nutrition"):
                    it["nutrition"] = a["nutrition"]
                    it["food_id"] = a.get("food_id") or it.get("food_id", "")

            log_data = {
                "meal_time": (base_time - timedelta(days=day_offset, hours=0)).replace(hour=hour).isoformat(),
                "meal_type": meal_type,
                "items": items,
                "note": f"测试{meal_type}day{day_offset}",
                "confirmed": True,
                "nutrition": analyze_result.get("total_nutrition"),
            }
            result = save_food_log(log_data)
            log_ids.append(result["log_id"])
    return log_ids
