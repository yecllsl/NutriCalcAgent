# tests/test_web.py
"""Web API 集成测试 — 使用 FastAPI TestClient"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(patch_storage):
    """FastAPI 测试客户端（使用临时存储）"""
    from nutricalc_mcp.web.app import create_app
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client_with_data(patch_storage, seeded_logs, sample_profile_data):
    """带测试数据的 FastAPI 测试客户端"""
    from nutricalc_mcp.tools.crud import save_user_profile
    save_user_profile(sample_profile_data)
    from nutricalc_mcp.web.app import create_app
    app = create_app()
    return TestClient(app)


class TestDashboard:
    """概览页"""

    def test_dashboard_partial(self, client):
        """概览片段返回 200"""
        r = client.get("/partials/dashboard")
        assert r.status_code == 200
        assert "今日能量" in r.text

    def test_dashboard_summary_api(self, client):
        """概览 API 返回 JSON"""
        r = client.get("/api/dashboard/summary")
        assert r.status_code == 200
        data = r.json()
        assert "today_calories" in data
        assert "target_calories" in data


class TestLogs:
    """饮食记录页"""

    def test_logs_partial(self, client_with_data):
        """记录片段返回 200 且包含已有记录"""
        r = client_with_data.get("/partials/logs")
        assert r.status_code == 200
        assert "记录一餐" in r.text

    def test_add_log(self, client):
        """新增记录"""
        r = client.post("/api/logs/add", data={
            "meal_time": "2026-07-24T12:30",
            "meal_type": "午餐",
            "food_names": "米饭(蒸),番茄炒蛋",
            "food_amounts": "200,250",
            "food_categories": "谷薯类,混合菜",
            "cooking_methods": "蒸,炒",
            "note": "测试",
        })
        assert r.status_code == 200

    def test_logs_api(self, client_with_data):
        """记录列表 API"""
        r = client_with_data.get("/api/logs")
        assert r.status_code == 200
        data = r.json()
        assert data["total_count"] > 0

    def test_delete_log(self, client_with_data, seeded_logs):
        """删除记录"""
        log_id = seeded_logs[0]
        r = client_with_data.delete(f"/api/logs/{log_id}")
        assert r.status_code == 200


class TestStats:
    """统计页"""

    def test_stats_partial(self, client_with_data):
        """统计片段返回 200"""
        r = client_with_data.get("/partials/stats")
        assert r.status_code == 200

    def test_stats_api(self, client_with_data):
        """统计 API"""
        r = client_with_data.get("/api/stats?group_by=meal_type")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data


class TestAnalysis:
    """分析页"""

    def test_analysis_partial(self, client_with_data):
        """分析片段返回 200"""
        r = client_with_data.get("/partials/analysis")
        assert r.status_code == 200
        assert "平衡评分" in r.text

    def test_analysis_balance_api(self, client_with_data):
        """平衡评估 API"""
        r = client_with_data.get("/api/analysis/balance?period=weekly")
        assert r.status_code == 200
        data = r.json()
        assert "assessment" in data

    def test_analysis_advice_api(self, client_with_data):
        """营养师建议 API"""
        r = client_with_data.get("/api/analysis/advice?period=weekly&persona=gentle")
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "advice"
        assert data["persona"] == "gentle"


class TestProfile:
    """用户档案页"""

    def test_profile_partial(self, client_with_data):
        """档案片段返回 200"""
        r = client_with_data.get("/partials/profile")
        assert r.status_code == 200

    def test_save_profile(self, client):
        """保存档案"""
        r = client.post("/api/profile/save", data={
            "age": 30,
            "gender": "male",
            "height_cm": 175,
            "weight_kg": 70,
            "activity_level": "轻度",
            "goal": "maintain",
            "life_stage": "成人",
            "allergies": "",
        })
        assert r.status_code == 200

    def test_profile_api(self, client):
        """档案 API"""
        r = client.get("/api/profile")
        assert r.status_code == 200
        data = r.json()
        assert "age" in data
