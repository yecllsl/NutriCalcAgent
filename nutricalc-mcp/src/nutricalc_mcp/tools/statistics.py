# src/nutricalc_mcp/tools/statistics.py
"""统计查询 Tool

提供多维度饮食统计，支持按日期/餐次/食物类别/营养素分组统计，
返回 30 天能量趋势 + 营养雷达图数据，供 Web 可视化与 MCP 客户端调用。

对齐 DeepReview tools/statistics.py 的 Counter 分组 + 30 天趋势模式。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

from nutricalc_mcp.tools.crud import get_storage, load_user_profile
from nutricalc_mcp.knowledge_map import (
    NUTRIENT_META, NUTRIENT_NAME_MAP, RADAR_NUTRIENTS, get_rni,
)
from nutricalc_mcp.models import NutritionFacts


def _log_nutrition(fl) -> NutritionFacts:
    """从 FoodLog 提取营养（优先汇总 nutrition，否则累加 items）"""
    if fl.nutrition:
        return fl.nutrition
    total = NutritionFacts()
    for item in fl.items:
        if item.nutrition:
            total = total.add(item.nutrition)
    return total


def get_statistics(group_by: str) -> dict:
    """按指定维度统计饮食分布

    Args:
        group_by: 分组维度，支持 date/meal_type/category/nutrient

    Returns:
        {
            items: 分组统计列表,
            total: 总记录数,
            trends: 30 天能量趋势 {date: calories},
            radar_data: 营养雷达图数据,
            summary: 总览统计
        }
    """
    storage = get_storage()
    logs = storage.get_all_logs_for_statistics()

    if not logs:
        return {
            "items": [],
            "total": 0,
            "trends": {},
            "radar_data": {"indicators": [], "values": []},
            "summary": {"total_calories": 0, "avg_daily_calories": 0, "log_count": 0},
        }

    # ── 按维度分组统计 ──
    if group_by == "date":
        counter = Counter()
        calories_by_date = defaultdict(float)
        for fl in logs:
            date = fl.meal_time.strftime("%Y-%m-%d") if fl.meal_time else "未知"
            counter[date] += 1
            calories_by_date[date] += _log_nutrition(fl).calories_kcal
        items = [
            {"name": d, "count": c, "calories": round(calories_by_date[d], 1)}
            for d, c in sorted(counter.items())
        ]

    elif group_by == "meal_type":
        counter = Counter()
        calories_by_meal = defaultdict(float)
        for fl in logs:
            counter[fl.meal_type] += 1
            calories_by_meal[fl.meal_type] += _log_nutrition(fl).calories_kcal
        items = [
            {"name": mt, "count": c, "calories": round(calories_by_meal[mt], 1)}
            for mt, c in counter.most_common()
        ]

    elif group_by == "category":
        counter = Counter()
        calories_by_cat = defaultdict(float)
        for fl in logs:
            for item in fl.items:
                counter[item.category] += 1
                # 类别能量：按 item.nutrition 累加，无则跳过
                if item.nutrition:
                    calories_by_cat[item.category] += item.nutrition.calories_kcal
        items = [
            {"name": cat, "count": c, "calories": round(calories_by_cat[cat], 1)}
            for cat, c in counter.most_common()
        ]

    elif group_by == "nutrient":
        # 按营养素汇总总摄入 + 对 RNI 达成率
        profile = load_user_profile("default")
        rni = get_rni(profile.get("gender", "male"), profile.get("life_stage", "成人"))
        total = NutritionFacts()
        for fl in logs:
            total = total.add(_log_nutrition(fl))
        items = []
        for meta in NUTRIENT_META:
            key = meta["key"]
            actual = getattr(total, key, 0) or 0
            target = rni.get(key, 0)
            ratio = round(actual / target, 3) if target > 0 else 0
            items.append({
                "name": meta["name"],
                "key": key,
                "total": round(actual, 2),
                "unit": meta["unit"],
                "rni": round(target, 2),
                "achievement_ratio": ratio,
            })
        # 按达成率升序（最缺的在前）
        items.sort(key=lambda x: x["achievement_ratio"])

    else:
        items = [{"name": "未知维度", "count": 0}]

    # ── 30 天能量趋势 ──
    trend_counter = defaultdict(float)
    for fl in logs:
        if fl.meal_time:
            date = fl.meal_time.strftime("%Y-%m-%d")
            trend_counter[date] += _log_nutrition(fl).calories_kcal
    trends = {}
    for i in range(30):
        day = (datetime.now(timezone.utc) - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        trends[day] = round(trend_counter.get(day, 0), 1)

    # ── 营养雷达图数据（按日均摄入对 RNI 达成率）──
    radar_data = _build_radar_data(logs)

    # ── 总览统计 ──
    total_calories = sum(_log_nutrition(fl).calories_kcal for fl in logs)
    # 日均：取有记录的日期数
    dates_with_logs = {fl.meal_time.strftime("%Y-%m-%d") for fl in logs if fl.meal_time}
    avg_daily = total_calories / len(dates_with_logs) if dates_with_logs else 0
    summary = {
        "total_calories": round(total_calories, 1),
        "avg_daily_calories": round(avg_daily, 1),
        "log_count": len(logs),
        "date_count": len(dates_with_logs),
        "food_variety": len({item.name for fl in logs for item in fl.items}),
    }

    return {
        "items": items,
        "total": len(logs),
        "trends": trends,
        "radar_data": radar_data,
        "summary": summary,
    }


def _build_radar_data(logs: list) -> dict:
    """构建营养雷达图数据（日均摄入对 RNI 达成率%）"""
    if not logs:
        return {"indicators": [], "values": []}
    profile = load_user_profile("default")
    rni = get_rni(profile.get("gender", "male"), profile.get("life_stage", "成人"))
    total = NutritionFacts()
    for fl in logs:
        total = total.add(_log_nutrition(fl))
    dates_with_logs = {fl.meal_time.strftime("%Y-%m-%d") for fl in logs if fl.meal_time}
    days = len(dates_with_logs) if dates_with_logs else 1
    avg = total.scale(1.0 / days)

    indicators = []
    values = []
    for key in RADAR_NUTRIENTS:
        name = NUTRIENT_NAME_MAP.get(key, key)
        target = rni.get(key, 0)
        actual = getattr(avg, key, 0) or 0
        ratio = (actual / target) if target > 0 else 0
        indicators.append({"name": name, "max": 150})
        values.append(round(ratio * 100, 1))
    return {"indicators": indicators, "values": values}
