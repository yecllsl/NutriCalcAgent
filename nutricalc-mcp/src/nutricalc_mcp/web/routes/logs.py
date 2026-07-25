# web/routes/logs.py
"""饮食记录路由 — 记录录入、列表查询、详情、删除、图片上传

提供 HTMX partial 端点（页面片段）与 JSON API 端点。
表单提交通过 HTMX，返回更新后的列表片段。
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from nutricalc_mcp.web.app import templates
from nutricalc_mcp.web import services

router = APIRouter()


@router.get("/partials/logs", response_class=HTMLResponse)
async def logs_partial(request: Request, meal_type: str = "", category: str = ""):
    """返回饮食记录页片段（含录入表单 + 记录列表）"""
    filters = {}
    if meal_type:
        filters["meal_type"] = meal_type
    if category:
        filters["category"] = category
    logs_data = services.get_food_logs(filters=filters if filters else None)
    options = services.get_form_options()
    # 默认表单值：当前时间、默认餐次
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    hour = datetime.now(timezone.utc).hour
    default_meal = "早餐" if hour < 10 else "午餐" if hour < 14 else "加餐" if hour < 17 else "晚餐"
    return templates.TemplateResponse(
        request,
        "partials/logs.html",
        {
            "logs": logs_data["food_logs"],
            "total_count": logs_data["total_count"],
            "filters": {"meal_type": meal_type, "category": category},
            "options": options,
            "now": now,
            "default_meal": default_meal,
        },
    )


@router.post("/api/logs/add", response_class=HTMLResponse)
async def add_log(
    request: Request,
    meal_time: str = Form(...),
    meal_type: str = Form(...),
    food_names: str = Form(""),
    food_amounts: str = Form(""),
    food_categories: str = Form(""),
    cooking_methods: str = Form(""),
    note: str = Form(""),
):
    """新增饮食记录（HTMX 表单提交）

    食物项以逗号分隔的多值传入，按位置对齐。
    """
    # 解析食物项（逗号分隔，按位置对齐）
    names = [n.strip() for n in food_names.split(",") if n.strip()]
    amounts = [a.strip() for a in food_amounts.split(",") if a.strip()]
    categories = [c.strip() for c in food_categories.split(",") if c.strip()]
    cookings = [c.strip() for c in cooking_methods.split(",") if c.strip()]

    items = []
    for i, name in enumerate(names):
        try:
            amount = float(amounts[i]) if i < len(amounts) and amounts[i] else 0
        except ValueError:
            amount = 0
        items.append({
            "food_id": "",
            "name": name,
            "amount_g": amount,
            "category": categories[i] if i < len(categories) else "其他",
            "source": "manual",
            "cooking_method": cookings[i] if i < len(cookings) and cookings[i] else None,
        })

    log_data = {
        "meal_time": meal_time,
        "meal_type": meal_type,
        "items": items,
        "note": note,
        "confirmed": True,  # 手动录入视为已确认
    }
    try:
        services.add_food_log(log_data)
    except Exception as e:
        # 失败时返回带错误提示的列表
        logs_data = services.get_food_logs()
        return templates.TemplateResponse(
            request,
            "partials/log_list.html",
            {"logs": logs_data["food_logs"], "total_count": logs_data["total_count"],
             "error": f"保存失败：{str(e)}"},
        )

    # 成功：返回更新后的列表片段
    logs_data = services.get_food_logs()
    return templates.TemplateResponse(
        request,
        "partials/log_list.html",
        {"logs": logs_data["food_logs"], "total_count": logs_data["total_count"],
         "success": "记录已保存"},
    )


@router.delete("/api/logs/{log_id}", response_class=HTMLResponse)
async def delete_log(request: Request, log_id: str):
    """删除饮食记录，返回更新后的列表片段"""
    services.remove_food_log(log_id)
    logs_data = services.get_food_logs()
    return templates.TemplateResponse(
        request,
        "partials/log_list.html",
        {"logs": logs_data["food_logs"], "total_count": logs_data["total_count"],
         "success": "记录已删除"},
    )


@router.get("/api/logs")
async def list_logs_api(meal_type: str = "", category: str = ""):
    """饮食记录列表 JSON API"""
    filters = {}
    if meal_type:
        filters["meal_type"] = meal_type
    if category:
        filters["category"] = category
    return services.get_food_logs(filters=filters if filters else None)


@router.get("/api/logs/{log_id}")
async def log_detail_api(log_id: str):
    """单条记录详情 JSON API"""
    detail = services.get_log_detail(log_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return detail
