# src/nutricalc_mcp/tools/export.py
"""数据导出 Tool

将饮食记录、用户档案、评估报告导出为 JSON / CSV，供用户备份或迁移。
遵循数据安全规则：导出操作本身不外传数据，仅生成本地文件/内容；
实际下载/外发由 Web 层或 MCP 宿主在用户确认后执行。

支持格式：
- json: 完整结构化导出（含嵌套营养素），适合备份/迁移
- csv:  扁平化导出（每行一条饮食记录），适合 Excel 分析
- xlsx: 预留（通过 pandas/openpyxl 实现，未安装时降级为 csv）

对齐 DeepReview 的"工具层只构造数据，不直接外传"原则。
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Optional

from nutricalc_mcp.tools.crud import get_storage, load_user_profile
from nutricalc_mcp.knowledge_map import NUTRIENT_META


# CSV 扁平化表头：基础字段 + 营养素字段
_CSV_HEADERS = [
    "log_id", "meal_time", "meal_type", "food_name", "category",
    "amount_g", "cooking_method", "source", "confirmed",
] + [meta["key"] for meta in NUTRIENT_META]


def _flatten_logs(logs: list) -> list[dict]:
    """将 FoodLog 列表扁平化为 CSV 行（每个食物项一行）

    若一条记录有多个食物项，则展开为多行；无食物项则保留一行（食物字段为空）。
    营养素取食物项自身的 nutrition，无则用记录汇总 nutrition 仅填充到首行。
    """
    rows: list[dict] = []
    for fl in logs:
        meal_time = fl.meal_time.strftime("%Y-%m-%d %H:%M") if fl.meal_time else ""
        base = {
            "log_id": fl.log_id,
            "meal_time": meal_time,
            "meal_type": fl.meal_type,
            "confirmed": fl.confirmed,
        }
        if not fl.items:
            # 无食物项：填一行空食物 + 汇总营养
            row = {h: "" for h in _CSV_HEADERS}
            row.update(base)
            if fl.nutrition:
                for meta in NUTRIENT_META:
                    row[meta["key"]] = round(getattr(fl.nutrition, meta["key"], 0) or 0, 3)
            rows.append(row)
            continue

        for item in fl.items:
            row = {h: "" for h in _CSV_HEADERS}
            row.update(base)
            row.update({
                "food_name": item.name,
                "category": item.category,
                "amount_g": item.amount_g,
                "cooking_method": item.cooking_method or "",
                "source": item.source,
            })
            n = item.nutrition or fl.nutrition
            if n:
                for meta in NUTRIENT_META:
                    row[meta["key"]] = round(getattr(n, meta["key"], 0) or 0, 3)
            rows.append(row)
    return rows


def _build_json_export(logs: list, profile: dict) -> dict:
    """构造 JSON 导出结构（完整嵌套，含用户档案）"""
    return {
        "export_meta": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "app": "NutriCalcAgent",
            "version": "0.1.1",
            "log_count": len(logs),
            "note": "本数据由本地营养师 Agent 导出，仅供个人备份与分析",
        },
        "user_profile": profile,
        "food_logs": [fl.model_dump(mode="json") for fl in logs],
    }


def _build_csv_content(logs: list) -> str:
    """构造 CSV 导出内容字符串"""
    rows = _flatten_logs(logs)
    output = io.StringIO()
    # utf-8-sig BOM 让 Excel 正确识别中文
    output.write("\ufeff")
    writer = csv.DictWriter(output, fieldnames=_CSV_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def export_data(
    format: str = "json",
    filters: Optional[dict] = None,
    include_profile: bool = True,
) -> dict:
    """数据导出主入口

    Args:
        format: 导出格式 json / csv
        filters: 过滤条件（同 query_food_logs：meal_type/category/date_range）
        include_profile: 是否包含用户档案（仅 json 格式有效）

    Returns:
        {
            format: 实际格式,
            content: 导出内容字符串（json/csv 文本）,
            log_count: 导出记录数,
            food_item_count: 导出食物项总数,
            filename: 建议文件名,
            needs_confirmation: True（提示需用户确认后外发）,
        }
    """
    filters = filters or {}
    storage = get_storage()
    # 复用 storage 的查询过滤（返回 model_dump 列表，这里重新加载以获取完整对象）
    query_result = storage.query_food_logs(filters=filters)
    log_ids = [item["log_id"] for item in query_result["food_logs"]]
    logs = [fl for fl in (storage.load_food_log(lid) for lid in log_ids) if fl]

    # 统计食物项
    food_item_count = sum(len(fl.items) for fl in logs)

    # 时间戳用于文件名
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format == "csv":
        content = _build_csv_content(logs)
        filename = f"nutricalc_export_{ts}.csv"
        return {
            "format": "csv",
            "content": content,
            "log_count": len(logs),
            "food_item_count": food_item_count,
            "filename": filename,
            "needs_confirmation": True,
            "headers": _CSV_HEADERS,
        }

    # 默认 json
    profile = load_user_profile("default") if include_profile else {}
    # 移除 not_found 标记（导出时无需）
    profile.pop("not_found", None)
    export_obj = _build_json_export(logs, profile)
    content = json.dumps(export_obj, ensure_ascii=False, indent=2, default=str)
    filename = f"nutricalc_export_{ts}.json"
    return {
        "format": "json",
        "content": content,
        "log_count": len(logs),
        "food_item_count": food_item_count,
        "filename": filename,
        "needs_confirmation": True,
        "export_meta": export_obj["export_meta"],
    }


def export_summary(filters: Optional[dict] = None) -> dict:
    """导出预览（不生成实际内容，仅统计待导出数据量）

    供 Web 层在用户确认前展示"将导出 N 条记录"。
    """
    filters = filters or {}
    storage = get_storage()
    query_result = storage.query_food_logs(filters=filters)
    log_count = query_result["total_count"]
    food_item_count = sum(
        len(item.get("items", [])) for item in query_result["food_logs"]
    )
    # 日期范围
    dates = [
        item.get("meal_time", "")[:10]
        for item in query_result["food_logs"]
        if item.get("meal_time")
    ]
    date_range = {"start": min(dates), "end": max(dates)} if dates else {"start": "", "end": ""}
    return {
        "log_count": log_count,
        "food_item_count": food_item_count,
        "date_range": date_range,
        "filters": filters,
    }
