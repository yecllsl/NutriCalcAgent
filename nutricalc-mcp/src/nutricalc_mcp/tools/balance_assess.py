# src/nutricalc_mcp/tools/balance_assess.py
"""营养平衡评估 Tool

基于日/周/月时序聚合饮食记录，计算:
- 总摄入 / 日均摄入
- 对 RNI（推荐摄入量）的达成率
- 平衡评分（0-100）
- 营养缺口（<80% RNI）/ 过量（钠/胆固醇 >150%）
- 饮食多样性评分（食物种类数）
- 结构化规则建议
- 评估 prompt（供 LLM 生成个性化建议）

对齐 DeepReview tools/analyze.py 的"构造上下文 prompt 交由 LLM 执行"模式。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from nutricalc_mcp.models import NutritionFacts, NutrientGap, BalanceAssessment
from nutricalc_mcp.knowledge_map import (
    get_rni, NUTRIENT_META, NUTRIENT_NAME_MAP, NUTRIENT_UNIT_MAP,
    GAP_THRESHOLDS, EXCESSIVE_NUTRIENTS, RADAR_NUTRIENTS,
    CHRONIC_DISEASE_TIPS, DIETARY_GUIDELINES,
)
from nutricalc_mcp.tools.crud import get_storage, load_user_profile
from nutricalc_mcp.prompts.balance_assess_prompt import BALANCE_ADVICE_PROMPT


def _resolve_date_range(period: str, start_date: str, end_date: str) -> tuple[str, str, int]:
    """解析评估周期为 (start, end, days)

    period: daily(当天) / weekly(最近7天) / monthly(最近30天)
    若提供 start_date/end_date 则优先使用。
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if start_date and end_date:
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        days = (d2 - d1).days + 1
        return start_date, end_date, max(days, 1)

    if period == "daily":
        return today, today, 1
    if period == "weekly":
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=6)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), 7
    if period == "monthly":
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=29)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), 30
    # 默认按日
    return today, today, 1


def _aggregate_logs(logs: list) -> NutritionFacts:
    """累加一组 FoodLog 的所有食物项营养（已按份量计算）"""
    total = NutritionFacts()
    for fl in logs:
        # 优先用 FoodLog 汇总 nutrition；否则累加 items
        if fl.nutrition:
            total = total.add(fl.nutrition)
            continue
        for item in fl.items:
            if item.nutrition:
                total = total.add(item.nutrition)
    return total


def _collect_food_names(logs: list) -> set[str]:
    """收集所有食物名称（用于多样性评分）"""
    names = set()
    for fl in logs:
        for item in fl.items:
            names.add(item.name)
    return names


def _compute_diversity_score(food_names: set[str]) -> float:
    """饮食多样性评分（基于食物种类数）

    参考《中国居民膳食指南》每天 12 种、每周 25 种：
    - 每天 12+ 种 = 100 分
    - 每周 25+ 种 = 100 分
    - 按比例折算，上限 100
    """
    if not food_names:
        return 0.0
    target = 12  # 简化：按日 12 种目标
    score = min(100.0, len(food_names) / target * 100)
    return round(score, 1)


def _compute_gaps(
    avg_nutrition: NutritionFacts,
    rni: dict[str, float],
) -> tuple[list[dict], dict[str, float]]:
    """计算各营养素达成率与缺口/过量

    Returns:
        (gaps 清单, rni_achievement 达成率字典)
    """
    gaps: list[dict] = []
    achievement: dict[str, float] = {}
    deficient_thr = GAP_THRESHOLDS["deficient"]
    excessive_thr = GAP_THRESHOLDS["excessive"]

    for meta in NUTRIENT_META:
        key = meta["key"]
        target = rni.get(key, 0)
        if target <= 0:
            continue
        actual = getattr(avg_nutrition, key, 0) or 0
        ratio = round(actual / target, 3)
        achievement[key] = ratio

        status = "adequate"
        if key in EXCESSIVE_NUTRIENTS:
            # 钠/胆固醇：低于 deficient 阈值或高于 excessive 阈值都算问题
            if ratio < deficient_thr:
                status = "deficient"
            elif ratio > excessive_thr:
                status = "excessive"
        else:
            if ratio < deficient_thr:
                status = "deficient"
            # 非监控营养素不算过量（如蛋白高摄入一般可接受）

        if status != "adequate":
            gaps.append({
                "nutrient": meta["name"],
                "nutrient_key": key,
                "status": status,
                "actual": round(actual, 2),
                "target": round(target, 2),
                "ratio": ratio,
                "unit": meta["unit"],
            })

    # 按问题严重度排序：不足按 ratio 升序，过量按 ratio 降序
    gaps.sort(key=lambda g: (g["status"] != "deficient", g["ratio"] if g["status"] == "deficient" else -g["ratio"]))
    return gaps, achievement


def _compute_balance_score(achievement: dict[str, float]) -> float:
    """平衡评分（0-100）

    评分逻辑：
    - 对每个参与评分的营养素，达成率在 [0.8, 1.5] 区间得满分
    - 不足（<0.8）：按 ratio/0.8 折算
    - 过量（>1.5，仅监控营养素）：按 1.5/ratio 折算
    - 平衡评分 = 平均得分 × 100
    """
    scores = []
    for meta in NUTRIENT_META:
        if not meta["score"]:
            continue
        ratio = achievement.get(meta["key"])
        if ratio is None:
            continue
        if ratio < 0.8:
            scores.append(ratio / 0.8)
        elif ratio > 1.5 and meta["key"] in EXCESSIVE_NUTRIENTS:
            scores.append(1.5 / ratio)
        else:
            scores.append(1.0)
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores) * 100, 1)


def _build_rule_recommendations(
    gaps: list[dict],
    diversity_score: float,
    goal: str,
) -> list[str]:
    """基于规则生成结构化建议（非 LLM）"""
    recs: list[str] = []
    deficient = [g for g in gaps if g["status"] == "deficient"]
    excessive = [g for g in gaps if g["status"] == "excessive"]

    for g in deficient[:5]:
        recs.append(
            f"{g['nutrient']}摄入不足（达成率 {g['ratio']*100:.0f}%），"
            f"建议增加富含{g['nutrient']}的食物"
        )
    for g in excessive[:3]:
        recs.append(
            f"{g['nutrient']}摄入过量（达成率 {g['ratio']*100:.0f}%），"
            f"建议控制{g['nutrient']}摄入"
        )

    if diversity_score < 60:
        recs.append(f"饮食多样性偏低（{diversity_score}/100），建议每日食物种类达到 12 种以上")

    # 叠加膳食指南核心准则
    recs.extend(DIETARY_GUIDELINES[:3])

    # 慢病/特殊人群建议
    if goal in CHRONIC_DISEASE_TIPS:
        recs.extend(CHRONIC_DISEASE_TIPS[goal][:2])

    return recs


def _format_achievement_detail(achievement: dict[str, float]) -> str:
    """格式化达成率明细用于 prompt"""
    lines = []
    for meta in NUTRIENT_META:
        ratio = achievement.get(meta["key"])
        if ratio is None:
            continue
        status = "✓达标" if 0.8 <= ratio <= 1.5 else (
            "✗不足" if ratio < 0.8 else "▲过量"
        )
        lines.append(
            f"- {meta['name']}：达成率 {ratio*100:.0f}% {status}"
        )
    return "\n".join(lines)


def _format_gaps_detail(gaps: list[dict]) -> str:
    """格式化缺口明细用于 prompt"""
    if not gaps:
        return "（无显著缺口或过量）"
    lines = []
    for g in gaps:
        lines.append(
            f"- {g['nutrient']}（{g['status']}）：实际 {g['actual']}{g['unit']} / "
            f"目标 {g['target']}{g['unit']}，达成率 {g['ratio']*100:.0f}%"
        )
    return "\n".join(lines)


def assess_balance(period: str = "daily", start_date: str = "", end_date: str = "") -> dict:
    """营养平衡评估主入口

    Args:
        period: daily/weekly/monthly
        start_date: 起始日期 YYYY-MM-DD（可选，覆盖 period 默认范围）
        end_date: 结束日期 YYYY-MM-DD（可选）

    Returns:
        BalanceAssessment 字典 + assessment_prompt（供 LLM 生成个性化建议）
    """
    # 解析日期范围
    start, end, days = _resolve_date_range(period, start_date, end_date)

    # 加载饮食记录
    storage = get_storage()
    logs = storage.get_logs_by_date_range(start, end)

    # 聚合营养
    total_nutrition = _aggregate_logs(logs)
    avg_nutrition = total_nutrition.scale(1.0 / days) if days > 0 else total_nutrition

    # 加载用户档案 → RNI
    profile_data = load_user_profile("default")
    rni = get_rni(profile_data.get("gender", "male"), profile_data.get("life_stage", "成人"))

    # 计算达成率与缺口
    gaps, achievement = _compute_gaps(avg_nutrition, rni)
    balance_score = _compute_balance_score(achievement)

    # 多样性评分
    food_names = _collect_food_names(logs)
    diversity_score = _compute_diversity_score(food_names)

    # 规则建议
    goal = profile_data.get("goal", "maintain")
    recommendations = _build_rule_recommendations(gaps, diversity_score, goal)

    # 构造评估结果
    assessment_id = f"as_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    assessment = BalanceAssessment(
        assessment_id=assessment_id,
        period=period,
        start_date=start,
        end_date=end,
        days=days,
        total_nutrition=total_nutrition,
        avg_daily_nutrition=avg_nutrition,
        rni_achievement=achievement,
        balance_score=balance_score,
        gaps=[NutrientGap(**g) for g in gaps],
        diversity_score=diversity_score,
        recommendations=recommendations,
    )

    # 保存评估报告
    storage.save_assessment(assessment)

    # 构造 LLM 评估 prompt
    chronic_tips = ""
    if goal in CHRONIC_DISEASE_TIPS:
        chronic_tips = "对应人群膳食要点：\n" + "\n".join(
            f"- {t}" for t in CHRONIC_DISEASE_TIPS[goal]
        )

    assessment_prompt = BALANCE_ADVICE_PROMPT.format(
        period=period,
        start_date=start,
        end_date=end,
        days=days,
        user_profile=f"{profile_data.get('gender','male')}/{profile_data.get('age',30)}岁/{profile_data.get('life_stage','成人')}",
        goal=goal,
        achievement_detail=_format_achievement_detail(achievement),
        gaps_detail=_format_gaps_detail(gaps),
        diversity_score=diversity_score,
        balance_score=balance_score,
        chronic_tips=chronic_tips,
    )

    return {
        "assessment": assessment.model_dump(),
        "assessment_prompt": assessment_prompt,
        "radar_data": _build_radar_data(achievement),
        "food_variety_count": len(food_names),
    }


def _build_radar_data(achievement: dict[str, float]) -> dict:
    """构建 ECharts 雷达图数据（10 个核心营养素达成率%）"""
    indicators = []
    values = []
    for key in RADAR_NUTRIENTS:
        name = NUTRIENT_NAME_MAP.get(key, key)
        ratio = achievement.get(key, 0)
        indicators.append({"name": name, "max": 150})  # 雷达图上限 150%
        values.append(round(ratio * 100, 1))
    return {"indicators": indicators, "values": values}
