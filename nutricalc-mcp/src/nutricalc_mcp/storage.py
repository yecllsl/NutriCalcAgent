# src/nutricalc_mcp/storage.py
"""本地 JSON 文件存储引擎

提供饮食记录（FoodLog）、用户档案（UserProfile）、平衡评估（BalanceAssessment）、
营养师建议（NutritionAdvice）的 CRUD 操作、查询过滤、统计支持。

设计对齐 DeepReview storage.py：
- 数据以 JSON 文件形式存储在本地文件系统，按类型分目录管理
- 原子写入：先写 .tmp 临时文件，再 os.replace 原子替换，防止写入中途崩溃损坏数据
- 文件名即 ID（{record_id}.json）
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from nutricalc_mcp.models import (
    FoodLog, UserProfile, BalanceAssessment, NutritionAdvice,
)


class Storage:
    """本地 JSON 文件存储引擎

    目录结构:
        base_dir/
        ├── food_logs/         # 饮食记录 FoodLog
        ├── food_images/       # 上传的食物图片
        ├── analysis_reports/  # 平衡评估 + 营养建议
        ├── meal_plans/        # 饮食计划（预留）
        ├── food_db/           # 中国食物成分表本地库
        └── user_profile/      # 用户档案 UserProfile
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.logs_dir = base_dir / "food_logs"
        self.images_dir = base_dir / "food_images"
        self.reports_dir = base_dir / "analysis_reports"
        self.plans_dir = base_dir / "meal_plans"
        self.food_db_dir = base_dir / "food_db"
        self.profile_dir = base_dir / "user_profile"
        # 确保所有子目录存在
        for d in [self.logs_dir, self.images_dir, self.reports_dir,
                  self.plans_dir, self.food_db_dir, self.profile_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────
    # 原子写入辅助
    # ──────────────────────────────────────────

    def _atomic_write(self, fp: Path, content: str):
        """原子写入：先写 .tmp，再 os.replace 原子替换"""
        tmp_fp = fp.with_suffix(fp.suffix + ".tmp")
        tmp_fp.write_text(content, encoding="utf-8")
        os.replace(tmp_fp, fp)

    def _read_json(self, fp: Path) -> Optional[dict]:
        """读取 JSON 文件，不存在返回 None"""
        if not fp.exists():
            return None
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    # ──────────────────────────────────────────
    # 饮食记录 FoodLog CRUD
    # ──────────────────────────────────────────

    def save_food_log(self, log: FoodLog) -> dict:
        """保存饮食记录（原子写入），返回 log_id 与文件路径

        若 log_id 为空，自动生成 fl_YYYYMMDD_NNN 格式 ID。
        """
        if not log.log_id:
            log.log_id = self._generate_log_id()
        fp = self.logs_dir / f"{log.log_id}.json"
        self._atomic_write(fp, log.model_dump_json(indent=2, ensure_ascii=False))
        return {"log_id": log.log_id, "saved_path": str(fp)}

    def _generate_log_id(self) -> str:
        """生成饮食记录ID：fl_YYYYMMDD_NNN（当天序号递增）"""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"fl_{today}_"
        existing = [lid for lid in self.list_all_log_ids() if lid.startswith(prefix)]
        seq = len(existing) + 1
        return f"fl_{today}_{seq:03d}"

    def load_food_log(self, log_id: str) -> Optional[FoodLog]:
        """根据 ID 加载饮食记录，不存在返回 None"""
        fp = self.logs_dir / f"{log_id}.json"
        data = self._read_json(fp)
        if data is None:
            return None
        return FoodLog.model_validate(data)

    def update_food_log(self, log: FoodLog) -> dict:
        """更新饮食记录（覆盖写入），语义等同 save"""
        return self.save_food_log(log)

    def delete_food_log(self, log_id: str) -> bool:
        """删除饮食记录文件，返回是否删除成功"""
        fp = self.logs_dir / f"{log_id}.json"
        if fp.exists():
            fp.unlink()
            return True
        return False

    def list_all_log_ids(self) -> list[str]:
        """列出所有饮食记录ID（文件名不含扩展名，仅 fl_ 前缀）"""
        return [f.stem for f in self.logs_dir.glob("fl_*.json")]

    def query_food_logs(self, filters: dict) -> dict:
        """根据过滤条件查询饮食记录

        支持的过滤条件:
            - meal_type: 餐次
            - category: 食物类别（items 中任一匹配）
            - date_range: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
                         按 meal_time 过滤
        """
        logs = []
        for lid in self.list_all_log_ids():
            fl = self.load_food_log(lid)
            if fl and self._matches(fl, filters):
                # mode="json" 确保 datetime 序列化为 ISO 字符串，
                # 供 Web 模板与 MCP 宿主直接消费
                logs.append(fl.model_dump(mode="json"))
        # 按进食时间倒序（ISO 字符串可正确按字典序比较）
        logs.sort(key=lambda x: x.get("meal_time", ""), reverse=True)
        return {"food_logs": logs, "total_count": len(logs)}

    def _matches(self, fl: FoodLog, f: dict) -> bool:
        """判断饮食记录是否匹配过滤条件"""
        if not f:
            return True
        if f.get("meal_type") and fl.meal_type != f["meal_type"]:
            return False
        if f.get("category"):
            # items 中任一食物类别匹配即可
            cats = {it.category for it in fl.items}
            if f["category"] not in cats:
                return False
        dr = f.get("date_range")
        if dr:
            meal_date = fl.meal_time.strftime("%Y-%m-%d") if fl.meal_time else ""
            if dr.get("start") and meal_date < dr["start"]:
                return False
            if dr.get("end") and meal_date > dr["end"]:
                return False
        return True

    def get_all_logs_for_statistics(self) -> list[FoodLog]:
        """获取全部饮食记录用于统计计算"""
        return [fl for lid in self.list_all_log_ids() if (fl := self.load_food_log(lid))]

    def get_logs_by_date_range(self, start: str, end: str) -> list[FoodLog]:
        """获取指定日期范围内的饮食记录（按 meal_time 过滤）"""
        result = []
        for fl in self.get_all_logs_for_statistics():
            meal_date = fl.meal_time.strftime("%Y-%m-%d") if fl.meal_time else ""
            if start <= meal_date <= end:
                result.append(fl)
        return result

    def save_image(self, image_bytes: bytes, filename: str) -> str:
        """保存食物图片到本地，返回相对路径

        图片文件名加时间戳前缀避免重名。
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_name = filename.replace(" ", "_")
        fp = self.images_dir / f"{ts}_{safe_name}"
        fp.write_bytes(image_bytes)
        return str(fp)

    # ──────────────────────────────────────────
    # 用户档案 UserProfile
    # ──────────────────────────────────────────

    def save_user_profile(self, profile: UserProfile) -> dict:
        """保存用户档案（本地单用户，固定文件名 profile.json）"""
        fp = self.profile_dir / f"{profile.user_id}.json"
        self._atomic_write(fp, profile.model_dump_json(indent=2, ensure_ascii=False))
        return {"user_id": profile.user_id, "saved_path": str(fp)}

    def load_user_profile(self, user_id: str = "default") -> Optional[UserProfile]:
        """加载用户档案，不存在返回 None"""
        fp = self.profile_dir / f"{user_id}.json"
        data = self._read_json(fp)
        if data is None:
            return None
        return UserProfile.model_validate(data)

    # ──────────────────────────────────────────
    # 平衡评估 BalanceAssessment
    # ──────────────────────────────────────────

    def save_assessment(self, assessment: BalanceAssessment) -> dict:
        """保存平衡评估报告"""
        fp = self.reports_dir / f"{assessment.assessment_id}.json"
        self._atomic_write(fp, assessment.model_dump_json(indent=2, ensure_ascii=False))
        return {"assessment_id": assessment.assessment_id, "saved_path": str(fp)}

    def load_assessment(self, assessment_id: str) -> Optional[BalanceAssessment]:
        """加载平衡评估报告"""
        fp = self.reports_dir / f"{assessment_id}.json"
        data = self._read_json(fp)
        if data is None:
            return None
        return BalanceAssessment.model_validate(data)

    def list_assessments(self) -> list[str]:
        """列出所有评估报告ID"""
        return [f.stem for f in self.reports_dir.glob("as_*.json")]

    # ──────────────────────────────────────────
    # 营养师建议 NutritionAdvice
    # ──────────────────────────────────────────

    def save_advice(self, advice: NutritionAdvice) -> dict:
        """保存营养师建议"""
        fp = self.reports_dir / f"{advice.advice_id}.json"
        self._atomic_write(fp, advice.model_dump_json(indent=2, ensure_ascii=False))
        return {"advice_id": advice.advice_id, "saved_path": str(fp)}

    def load_advice(self, advice_id: str) -> Optional[NutritionAdvice]:
        """加载营养师建议"""
        fp = self.reports_dir / f"{advice_id}.json"
        data = self._read_json(fp)
        if data is None:
            return None
        return NutritionAdvice.model_validate(data)
