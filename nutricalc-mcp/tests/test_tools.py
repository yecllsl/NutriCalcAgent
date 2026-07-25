# tests/test_tools.py
"""工具层测试 — 营养分析/平衡评估/统计/营养师/导出"""
import pytest

from nutricalc_mcp.tools.nutrition_analyze import analyze_nutrition
from nutricalc_mcp.tools.balance_assess import assess_balance
from nutricalc_mcp.tools.statistics import get_statistics
from nutricalc_mcp.tools.nutritionist import nutritionist_advice, interpret_trend
from nutricalc_mcp.tools.export import export_data, export_summary
from nutricalc_mcp.tools.crud import save_food_log, save_user_profile


class TestAnalyzeNutrition:
    """营养分析工具"""

    def test_analyze_matched_items(self, sample_food_items):
        """本地库命中的食物项应返回营养素"""
        result = analyze_nutrition(sample_food_items)
        assert result["matched_count"] == 2
        assert result["unmatched_count"] == 0
        assert result["total_nutrition"]["calories_kcal"] > 0
        assert result["needs_llm"] is False

    def test_analyze_unmatched(self):
        """未命中的食物应返回估算 prompt"""
        items = [{"name": "非常罕见的外星食物", "amount_g": 100}]
        result = analyze_nutrition(items)
        assert result["unmatched_count"] == 1
        assert result["needs_llm"] is True
        assert "estimate_prompts" in result

    def test_analyze_empty(self):
        """空列表返回空结果"""
        result = analyze_nutrition([])
        assert result["items"] == []
        assert result["matched_count"] == 0


class TestAssessBalance:
    """营养平衡评估工具"""

    def test_assess_daily_empty(self, patch_storage):
        """无记录时评估不报错，评分为 0"""
        result = assess_balance(period="daily")
        assert "assessment" in result
        assert result["assessment"]["balance_score"] == 0.0

    def test_assess_with_logs(self, patch_storage, seeded_logs, sample_profile_data):
        """有记录时评估返回非零评分"""
        save_user_profile(sample_profile_data)
        result = assess_balance(period="weekly")
        assert "assessment" in result
        assessment = result["assessment"]
        assert assessment["days"] == 7
        assert "radar_data" in result
        # 有记录时总能量应 > 0
        assert assessment["total_nutrition"]["calories_kcal"] > 0

    def test_assess_custom_range(self, patch_storage, seeded_logs):
        """自定义日期范围"""
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        result = assess_balance(period="daily", start_date=today, end_date=today)
        assert result["assessment"]["days"] == 1


class TestStatistics:
    """统计工具"""

    def test_stats_empty(self, patch_storage):
        """无记录时返回空统计"""
        result = get_statistics(group_by="date")
        assert result["total"] == 0
        assert result["items"] == []

    def test_stats_by_meal_type(self, patch_storage, seeded_logs):
        """按餐次统计"""
        result = get_statistics(group_by="meal_type")
        assert result["total"] > 0
        # 应包含早餐和午餐
        names = [item["name"] for item in result["items"]]
        assert "早餐" in names
        assert "午餐" in names

    def test_stats_trends(self, patch_storage, seeded_logs):
        """30天趋势数据结构正确"""
        result = get_statistics(group_by="date")
        trends = result["trends"]
        assert len(trends) == 30  # 30 天

    def test_stats_radar_data(self, patch_storage, seeded_logs, sample_profile_data):
        """雷达图数据结构"""
        save_user_profile(sample_profile_data)
        result = get_statistics(group_by="date")
        radar = result["radar_data"]
        assert "indicators" in radar
        assert "values" in radar


class TestNutritionist:
    """AI 营养师工具"""

    def test_advice_mode(self, patch_storage, seeded_logs, sample_profile_data):
        """建议模式（无 question）"""
        save_user_profile(sample_profile_data)
        result = nutritionist_advice(period="weekly", persona="gentle")
        assert result["mode"] == "advice"
        assert result["persona"] == "gentle"
        assert "advice_prompt" in result
        assert "温暖" in result["advice_prompt"]  # gentle 人设关键词

    def test_chat_mode(self, patch_storage, seeded_logs, sample_profile_data):
        """对话模式（有 question）"""
        save_user_profile(sample_profile_data)
        result = nutritionist_advice(
            period="weekly", persona="strict", question="能吃甜点吗？"
        )
        assert result["mode"] == "chat"
        assert "advice_prompt" in result
        assert "严格" in result["advice_prompt"]  # strict 人设关键词

    def test_next_meal_prompt(self, patch_storage, seeded_logs, sample_profile_data):
        """daily + 建议模式包含下一餐 prompt"""
        save_user_profile(sample_profile_data)
        result = nutritionist_advice(period="daily")
        assert "next_meal_prompt" in result

    def test_invalid_persona_fallback(self, patch_storage, seeded_logs):
        """无效人设回退到 professional"""
        result = nutritionist_advice(period="daily", persona="invalid")
        assert result["persona"] == "professional"

    def test_interpret_trend(self, patch_storage, seeded_logs, sample_profile_data):
        """趋势解读"""
        save_user_profile(sample_profile_data)
        result = interpret_trend(period="weekly")
        assert "trend_prompt" in result
        assert "energy_trend" in result


class TestExport:
    """数据导出工具"""

    def test_export_json(self, patch_storage, seeded_logs):
        """JSON 导出"""
        result = export_data(format="json")
        assert result["format"] == "json"
        assert result["log_count"] > 0
        assert "content" in result
        assert result["needs_confirmation"] is True

    def test_export_csv(self, patch_storage, seeded_logs):
        """CSV 导出"""
        result = export_data(format="csv")
        assert result["format"] == "csv"
        assert "content" in result
        assert "\ufeff" in result["content"]  # BOM

    def test_export_empty(self, patch_storage):
        """无记录时导出不报错"""
        result = export_data(format="json")
        assert result["log_count"] == 0

    def test_export_summary(self, patch_storage, seeded_logs):
        """导出预览"""
        result = export_summary()
        assert result["log_count"] > 0
        assert "food_item_count" in result
