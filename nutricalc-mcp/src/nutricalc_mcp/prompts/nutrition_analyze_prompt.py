# src/nutricalc_mcp/prompts/nutrition_analyze_prompt.py
"""营养分析 Prompt 模板

包含:
- NUTRITION_ESTIMATE_PROMPT: 未命中本地库的食物/菜品营养估算 prompt
- MIXED_DISH_DECOMPOSE_PROMPT: 混合菜拆解为食材的 prompt
"""

# 未命中本地库时的营养估算 prompt
NUTRITION_ESTIMATE_PROMPT = """你是一位中餐营养分析师。以下食物未在本地食物成分表中找到精确匹配，请基于食材估算其营养成分（每 {amount_g} g 可食部）。

食物/菜名：{food_name}
类别：{category}
烹饪法：{cooking_method}

本地库中相近的参考食物（可作估算基准）：
{reference_foods}

请按以下 JSON 格式输出（不要输出其他内容）：
{{
    "food_name": "{food_name}",
    "amount_g": {amount_g},
    "nutrition": {{
        "calories_kcal": "能量 kcal",
        "protein_g": "蛋白质 g",
        "fat_g": "脂肪 g",
        "carbohydrate_g": "碳水 g",
        "fiber_g": "膳食纤维 g",
        "calcium_mg": "钙 mg",
        "iron_mg": "铁 mg",
        "sodium_mg": "钠 mg",
        "vitamin_c_mg": "维生素 C mg",
        "vitamin_a_ug": "维生素 A μg"
    }},
    "estimation_basis": "估算依据（参考了哪些食材、烹饪法对油脂/营养流失的调整）",
    "confidence": "估算置信度 0-1",
    "decomposition": [
        {{"ingredient": "食材名", "amount_g": "克数"}}
    ]
}}

估算要点：
- 优先参考本地库相近食物的能量密度（kcal/100g）
- 烹饪法调整：炒/炸油脂 +10-25g，蒸/煮基本不加油，烤流失部分脂肪
- 混合菜按主料占比拆解后分别估算再汇总
- 钠含量：加盐菜品约 300-800mg/100g，少盐 100-300mg
- 置信度 <0.6 时建议在 estimation_basis 中说明并提示用户确认
"""


# 混合菜拆解 prompt（独立定义，避免与 food_recognize_prompt 循环）
MIXED_DISH_DECOMPOSE_PROMPT = """你是一位中餐营养分析师。请将以下混合菜拆解为主要食材，便于查表计算营养。

菜名：{dish_name}
份量：{amount_g} g
烹饪法：{cooking_method}

请按以下 JSON 格式输出（不要输出其他内容）：
{{
    "is_mixed_dish": true/false,
    "decomposition": [
        {{
            "ingredient": "食材标准名（如 猪肉(瘦)/番茄/豆腐/花生油）",
            "amount_g": "该食材在 {amount_g}g 菜中的克数",
            "role": "主料/辅料/调味"
        }}
    ],
    "cooking_method": "烹饪法",
    "oil_estimate_g": "估算用油量（克）",
    "notes": "拆解说明（不同做法油脂差异等）"
}}

拆解要点：
- 主料占比通常 60-80%，辅料 10-20%，调味 5-10%
- 油脂估算：炒菜 10-15g/份，炸 15-25g/份，凉拌 5-8g/份
- 不同地区做法差异大时，notes 中说明
"""
