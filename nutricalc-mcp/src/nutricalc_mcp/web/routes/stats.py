# web/routes/stats.py
"""统计图表路由 — 多维统计 + 趋势 + 雷达图"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from nutricalc_mcp.web.app import templates
from nutricalc_mcp.web import services

router = APIRouter()


@router.get("/partials/stats", response_class=HTMLResponse)
async def stats_partial(request: Request):
    """返回统计图表页片段"""
    # 默认按日期统计 + 总览
    date_stats = services.get_stats_by_dimension("date")
    meal_stats = services.get_stats_by_dimension("meal_type")
    category_stats = services.get_stats_by_dimension("category")
    return templates.TemplateResponse(
        request,
        "partials/stats.html",
        {
            "date_stats": date_stats,
            "meal_stats": meal_stats,
            "category_stats": category_stats,
            "summary": date_stats.get("summary", {}),
        },
    )


@router.get("/api/stats")
async def stats_api(group_by: str = "date"):
    """按维度获取统计数据"""
    return services.get_stats_by_dimension(group_by=group_by)
