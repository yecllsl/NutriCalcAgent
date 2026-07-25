# web/routes/profile.py
"""用户档案路由 — 档案查看与编辑"""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse

from nutricalc_mcp.web.app import templates
from nutricalc_mcp.web import services

router = APIRouter()


@router.get("/partials/profile", response_class=HTMLResponse)
async def profile_partial(request: Request):
    """返回用户档案页片段"""
    profile = services.get_user_profile()
    options = services.get_form_options()
    return templates.TemplateResponse(
        request,
        "partials/profile.html",
        {
            "profile": profile,
            "options": options,
            "not_found": profile.get("not_found", False),
        },
    )


@router.post("/api/profile/save", response_class=HTMLResponse)
async def save_profile(
    request: Request,
    age: int = Form(...),
    gender: str = Form(...),
    height_cm: float = Form(...),
    weight_kg: float = Form(...),
    activity_level: str = Form("轻度"),
    goal: str = Form("maintain"),
    life_stage: str = Form("成人"),
    allergies: str = Form(""),
):
    """保存用户档案（HTMX 表单提交）"""
    allergy_list = [a.strip() for a in allergies.split(",") if a.strip()]
    profile_data = {
        "user_id": "default",
        "age": age,
        "gender": gender,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "activity_level": activity_level,
        "goal": goal,
        "life_stage": life_stage,
        "allergies": allergy_list,
    }
    try:
        services.set_user_profile(profile_data)
    except Exception as e:
        profile = services.get_user_profile()
        options = services.get_form_options()
        return templates.TemplateResponse(
            request,
            "partials/profile_form.html",
            {"profile": profile, "options": options, "error": f"保存失败：{str(e)}"},
        )

    # 成功：返回展示视图
    profile = services.get_user_profile()
    options = services.get_form_options()
    return templates.TemplateResponse(
        request,
        "partials/profile_view.html",
        {"profile": profile, "options": options, "success": "档案已保存"},
    )


@router.get("/partials/profile/edit", response_class=HTMLResponse)
async def profile_edit_partial(request: Request):
    """返回档案编辑表单片段"""
    profile = services.get_user_profile()
    options = services.get_form_options()
    return templates.TemplateResponse(
        request,
        "partials/profile_form.html",
        {"profile": profile, "options": options},
    )


@router.get("/api/profile")
async def profile_api():
    """用户档案 JSON API"""
    return services.get_user_profile()
