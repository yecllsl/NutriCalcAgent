# src/nutricalc_mcp/tools/nutritionist.py
"""AI 营养师 Tool

基于近期饮食记录 + 平衡评估 + 用户档案，构造上下文感知的营养师建议 prompt，
供 MCP 宿主 LLM 生成多轮对话式建议。

支持两种模式：
1. 建议模式（无 question）：生成完整个性化建议（总览/发现/推荐/下一餐/目标）
2. 对话模式（有 question）：基于用户具体提问生成自然语言回答

支持三种人设：professional(专业) / gentle(温柔) / strict(严格)

设计对齐 DeepReview tools/improvement.py 的"构造 prompt 交由 LLM 执行"模式：
Tool 不直接调用 LLM，而是返回构造好的 prompt + 结构化上下文数据。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from nutricalc_mcp.models import NutritionFacts, NutritionAdvice
from nutricalc_mcp.knowledge_map import (
    get_rni, NUTRIENT_META, NUTRIENT_NAME_MAP,
    CHRONIC_DISEASE_TIPS, GOALS, GOAL_DESC,
)
from nutricalc_mcp.tools.crud import get_storage, load_user_profile
from nutricalc_mcp.tools.balance_assess import (
    _resolve_date_range, _aggregate_logs, _collect_food_names,
    _compute_diversity_score, _compute_gaps, _compute_balance_score,
    _format_achievement_detail, _format_gaps_detail, _build_radar_data,
)
from nutricalc_mcp.prompts.nutritionist_prompt import (
    get_persona_prompt, NUTRITIONIST_ADVICE_PROMPT, NUTRITIONIST_CHAT_PROMPT,
    NEXT_MEAL_SUGGESTION_PROMPT, TREND_INTERPRETATION_PROMPT,
)


def _goal_description(goal: str) -> str:
    """健康目标 → 中文描述"""
    return GOAL_DESC.get(goal, "维持健康")


def _format_user_profile(profile: dict) -> str:
    """格式化用户档案为可读字符串"""
    gender_cn = "男" if profile.get("gender") == "male" else "女"
    return (
        f"{profile.get('age', 30)}岁/{gender_cn}/"
        f"{profile.get('life_stage', '成人')}/"
        f"身高 {profile.get('height_cm', 170)}cm/"
        f"体重 {profile.get('weight_kg', 65)}kg/"
        f"活动水平 {profile.get('activity_level', '轻度')}"
    )


def _format_recent_logs_summary(logs: list, limit: int = 10) -> str:
    """格式化近期饮食记录摘要（最多 limit 条）"""
    if not logs:
        return "（近期无饮食记录）"

    # 归一化 datetime 时区：无时区的视为 UTC，避免混合比较报错
    def _sort_key(fl):
        mt = fl.meal_time
        if mt is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if mt.tzinfo is None:
            return mt.replace(tzinfo=timezone.utc)
        return mt

    # 按时间倒序取最近 limit 条
    sorted_logs = sorted(logs, key=_sort_key, reverse=True)[:limit]
    lines = []
    for fl in sorted_logs:
        meal_time = fl.meal_time.strftime("%m-%d %H:%M") if fl.meal_time else "未知时间"
        items_str = "、".join(f"{it.name}({it.amount_g}g)" for it in fl.items[:5])
        if len(fl.items) > 5:
            items_str += f"等{len(fl.items)}项"
        n = fl.nutrition
        cal = f"{n.calories_kcal:.0f}kcal" if n else "未分析"
        lines.append(f"- [{meal_time}] {fl.meal_type}：{items_str}（{cal}）")
    return "\n".join(lines)


def _build_todays_intake() -> dict:
    """获取今日已摄入营养汇总 + 食物列表"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    storage = get_storage()
    logs = storage.get_logs_by_date_range(today, today)
    total = _aggregate_logs(logs)
    foods = []
    meals = set()
    for fl in logs:
        meals.add(fl.meal_type)
        for it in fl.items:
            foods.append(it.name)
    return {
        "nutrition": total,
        "foods": foods,
        "meals": sorted(meals),
        "log_count": len(logs),
    }


def _next_meal_type(meals: list[str]) -> str:
    """根据今日已吃的餐次推断下一餐"""
    order = ["早餐", "午餐", "晚餐", "加餐"]
    if not meals:
        # 根据当前时间判断
        hour = datetime.now(timezone.utc).hour
        if hour < 10:
            return "早餐"
        if hour < 14:
            return "午餐"
        if hour < 18:
            return "晚餐"
        return "加餐"
    for m in order[:3]:  # 早餐/午餐/晚餐
        if m not in meals:
            return m
    return "加餐"


def _build_next_meal_prompt(profile: dict, persona: str) -> str:
    """构造下一餐建议 prompt"""
    today = _build_todays_intake()
    nutrition = today["nutrition"]
    rni = get_rni(profile.get("gender", "male"), profile.get("life_stage", "成人"))
    next_meal = _next_meal_type(today["meals"])
    allergies = profile.get("allergies", [])

    return NEXT_MEAL_SUGGESTION_PROMPT.format(
        persona_prompt=get_persona_prompt(persona),
        user_profile=_format_user_profile(profile),
        goal_desc=_goal_description(profile.get("goal", "maintain")),
        today_calories=round(nutrition.calories_kcal, 1),
        target_calories=rni.get("calories_kcal", 2000),
        today_protein=round(nutrition.protein_g, 1),
        target_protein=rni.get("protein_g", 60),
        today_fat=round(nutrition.fat_g, 1),
        today_carb=round(nutrition.carbohydrate_g, 1),
        today_fiber=round(nutrition.fiber_g, 1),
        today_sodium=round(nutrition.sodium_mg, 1),
        today_foods="、".join(today["foods"][:8]) if today["foods"] else "（暂无）",
        today_meals="、".join(today["meals"]) if today["meals"] else "（暂无）",
        next_meal_type=next_meal,
        allergies="、".join(allergies) if allergies else "无",
    )


def _build_advice_prompt(
    profile: dict,
    persona: str,
    period: str,
    start: str,
    end: str,
    days: int,
    avg_nutrition: NutritionFacts,
    achievement: dict[str, float],
    gaps: list[dict],
    balance_score: float,
    diversity_score: float,
    food_variety_count: int,
    logs: list,
) -> str:
    """构造完整个性化建议 prompt"""
    rni = get_rni(profile.get("gender", "male"), profile.get("life_stage", "成人"))
    goal = profile.get("goal", "maintain")

    # 慢病/特殊人群膳食要点
    chronic_tips = ""
    if goal in CHRONIC_DISEASE_TIPS:
        chronic_tips = "对应人群膳食要点：\n" + "\n".join(
            f"- {t}" for t in CHRONIC_DISEASE_TIPS[goal]
        )

    period_desc = {"daily": "今日", "weekly": "本周", "monthly": "本月"}.get(period, "本周期")

    return NUTRITIONIST_ADVICE_PROMPT.format(
        persona_prompt=get_persona_prompt(persona),
        user_profile=_format_user_profile(profile),
        goal_desc=_goal_description(goal),
        allergies="、".join(profile.get("allergies", [])) or "无",
        period_desc=period_desc,
        start_date=start,
        end_date=end,
        days=days,
        balance_score=balance_score,
        diversity_score=diversity_score,
        food_variety_count=food_variety_count,
        avg_calories=round(avg_nutrition.calories_kcal, 1),
        target_calories=rni.get("calories_kcal", 2000),
        achievement_detail=_format_achievement_detail(achievement),
        gaps_detail=_format_gaps_detail(gaps),
        recent_logs_summary=_format_recent_logs_summary(logs),
        chronic_tips=chronic_tips,
    )


def _build_chat_prompt(
    profile: dict,
    persona: str,
    period: str,
    start: str,
    end: str,
    achievement: dict[str, float],
    gaps: list[dict],
    balance_score: float,
    diversity_score: float,
    logs: list,
    question: str,
) -> str:
    """构造多轮对话问答 prompt"""
    # 提取 top 缺口与过量
    deficient = [g for g in gaps if g["status"] == "deficient"][:3]
    excessive = [g for g in gaps if g["status"] == "excessive"][:3]
    top_gaps = "、".join(f"{g['nutrient']}({g['ratio']*100:.0f}%)" for g in deficient) or "无显著缺口"
    top_excess = "、".join(f"{g['nutrient']}({g['ratio']*100:.0f}%)" for g in excessive) or "无显著过量"
    period_desc = {"daily": "今日", "weekly": "本周", "monthly": "本月"}.get(period, "本周期")

    return NUTRITIONIST_CHAT_PROMPT.format(
        persona_prompt=get_persona_prompt(persona),
        user_profile=_format_user_profile(profile),
        goal_desc=_goal_description(profile.get("goal", "maintain")),
        period_desc=period_desc,
        balance_score=balance_score,
        diversity_score=diversity_score,
        top_gaps=top_gaps,
        top_excess=top_excess,
        recent_logs_summary=_format_recent_logs_summary(logs),
        question=question,
    )


def nutritionist_advice(
    period: str = "daily",
    persona: str = "professional",
    question: str = "",
) -> dict:
    """AI 营养师建议主入口

    Args:
        period: 评估周期 daily/weekly/monthly
        persona: 人设 professional(专业) / gentle(温柔) / strict(严格)
        question: 用户具体提问（非空时进入对话模式，空时生成完整建议）

    Returns:
        {
            mode: "advice" | "chat",
            persona: 实际人设,
            period: 评估周期,
            advice_prompt: 建议/对话 prompt（供 LLM 执行）,
            next_meal_prompt: 下一餐建议 prompt（仅 advice 模式 + daily）,
            context: 结构化上下文（平衡评分/缺口/雷达图等）,
            advice_id: 建议ID,
        }
    """
    # 校验人设
    if persona not in ("professional", "gentle", "strict"):
        persona = "professional"

    # 解析日期范围
    start, end, days = _resolve_date_range(period, "", "")

    # 加载饮食记录
    storage = get_storage()
    logs = storage.get_logs_by_date_range(start, end)

    # 聚合营养
    total_nutrition = _aggregate_logs(logs)
    avg_nutrition = total_nutrition.scale(1.0 / days) if days > 0 else total_nutrition

    # 加载用户档案 → RNI
    profile = load_user_profile("default")
    rni = get_rni(profile.get("gender", "male"), profile.get("life_stage", "成人"))

    # 计算达成率与缺口
    gaps, achievement = _compute_gaps(avg_nutrition, rni)
    balance_score = _compute_balance_score(achievement)
    food_names = _collect_food_names(logs)
    diversity_score = _compute_diversity_score(food_names)

    # 生成建议ID
    advice_id = f"ad_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    # 构造 prompt
    mode = "chat" if question.strip() else "advice"

    if mode == "chat":
        prompt = _build_chat_prompt(
            profile, persona, period, start, end,
            achievement, gaps, balance_score, diversity_score,
            logs, question.strip(),
        )
    else:
        prompt = _build_advice_prompt(
            profile, persona, period, start, end, days,
            avg_nutrition, achievement, gaps, balance_score,
            diversity_score, len(food_names), logs,
        )

    # 构造返回上下文
    context = {
        "balance_score": balance_score,
        "diversity_score": diversity_score,
        "food_variety_count": len(food_names),
        "avg_daily_calories": round(avg_nutrition.calories_kcal, 1),
        "target_calories": rni.get("calories_kcal", 2000),
        "top_gaps": [
            {"nutrient": g["nutrient"], "status": g["status"], "ratio": g["ratio"]}
            for g in gaps[:5]
        ],
        "radar_data": _build_radar_data(achievement),
        "log_count": len(logs),
        "days": days,
        "date_range": {"start": start, "end": end},
    }

    result = {
        "mode": mode,
        "persona": persona,
        "period": period,
        "advice_id": advice_id,
        "advice_prompt": prompt,
        "context": context,
        "user_profile": _format_user_profile(profile),
        "goal_desc": _goal_description(profile.get("goal", "maintain")),
    }

    # 建议模式 + daily：附加下一餐建议 prompt
    if mode == "advice" and period == "daily":
        result["next_meal_prompt"] = _build_next_meal_prompt(profile, persona)

    return result


def interpret_trend(period: str = "weekly") -> dict:
    """生成趋势解读 prompt（供 LLM 生成自然语言趋势解读）

    Args:
        period: weekly/monthly

    Returns:
        { trend_prompt, energy_trend, nutrient_trends }
    """
    start, end, days = _resolve_date_range(period, "", "")
    storage = get_storage()
    logs = storage.get_logs_by_date_range(start, end)

    # 按日聚合能量
    from collections import defaultdict
    energy_by_date = defaultdict(float)
    for fl in logs:
        if fl.meal_time:
            d = fl.meal_time.strftime("%Y-%m-%d")
            n = fl.nutrition or NutritionFacts()
            energy_by_date[d] += n.calories_kcal
    energy_trend = "\n".join(
        f"- {d}: {round(v, 0)} kcal" for d, v in sorted(energy_by_date.items())
    ) or "（无数据）"

    # 关键营养素日均达成率趋势
    profile = load_user_profile("default")
    rni = get_rni(profile.get("gender", "male"), profile.get("life_stage", "成人"))
    total = _aggregate_logs(logs)
    avg = total.scale(1.0 / days) if days > 0 else total
    nutrient_trends = []
    for meta in NUTRIENT_META:
        key = meta["key"]
        target = rni.get(key, 0)
        actual = getattr(avg, key, 0) or 0
        ratio = round(actual / target * 100, 1) if target > 0 else 0
        nutrient_trends.append(f"- {meta['name']}: {ratio}%")
    nutrient_trends_str = "\n".join(nutrient_trends)

    diversity = _compute_diversity_score(_collect_food_names(logs))
    diversity_trend = f"多样性评分：{diversity}/100"

    period_desc = {"weekly": "本周", "monthly": "本月"}.get(period, "本周期")
    trend_prompt = TREND_INTERPRETATION_PROMPT.format(
        persona_prompt=get_persona_prompt("professional"),
        period_desc=period_desc,
        start_date=start,
        end_date=end,
        energy_trend=energy_trend,
        nutrient_trends=nutrient_trends_str,
        diversity_trend=diversity_trend,
    )

    return {
        "trend_prompt": trend_prompt,
        "energy_trend": dict(energy_by_date),
        "period": period,
        "date_range": {"start": start, "end": end},
    }
