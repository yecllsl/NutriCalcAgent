# src/nutricalc_mcp/prompts/balance_assess_prompt.py
"""营养平衡评估 Prompt 模板"""

BALANCE_ADVICE_PROMPT = """你是一位资深注册营养师。请基于以下营养平衡评估结果，生成个性化、可执行的营养改善建议。

评估周期：{period}（{start_date} 至 {end_date}，共 {days} 天）
用户档案：{user_profile}
用户健康目标：{goal}

日均营养摄入与 RNI 达成率：
{achievement_detail}

营养缺口/过量清单：
{gaps_detail}

饮食多样性评分：{diversity_score}/100
平衡评分：{balance_score}/100

{chronic_tips}

请输出（JSON）：
{{
    "summary": "一句话总览（如 本周整体能量达标，但膳食纤维与钙持续不足）",
    "key_findings": [
        "关键发现1（具体到营养素与数值）",
        "关键发现2",
        "关键发现3"
    ],
    "recommendations": [
        {{
            "priority": "high/medium/low",
            "nutrient": "相关营养素",
            "action": "具体可执行的饮食动作（如 每日增加 200g 深色蔬菜）",
            "food_suggestions": ["推荐食物1", "推荐食物2", "推荐食物3"],
            "expected_effect": "预期改善效果"
        }}
    ],
    "next_meal_suggestion": "下一餐针对性建议",
    "weekly_goal": "本周可量化目标（如 膳食纤维日均提升至 25g）",
    "caution": "免责声明：本建议为营养参考，非医疗建议；慢病患者请遵医嘱"
}}

建议生成要点：
- 必须具体到营养素与食物，禁止笼统建议（如"多吃蔬菜"应改为"每日增加 200g 菠菜/西兰花"）
- 每个建议必须可执行、可量化、可验证
- 优先处理 high 优先级缺口（连续不足的关键营养素）
- 结合用户健康目标（减脂/控糖/孕期等）定制
- 至少 3 个食物推荐方向
- 慢病人群须叠加对应膳食指南要点
"""


BALANCE_PERIOD_PROMPT = """请生成 {period} 营养平衡报告的自然语言解读。

周期：{start_date} 至 {end_date}（{days} 天）
平衡评分：{balance_score}/100
饮食多样性：{diversity_score}/100

主要营养缺口：{top_gaps}
主要过量营养素：{top_excess}

请用 200 字以内简明解读本周期营养状况，包括：
1. 整体评价
2. 做得好的方面
3. 需要改进的方面
4. 下周期重点关注
"""
