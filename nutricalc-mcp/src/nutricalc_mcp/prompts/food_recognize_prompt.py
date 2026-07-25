# src/nutricalc_mcp/prompts/food_recognize_prompt.py
"""食物识别 Prompt 模板

包含:
- FOOD_VISION_PROMPT: 视觉识别 prompt，供多模态 LLM 看图识别菜品/食材/份量/烹饪法
- NUTRITION_LABEL_OCR_PROMPT: 营养标签/菜单 OCR 结构化 prompt
- CLARIFICATION_PROMPT: 澄清提问模板，向用户确认不确定信息
"""

# 视觉识别 prompt：让多模态 LLM 看图识别图中所有食物
FOOD_VISION_PROMPT = """你是一位资深中餐营养分析师。请观察用户上传的食物照片，识别图中的所有菜品/食物。

{context_hint}

请对图中每一道食物/菜品输出以下结构化信息（JSON 数组，不要输出其他内容）：
[
    {{
        "name": "食物/菜名（中文，优先使用常见标准名，如 番茄炒蛋/米饭/红烧肉）",
        "estimated_amount_g": "估算份量（克，整数）",
        "main_ingredients": ["主要食材1", "主要食材2"],
        "cooking_method": "烹饪法（蒸/煮/炒/炸/烤/炖/凉拌/生食/卤/煎/未知）",
        "confidence": "识别置信度 0-1（1 为非常确定）",
        "visible_evidence": "识别依据简述（颜色/形状/食材可见特征）"
    }}
]

识别要点：
- 优先识别常见中餐菜品名，避免生僻译名
- 一道菜若含多种食材，按主食食材命名（如"番茄炒蛋"而非"鸡蛋番茄混合"）
- 份量按常见一份估算（如一碗米饭约200g，一盘炒菜约250-300g）
- 多道菜请全部识别，不要遗漏
- 若图中存在餐具/参考物，可辅助份量估算
- 若图片模糊或无法识别，confidence 设为 <0.5 并在 visible_evidence 说明

本地食物库已提供的候选匹配（优先采用这些标准名）：
{candidates_hint}
"""


# 营养标签 / 菜单 OCR 结构化 prompt
NUTRITION_LABEL_OCR_PROMPT = """你是一位食品营养标签解析专家。以下是 OCR 识别到的文字（可能来自包装食品营养标签或餐厅菜单）。

OCR 原始文字：
{raw_text}

请按以下 JSON 格式输出结构化结果（不要输出其他内容）：
{{
    "source_type": "label(营养标签) / menu(菜单) / recipe(食谱) / unknown",
    "food_name": "食物名称（若可识别）",
    "items": [
        {{
            "name": "食物/菜品名",
            "amount_g": "份量（克，若标签标明每份含量则取该值，否则按 100g）",
            "nutrition": {{
                "calories_kcal": "能量",
                "protein_g": "蛋白质",
                "fat_g": "脂肪",
                "carbohydrate_g": "碳水化合物",
                "sodium_mg": "钠",
                "calcium_mg": "钙"
            }}
        }}
    ],
    "ambiguous_fields": ["无法确定的字段列表"]
}}

解析要点：
- 营养标签通常标注"每100g"或"每份"，注意单位换算
- 菜单通常只有菜名，份量与营养需结合本地库或估算
- OCR 文字可能有错字，结合上下文修正（如"蛋自质"→"蛋白质"）
"""


# 澄清提问模板：当识别置信度低或份量不确定时，生成向用户的提问
CLARIFICATION_PROMPT = """基于初步识别结果，以下信息需要用户确认以提升营养分析准确度。
请以友好、简洁的中文向用户提问，每次最多 3 个问题。

初步识别结果：
{preliminary_result}

需要澄清的方面（按需选择）：
1. **菜名确认**：当某道菜 confidence < 0.7 或可能有歧义时
   - 例：「第 2 道菜看起来像红烧肉，是红烧肉还是糖醋排骨？」
2. **份量确认**：当估算份量波动较大时
   - 例：「这碗米饭大约是多少克？（小碗约150g / 中碗约200g / 大碗约250g）」
3. **烹饪法确认**：影响油脂摄入估算
   - 例：「这道青菜是清炒还是凉拌？放油多吗？」
4. **食材调整**：当识别的食材可能不全时
   - 例：「这道菜里还有其他主要食材吗？」
5. **特殊说明**：低盐/少油/无糖等烹调偏好

输出格式（JSON）：
{{
    "questions": [
        {{
            "target_food": "针对哪道菜",
            "field": "name/amount/cooking/ingredients/preference",
            "question": "向用户提问的完整句子",
            "options": ["可选答案1", "可选答案2"]
        }}
    ],
    "summary": "一句话说明为何需要确认"
}}

注意：若初步识别结果置信度都 ≥0.8 且份量明确，可返回空 questions 数组。
"""
