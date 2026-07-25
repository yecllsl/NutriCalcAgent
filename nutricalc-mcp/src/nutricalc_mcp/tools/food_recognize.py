# src/nutricalc_mcp/tools/food_recognize.py
"""食物识别 Tool

支持两种输入路径：
1. 拍照识别（image_path）：PaddleOCR 识别图片中的文字（菜单/标签/菜品牌）→
   返回视觉识别 prompt（供 MCP 宿主多模态 LLM 识别"是什么菜"+ 食材 + 份量）→
   本地食物成分表候选匹配 → 生成澄清提问
2. 文本输入（input_text）：直接查本地食物库，返回候选 + 澄清提问

设计对齐 DeepReview tools/ocr_recognize.py：
- PaddleOCR 懒加载单例，未安装时返回友好错误并降级为手动输入
- Tool 不直接调用 LLM，而是返回构造好的 prompt 交由 MCP 宿主执行（MCP 标准模式）
- 失败降级：OCR 失败/图片不存在时提示手动输入
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from nutricalc_mcp.food_db import get_food_db
from nutricalc_mcp.prompts.food_recognize_prompt import (
    FOOD_VISION_PROMPT, NUTRITION_LABEL_OCR_PROMPT, CLARIFICATION_PROMPT,
)

# 全局 OCR 引擎实例，懒加载避免启动时加载模型
_ocr_engine = None


def _get_ocr_engine():
    """获取 PaddleOCR 引擎实例（懒加载单例）

    首次调用时初始化 PaddleOCR，后续复用。use_angle_cls=True 支持旋转文字，lang="ch" 中文。
    PaddleOCR 为可选依赖，未安装时抛 ImportError 并附安装指引，由上层转为友好降级响应。
    """
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from paddleocr import PaddleOCR  # noqa: WPS433 (懒加载)
        except ImportError as exc:
            raise ImportError(
                "未安装 PaddleOCR。请运行 `uv sync --extra ocr` "
                "或 `uv pip install paddleocr paddlepaddle` 后重试。"
            ) from exc
        _ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    return _ocr_engine


def _run_paddle_ocr(image_path: str) -> str:
    """执行 PaddleOCR 识别，返回识别文本（每行一个结果）"""
    engine = _get_ocr_engine()
    result = engine.ocr(image_path, cls=True)
    lines = []
    if result and result[0]:
        for line in result[0]:
            # PaddleOCR 返回格式: [坐标列表, (文本, 置信度)]
            if line and len(line) >= 2:
                lines.append(line[1][0])
    return "\n".join(lines)


def _build_candidates_hint(raw_text: str, input_text: str, limit: int = 15) -> tuple[str, list[dict]]:
    """基于 OCR 文字或输入文本，从本地食物库匹配候选，构建候选提示串

    Returns:
        (candidates_hint 文本, candidates 列表)
    """
    db = get_food_db()
    keywords = []
    if input_text:
        keywords.append(input_text.strip())
    if raw_text:
        # 取 OCR 文字的每行作为候选关键词（去空行）
        keywords.extend([ln.strip() for ln in raw_text.split("\n") if ln.strip()])

    seen_ids: set[str] = set()
    candidates: list[dict] = []
    for kw in keywords[:8]:  # 最多取 8 个关键词
        for r in db.search(kw, limit=5):
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                candidates.append({
                    "food_id": r["id"],
                    "name": r["name"],
                    "category": r["category"],
                    "match_type": r.get("match_type", "partial"),
                })
        if len(candidates) >= limit:
            break

    if not candidates:
        return "（本地库暂无匹配候选，需 LLM 自行估算）", candidates
    hint_lines = [f"- {c['name']}（{c['category']}，ID:{c['food_id']}）" for c in candidates[:limit]]
    return "\n".join(hint_lines), candidates


def recognize_food(image_path: str = "", input_text: str = "") -> dict:
    """食物识别主入口

    Args:
        image_path: 食物图片本地路径（可选）
        input_text: 手动输入的食物名称/描述（可选，OCR 失败降级用）

    Returns:
        包含以下字段的字典:
        - raw_text: OCR 识别的原始文字（仅 image_path 模式）
        - vision_prompt: 视觉识别 prompt（供多模态 LLM 看图识别）
        - label_parse_prompt: 营养标签解析 prompt（基于 OCR 文字）
        - candidates: 本地食物库候选匹配列表
        - clarification_prompt: 澄清提问 prompt
        - parse_mode: actual 输入模式 photo/text/manual
        - error: 错误信息（仅在降级时存在）
    """
    # 路径 A：纯文本输入（无图片），直接查表
    if not image_path and input_text:
        return _recognize_by_text(input_text)

    # 路径 B：无任何输入
    if not image_path and not input_text:
        return {
            "raw_text": "",
            "vision_prompt": "",
            "candidates": [],
            "clarification_prompt": "",
            "parse_mode": "empty",
            "error": "未提供图片或文本输入，请上传食物照片或输入食物名称",
        }

    # 路径 C：拍照识别
    return _recognize_by_image(image_path, input_text)


def _recognize_by_text(input_text: str) -> dict:
    """文本输入模式：直接查本地食物库 + 生成澄清提问"""
    candidates_hint, candidates = _build_candidates_hint("", input_text)

    # 构造澄清提问（即使文本输入，份量/烹饪法仍需确认）
    preliminary = [{"name": input_text, "confidence": 0.6, "estimated_amount_g": "未知"}]
    clarification_prompt = CLARIFICATION_PROMPT.format(
        preliminary_result=_format_preliminary(preliminary)
    )

    return {
        "raw_text": "",
        "vision_prompt": "",
        "label_parse_prompt": "",
        "candidates": candidates,
        "clarification_prompt": clarification_prompt,
        "parse_mode": "text",
        "input_text": input_text,
    }


def _recognize_by_image(image_path: str, input_text: str = "") -> dict:
    """拍照识别模式：PaddleOCR + 视觉 prompt + 本地查表 + 澄清提问"""
    # 检查文件存在
    if not Path(image_path).exists():
        return {
            "raw_text": "",
            "vision_prompt": "",
            "candidates": [],
            "clarification_prompt": "",
            "parse_mode": "photo",
            "error": f"图片文件不存在: {image_path}，请重试或手动输入食物名称",
        }

    # 执行 OCR 识别
    raw_text = ""
    ocr_error = None
    try:
        raw_text = _run_paddle_ocr(image_path)
    except ImportError as e:
        # PaddleOCR 未安装：降级为纯视觉 prompt（仍可让宿主 LLM 看图识别）
        ocr_error = f"PaddleOCR 未安装，跳过文字识别：{str(e)}"
    except Exception as e:
        ocr_error = f"OCR 识别失败：{str(e)}"

    # 构建本地库候选（基于 OCR 文字 + 输入文本）
    candidates_hint, candidates = _build_candidates_hint(raw_text, input_text)

    # 构建视觉识别 prompt（供多模态 LLM 看图识别菜品）
    context_hint = "用户上传了一张食物照片。"
    if input_text:
        context_hint += f"用户补充说明：{input_text}。"
    if ocr_error:
        context_hint += "（OCR 文字识别不可用，请主要依赖视觉识别）"
    elif raw_text:
        context_hint += f"OCR 识别到文字：\n{raw_text}"

    vision_prompt = FOOD_VISION_PROMPT.format(
        context_hint=context_hint,
        candidates_hint=candidates_hint,
    )

    # 构建营养标签解析 prompt（若 OCR 文字像标签/菜单）
    label_parse_prompt = ""
    if raw_text and any(kw in raw_text for kw in ["能量", "蛋白质", "脂肪", "kcal", "营养成分", "菜单"]):
        label_parse_prompt = NUTRITION_LABEL_OCR_PROMPT.format(raw_text=raw_text)

    # 构建澄清提问 prompt
    preliminary = []
    if candidates:
        for c in candidates[:3]:
            preliminary.append({"name": c["name"], "confidence": 0.6, "estimated_amount_g": "未知"})
    clarification_prompt = CLARIFICATION_PROMPT.format(
        preliminary_result=_format_preliminary(preliminary) if preliminary else "（待视觉识别后确定）"
    )

    result = {
        "raw_text": raw_text,
        "vision_prompt": vision_prompt,
        "candidates": candidates,
        "clarification_prompt": clarification_prompt,
        "parse_mode": "photo",
        "image_path": image_path,
    }
    if label_parse_prompt:
        result["label_parse_prompt"] = label_parse_prompt
    if ocr_error:
        result["warning"] = ocr_error
        # OCR 失败但仍返回视觉 prompt，让宿主 LLM 识别
    return result


def _format_preliminary(items: list[dict]) -> str:
    """格式化初步识别结果用于 prompt"""
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(
            f"{i}. {it.get('name', '未知')} "
            f"(置信度: {it.get('confidence', '?')}, 份量: {it.get('estimated_amount_g', '未知')})"
        )
    return "\n".join(lines) if lines else "（暂无）"
