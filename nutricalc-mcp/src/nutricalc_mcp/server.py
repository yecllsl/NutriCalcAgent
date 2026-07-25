# src/nutricalc_mcp/server.py
"""NutriCalcAgent MCP Server 入口

注册所有 MCP 工具（4 个饮食记录 CRUD + 8 个业务工具），通过 FastMCP 框架对外提供服务。
业务工具模块使用懒导入（函数体内 import），确保 server.py 本身可正常加载，
后续业务模块按 Task 逐个实现。

工具清单:
- CRUD: save_food_log / query_food_logs / update_food_log / delete_food_log
- 业务: recognize_food / analyze_nutrition / assess_balance /
        get_statistics / nutritionist_advice / save_user_profile /
        load_user_profile / export_data
"""
from fastmcp import FastMCP

mcp = FastMCP(
    name="nutricalc-mcp",
    instructions="本地优先、隐私保护、AI驱动的中文营养师 Agent MCP Server",
)


# ──────────────────────────────────────────
# 饮食记录 CRUD（已实现）
# ──────────────────────────────────────────

@mcp.tool()
def save_food_log(log_data: dict) -> dict:
    """保存饮食记录到本地 JSON 文件。

    log_data 需符合 FoodLog 结构：meal_time/meal_type/items 等；
    log_id 与 created_at 缺省时自动生成。
    """
    from nutricalc_mcp.tools.crud import save_food_log as _save
    return _save(log_data)


@mcp.tool()
def query_food_logs(filters: dict) -> dict:
    """按条件查询饮食记录。

    filters 支持 meal_type(餐次) / category(食物类别) / date_range({start,end})。
    """
    from nutricalc_mcp.tools.crud import query_food_logs as _query
    return _query(filters)


@mcp.tool()
def update_food_log(log_data: dict) -> dict:
    """更新饮食记录（覆盖写入，需包含 log_id）。"""
    from nutricalc_mcp.tools.crud import update_food_log as _update
    return _update(log_data)


@mcp.tool()
def delete_food_log(log_id: str) -> dict:
    """删除饮食记录。"""
    from nutricalc_mcp.tools.crud import delete_food_log as _delete
    return _delete(log_id)


# ──────────────────────────────────────────
# 业务工具（懒导入，按 Task 实现）
# ──────────────────────────────────────────

@mcp.tool()
def recognize_food(image_path: str = "", input_text: str = "") -> dict:
    """食物图像识别 + 文本识别。

    上传食物照片后：
    1. PaddleOCR 识别图片中的文字（菜单/营养标签/菜品牌）
    2. 返回视觉识别 prompt（供 MCP 宿主多模态 LLM 识别"是什么菜"+ 食材 + 份量）
    3. 本地食物成分表候选匹配
    4. 生成澄清提问（菜名/烹饪法/份量），向用户确认
    失败时降级为手动输入（input_text 直接查表）。
    """
    from nutricalc_mcp.tools.food_recognize import recognize_food as _rec
    return _rec(image_path=image_path, input_text=input_text)


@mcp.tool()
def analyze_nutrition(items: list[dict]) -> dict:
    """营养成分分析。

    items 为 FoodItem 列表（name + amount_g + 可选 cooking_method）。
    优先本地食物成分表查表；未命中时返回估算 prompt 供 LLM 基于食材估算。
    输出每项营养 + 汇总营养（NutritionFacts）。
    """
    from nutricalc_mcp.tools.nutrition_analyze import analyze_nutrition as _ana
    return _ana(items)


@mcp.tool()
def assess_balance(period: str = "daily", start_date: str = "", end_date: str = "") -> dict:
    """营养平衡评估（日/周/月时序）。

    基于指定周期的饮食记录，计算总摄入、日均摄入、对 RNI 达成率、
    平衡评分、营养缺口/过量、饮食多样性评分，生成结构化建议。
    period: daily/weekly/monthly；start_date/end_date 可选，缺省取最近周期。
    """
    from nutricalc_mcp.tools.balance_assess import assess_balance as _assess
    return _assess(period=period, start_date=start_date, end_date=end_date)


@mcp.tool()
def get_statistics(group_by: str) -> dict:
    """统计分析饮食记录分布与趋势。

    group_by 支持 date(日期)/meal_type(餐次)/category(食物类别)/nutrient(营养素)。
    返回分组统计 + 30 天趋势 + 营养雷达图数据。
    """
    from nutricalc_mcp.tools.statistics import get_statistics as _stats
    return _stats(group_by=group_by)


@mcp.tool()
def nutritionist_advice(period: str = "daily", persona: str = "professional", question: str = "") -> dict:
    """AI 营养师个性化建议。

    基于近期饮食记录 + 平衡评估 + 用户档案，生成上下文感知的营养师建议 prompt，
    供 MCP 宿主 LLM 生成多轮对话式建议（为什么这样吃/下一餐怎么吃/本周趋势/缺什么）。
    persona: professional(专业) / gentle(温柔) / strict(严格)。
    """
    from nutricalc_mcp.tools.nutritionist import nutritionist_advice as _adv
    return _adv(period=period, persona=persona, question=question)


@mcp.tool()
def save_user_profile(profile_data: dict) -> dict:
    """保存用户档案（年龄/性别/身高/体重/活动水平/目标/生命阶段），
    用于个性化 RNI 计算与平衡评估基准。
    """
    from nutricalc_mcp.tools.crud import save_user_profile as _save_p
    return _save_p(profile_data)


@mcp.tool()
def load_user_profile(user_id: str = "default") -> dict:
    """加载用户档案；不存在返回默认成人档案。"""
    from nutricalc_mcp.tools.crud import load_user_profile as _load_p
    return _load_p(user_id)


@mcp.tool()
def export_data(format: str = "json", filters: dict = None) -> dict:
    """导出饮食记录数据（json/csv）。导出前需用户确认（数据安全规则）。"""
    from nutricalc_mcp.tools.export import export_data as _export
    return _export(format=format, filters=filters or {})


def main():
    """启动 MCP Server（stdio 传输模式）"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
