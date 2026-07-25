# web/routes/analysis.py
"""分析路由 — 营养平衡评估 + AI 营养师建议 + 趋势解读"""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

from nutricalc_mcp.web.app import templates
from nutricalc_mcp.web import services

router = APIRouter()


@router.get("/partials/analysis", response_class=HTMLResponse)
async def analysis_partial(request: Request, period: str = "daily"):
    """返回分析页片段（平衡评估 + 营养师建议）"""
    assessment = services.get_balance_assessment(period=period)
    advice = services.get_nutritionist_advice(period=period, persona="professional")
    options = services.get_form_options()
    return templates.TemplateResponse(
        request,
        "partials/analysis.html",
        {
            "assessment": assessment.get("assessment", {}),
            "radar_data": assessment.get("radar_data", {"indicators": [], "values": []}),
            "advice_prompt": advice.get("advice_prompt", ""),
            "advice_context": advice.get("context", {}),
            "next_meal_prompt": advice.get("next_meal_prompt", ""),
            "period": period,
            "options": options,
        },
    )


@router.post("/partials/analysis", response_class=HTMLResponse)
async def analysis_with_persona(
    request: Request,
    period: str = Form("daily"),
    persona: str = Form("professional"),
    question: str = Form(""),
):
    """按人设/提问重新生成分析（HTMX 表单提交）"""
    assessment = services.get_balance_assessment(period=period)
    advice = services.get_nutritionist_advice(period=period, persona=persona, question=question)
    options = services.get_form_options()
    return templates.TemplateResponse(
        request,
        "partials/analysis.html",
        {
            "assessment": assessment.get("assessment", {}),
            "radar_data": assessment.get("radar_data", {"indicators": [], "values": []}),
            "advice_prompt": advice.get("advice_prompt", ""),
            "advice_context": advice.get("context", {}),
            "advice_mode": advice.get("mode", "advice"),
            "next_meal_prompt": advice.get("next_meal_prompt", ""),
            "period": period,
            "selected_persona": persona,
            "user_question": question,
            "options": options,
        },
    )


@router.get("/api/analysis/balance")
async def balance_api(period: str = "daily"):
    """平衡评估 JSON API"""
    return services.get_balance_assessment(period=period)


@router.get("/api/analysis/advice")
async def advice_api(period: str = "daily", persona: str = "professional", question: str = ""):
    """营养师建议 JSON API"""
    return services.get_nutritionist_advice(period=period, persona=persona, question=question)


@router.get("/api/analysis/trend")
async def trend_api(period: str = "weekly"):
    """趋势解读 JSON API"""
    return services.get_trend_interpretation(period=period)
