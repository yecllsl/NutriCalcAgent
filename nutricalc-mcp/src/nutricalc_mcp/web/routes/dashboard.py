# web/routes/dashboard.py
"""概览路由 — Dashboard 首页片段与 KPI 数据 API"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from nutricalc_mcp.web.app import templates
from nutricalc_mcp.web import services

router = APIRouter()


@router.get("/partials/dashboard", response_class=HTMLResponse)
async def dashboard_partial(request: Request):
    """返回概览页片段"""
    summary = services.get_dashboard_summary()
    return templates.TemplateResponse(
        request,
        "partials/dashboard.html",
        {"summary": summary},
    )


@router.get("/api/dashboard/summary")
async def dashboard_summary_api():
    """返回概览 KPI 数据（JSON）"""
    return services.get_dashboard_summary()
