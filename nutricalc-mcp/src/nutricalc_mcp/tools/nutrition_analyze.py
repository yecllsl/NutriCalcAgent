# src/nutricalc_mcp/tools/nutrition_analyze.py
"""营养成分分析 Tool

对一组食物项（name + amount_g + 可选 cooking_method）执行营养分析：
1. 优先本地食物成分表查表（精确/模糊匹配）
2. 命中：按 amount_g 缩放营养素
3. 未命中：返回估算 prompt + 混合菜拆解 prompt，供 LLM 基于食材估算
4. 累加所有项 → 汇总 NutritionFacts

对齐 DeepReview tools/analyze.py 的"构造上下文 prompt 交由 LLM 执行"模式。
"""
from __future__ import annotations

from typing import Optional

from nutricalc_mcp.food_db import get_food_db
from nutricalc_mcp.models import NutritionFacts
from nutricalc_mcp.knowledge_map import NUTRIENT_NAME_MAP
from nutricalc_mcp.prompts.nutrition_analyze_prompt import (
    NUTRITION_ESTIMATE_PROMPT, MIXED_DISH_DECOMPOSE_PROMPT, NUTRITION_SUMMARY_PROMPT,
)


def _analyze_single_item(item: dict) -> dict:
    """分析单个食物项

    Returns:
        {
            food_id, name, category, amount_g, cooking_method,
            nutrition: NutritionFacts dict | None,
            source: "db" | "unmatched",
            match_type: "exact" | "partial" | None,
            decompose_prompt: str (仅 unmatched),
            estimate_prompt: str (仅 unmatched)
        }
    """
    name = item.get("name", "").strip()
    amount_g = float(item.get("amount_g", 0) or 0)
    cooking = item.get("cooking_method") or "未知"
    category = item.get("category", "")

    if not name or amount_g <= 0:
        return {
            "name": name, "amount_g": amount_g, "source": "invalid",
            "error": "缺少食物名称或份量",
        }

    db = get_food_db()
    results = db.search(name, limit=1)

    if results:
        r = results[0]
        factor = amount_g / 100.0
        nutrition = r["nutrition"].scale(factor)
        return {
            "food_id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "amount_g": amount_g,
            "cooking_method": cooking,
            "nutrition": nutrition.model_dump(),
            "source": "db",
            "match_type": r.get("match_type", "partial"),
        }

    # 未命中：生成拆解 + 估算 prompt
    # 取本地库中类别相近的食物作参考
    ref_hint = "（无相近参考）"
    if category:
        refs = db.query_by_category(category, limit=3)
        if refs:
            ref_hint = "\n".join(
                f"- {r['name']}（{r['nutrition'].calories_kcal} kcal/100g）"
                for r in refs
            )
    else:
        # 用名称关键词再搜一次更宽松的参考
        refs = db.search(name[:2] if len(name) >= 2 else name, limit=3)
        if refs:
            ref_hint = "\n".join(
                f"- {r['name']}（{r['nutrition'].calories_kcal} kcal/100g）"
                for r in refs
            )

    decompose_prompt = MIXED_DISH_DECOMPOSE_PROMPT.format(
        dish_name=name, amount_g=amount_g, cooking_method=cooking,
    )
    estimate_prompt = NUTRITION_ESTIMATE_PROMPT.format(
        food_name=name, amount_g=amount_g, category=category or "未知",
        cooking_method=cooking, reference_foods=ref_hint,
    )
    return {
        "food_id": None,
        "name": name,
        "category": category,
        "amount_g": amount_g,
        "cooking_method": cooking,
        "nutrition": None,
        "source": "unmatched",
        "decompose_prompt": decompose_prompt,
        "estimate_prompt": estimate_prompt,
    }


def _aggregate_nutrition(items: list[dict]) -> dict:
    """累加所有已分析项的营养素（仅 source=db 或已有 nutrition 的项）"""
    total = NutritionFacts()
    valid_count = 0
    for it in items:
        n = it.get("nutrition")
        if n:
            total = total.add(NutritionFacts(**n))
            valid_count += 1
    return {"nutrition": total.model_dump(), "valid_item_count": valid_count}


def analyze_nutrition(items: list[dict]) -> dict:
    """营养分析主入口

    Args:
        items: 食物项列表，每项 {name, amount_g, cooking_method?, category?}

    Returns:
        {
            items: 每项分析结果列表,
            total_nutrition: 汇总营养 NutritionFacts,
            matched_count: 本地库命中数,
            unmatched_count: 未命中数,
            unmatched_items: 未命中项名称列表,
            summary_prompt: 整餐汇总解读 prompt（可选，需 meal_type/meal_time）,
            needs_llm: 是否需要 LLM 介入（有未命中项）
        }
    """
    if not items:
        return {
            "items": [],
            "total_nutrition": NutritionFacts().model_dump(),
            "matched_count": 0,
            "unmatched_count": 0,
            "needs_llm": False,
            "error": "未提供食物项",
        }

    analyzed = [_analyze_single_item(it) for it in items]
    matched = [a for a in analyzed if a.get("source") == "db"]
    unmatched = [a for a in analyzed if a.get("source") == "unmatched"]
    agg = _aggregate_nutrition(analyzed)

    result = {
        "items": analyzed,
        "total_nutrition": agg["nutrition"],
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "unmatched_items": [a["name"] for a in unmatched],
        "valid_item_count": agg["valid_item_count"],
        "needs_llm": len(unmatched) > 0,
    }

    # 若有未命中项，提供合并的估算 prompt 供 LLM 一次性处理
    if unmatched:
        result["estimate_prompts"] = [a["estimate_prompt"] for a in unmatched]
        result["decompose_prompts"] = [a["decompose_prompt"] for a in unmatched]

    return result


def build_summary_prompt(
    total_nutrition: dict,
    meal_type: str = "加餐",
    meal_time: str = "",
    target_calories: float = 700,
    target_protein: float = 22,
) -> str:
    """构建整餐营养汇总解读 prompt（供 LLM 解读汇总数据）

    Args:
        total_nutrition: analyze_nutrition 返回的 total_nutrition
        meal_type: 餐次
        meal_time: 进食时间
        target_calories: 该餐次能量目标（RNI/3 简化）
        target_protein: 该餐次蛋白目标

    Returns:
        summary_prompt 字符串
    """
    n = total_nutrition
    return NUTRITION_SUMMARY_PROMPT.format(
        meal_type=meal_type,
        meal_time=meal_time or "未指定",
        item_count=n.get("item_count", 0),
        calories=round(n.get("calories_kcal", 0), 1),
        protein=round(n.get("protein_g", 0), 1),
        fat=round(n.get("fat_g", 0), 1),
        carb=round(n.get("carbohydrate_g", 0), 1),
        fiber=round(n.get("fiber_g", 0), 1),
        sodium=round(n.get("sodium_mg", 0), 1),
        target_calories=round(target_calories, 0),
        target_protein=round(target_protein, 1),
    )
