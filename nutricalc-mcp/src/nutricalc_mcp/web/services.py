# web/services.py
"""Web 服务层 — 编排 tools / storage / statistics / nutritionist

作为路由层和数据层之间的薄编排层，不复制数据访问逻辑。
所有读写都通过 tools 层完成，保持单一数据入口。

对齐 DeepReview web/services.py 的编排模式。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from nutricalc_mcp.tools.crud import (
    get_storage, load_user_profile, save_user_profile,
    save_food_log, query_food_logs, delete_food_log, update_food_log,
)
from nutricalc_mcp.tools.statistics import get_statistics
from nutricalc_mcp.tools.balance_assess import assess_balance
from nutricalc_mcp.tools.nutritionist import nutritionist_advice, interpret_trend
from nutricalc_mcp.tools.export import export_data, export_summary
from nutricalc_mcp.tools.nutrition_analyze import analyze_nutrition
from nutricalc_mcp.knowledge_map import (
    FOOD_CATEGORIES, MEAL_TYPES, COOKING_METHODS,
    ACTIVITY_LEVELS, GENDERS, GOALS, LIFE_STAGES, PERSONAS,
)


# ──────────────────────────────────────────
# Dashboard 概览
# ──────────────────────────────────────────

def get_dashboard_summary() -> dict:
    """获取 Dashboard 概览数据：今日 KPI + 近期记录 + 30天能量趋势 + 雷达图"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    storage = get_storage()

    # 今日记录
    today_logs_data = storage.query_food_logs(filters={"date_range": {"start": today, "end": today}})
    today_logs = today_logs_data["food_logs"]
    today_calories = sum(
        (fl.get("nutrition") or {}).get("calories_kcal", 0) for fl in today_logs
    )

    # 用户档案 + RNI
    profile = load_user_profile("default")
    from nutricalc_mcp.knowledge_map import get_rni
    rni = get_rni(profile.get("gender", "male"), profile.get("life_stage", "成人"))
    target_calories = rni.get("calories_kcal", 2000)

    # 全部记录统计（用于趋势与雷达）
    stats = get_statistics(group_by="date")

    # 最近 7 天记录数
    week_ago = (datetime.now(timezone.utc) - timedelta(days=6)).strftime("%Y-%m-%d")
    week_logs = storage.query_food_logs(filters={"date_range": {"start": week_ago, "end": today}})
    week_log_count = week_logs["total_count"]

    # 待确认记录数（识别/分析后未经用户确认）
    pending_confirm = sum(1 for fl in today_logs if not fl.get("confirmed"))

    return {
        "today_calories": round(today_calories, 1),
        "target_calories": target_calories,
        "calorie_ratio": round(today_calories / target_calories, 3) if target_calories else 0,
        "today_log_count": len(today_logs),
        "week_log_count": week_log_count,
        "pending_confirm": pending_confirm,
        "trends": stats.get("trends", {}),
        "radar_data": stats.get("radar_data", {"indicators": [], "values": []}),
        "summary": stats.get("summary", {}),
        "profile": profile,
        "has_profile": not profile.get("not_found", False),
    }


# ──────────────────────────────────────────
# 饮食记录管理
# ──────────────────────────────────────────

def get_food_logs(filters: Optional[dict] = None) -> dict:
    """查询饮食记录列表"""
    return query_food_logs(filters=filters or {})


def get_log_detail(log_id: str) -> Optional[dict]:
    """获取单条饮食记录详情"""
    storage = get_storage()
    fl = storage.load_food_log(log_id)
    return fl.model_dump(mode="json") if fl else None


def add_food_log(log_data: dict) -> dict:
    """新增饮食记录

    若 items 含 name+amount_g 但无 nutrition，自动调用营养分析填充。
    """
    # 自动营养分析：items 有名称份量但缺营养素时
    items = log_data.get("items", [])
    needs_analysis = any(
        it.get("name") and it.get("amount_g") and not it.get("nutrition")
        for it in items
    )
    if needs_analysis:
        analyze_items = [
            {"name": it["name"], "amount_g": it["amount_g"],
             "cooking_method": it.get("cooking_method"), "category": it.get("category")}
            for it in items if it.get("name") and it.get("amount_g")
        ]
        result = analyze_nutrition(analyze_items)
        # 回填营养素到 items
        analyzed_map = {a.get("name"): a for a in result.get("items", [])}
        for it in items:
            a = analyzed_map.get(it.get("name"))
            if a and a.get("nutrition"):
                it["nutrition"] = a["nutrition"]
                it["food_id"] = a.get("food_id") or it.get("food_id", "")
                if not it.get("category") and a.get("category"):
                    it["category"] = a["category"]
        # 填充整餐汇总营养
        if not log_data.get("nutrition"):
            log_data["nutrition"] = result.get("total_nutrition")

    return save_food_log(log_data)


def remove_food_log(log_id: str) -> dict:
    """删除饮食记录"""
    return delete_food_log(log_id)


def edit_food_log(log_data: dict) -> dict:
    """更新饮食记录"""
    return update_food_log(log_data)


# ──────────────────────────────────────────
# 统计分析
# ──────────────────────────────────────────

def get_stats_by_dimension(group_by: str) -> dict:
    """按维度获取统计"""
    return get_statistics(group_by=group_by)


# ──────────────────────────────────────────
# 营养平衡评估 + AI 营养师
# ──────────────────────────────────────────

def get_balance_assessment(period: str = "daily") -> dict:
    """获取营养平衡评估"""
    return assess_balance(period=period)


def get_nutritionist_advice(period: str = "daily", persona: str = "professional", question: str = "") -> dict:
    """获取 AI 营养师建议"""
    return nutritionist_advice(period=period, persona=persona, question=question)


def get_trend_interpretation(period: str = "weekly") -> dict:
    """获取趋势解读"""
    return interpret_trend(period=period)


# ──────────────────────────────────────────
# 数据导出
# ──────────────────────────────────────────

def get_export_summary(filters: Optional[dict] = None) -> dict:
    """导出预览（统计待导出数据量）"""
    return export_summary(filters=filters)


def do_export(format: str = "json", filters: Optional[dict] = None) -> dict:
    """执行导出"""
    return export_data(format=format, filters=filters)


# ──────────────────────────────────────────
# 用户档案
# ──────────────────────────────────────────

def get_user_profile() -> dict:
    """获取用户档案"""
    return load_user_profile("default")


def set_user_profile(profile_data: dict) -> dict:
    """保存用户档案"""
    return save_user_profile(profile_data)


# ──────────────────────────────────────────
# 选项常量（供表单下拉框）
# ──────────────────────────────────────────

def get_form_options() -> dict:
    """获取所有表单选项常量"""
    return {
        "food_categories": FOOD_CATEGORIES,
        "meal_types": MEAL_TYPES,
        "cooking_methods": COOKING_METHODS,
        "activity_levels": ACTIVITY_LEVELS,
        "genders": GENDERS,
        "goals": GOALS,
        "life_stages": LIFE_STAGES,
        "personas": PERSONAS,
    }
