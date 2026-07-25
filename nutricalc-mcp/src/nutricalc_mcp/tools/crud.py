# src/nutricalc_mcp/tools/crud.py
"""饮食记录与用户档案 CRUD 操作 Tools

作为 MCP Tool 的业务逻辑层，底层调用 Storage 引擎完成实际文件 IO。
对齐 DeepReview tools/crud.py 的 get_storage 单例 + 薄封装模式。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from nutricalc_mcp.models import FoodLog, UserProfile
from nutricalc_mcp.storage import Storage

# 默认数据目录：项目根目录下的 data/ 文件夹
_DEFAULT_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"


def get_storage() -> Storage:
    """获取默认 Storage 实例（指向项目 data 目录）"""
    return Storage(base_dir=_DEFAULT_DATA_DIR)


def _next_log_id(storage: Storage) -> str:
    """生成下一个饮食记录ID：fl_YYYYMMDD_NNN

    扫描当天已有的记录数，生成 3 位序号，避免冲突。
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"fl_{today}_"
    existing = [lid for lid in storage.list_all_log_ids() if lid.startswith(prefix)]
    seq = len(existing) + 1
    return f"fl_{today}_{seq:03d}"


# ──────────────────────────────────────────
# 饮食记录 CRUD
# ──────────────────────────────────────────

def save_food_log(log_data: dict) -> dict:
    """保存饮食记录

    Args:
        log_data: 饮食记录字典，符合 FoodLog 模型结构。
                  若未提供 log_id/created_at，自动生成。

    Returns:
        包含 log_id 和 saved_path 的字典
    """
    storage = get_storage()
    # 自动填充 ID 与创建时间
    if not log_data.get("log_id"):
        log_data["log_id"] = _next_log_id(storage)
    if not log_data.get("created_at"):
        log_data["created_at"] = datetime.now(timezone.utc).isoformat()
    fl = FoodLog.model_validate(log_data)
    return storage.save_food_log(fl)


def query_food_logs(filters: dict) -> dict:
    """按条件查询饮食记录

    Args:
        filters: 过滤条件字典，支持 meal_type/category/date_range

    Returns:
        包含 food_logs 列表和 total_count 的字典
    """
    return get_storage().query_food_logs(filters=filters or {})


def update_food_log(log_data: dict) -> dict:
    """更新饮食记录（覆盖写入，需包含 log_id）"""
    storage = get_storage()
    fl = FoodLog.model_validate(log_data)
    return storage.save_food_log(fl)


def patch_food_log(log_id: str, patch: dict) -> dict:
    """部分更新饮食记录（仅更新 patch 中包含的字段）

    Args:
        log_id: 记录ID
        patch: 要更新的字段字典

    Returns:
        更新后的记录字典；若 ID 不存在返回 {error: ...}
    """
    storage = get_storage()
    updated = storage.patch_food_log(log_id, patch)
    if updated is None:
        return {"error": f"饮食记录不存在: {log_id}"}
    return updated.model_dump()


def delete_food_log(log_id: str) -> dict:
    """删除饮食记录

    Returns:
        包含 deleted 状态和 log_id 的字典
    """
    success = get_storage().delete_food_log(log_id)
    return {"deleted": success, "log_id": log_id}


# ──────────────────────────────────────────
# 用户档案
# ──────────────────────────────────────────

def save_user_profile(profile_data: dict) -> dict:
    """保存用户档案（本地单用户）

    Args:
        profile_data: 用户档案字典，符合 UserProfile 模型结构

    Returns:
        包含 user_id 和 saved_path 的字典
    """
    storage = get_storage()
    profile = UserProfile.model_validate(profile_data)
    return storage.save_user_profile(profile)


def load_user_profile(user_id: str = "default") -> dict:
    """加载用户档案

    Returns:
        用户档案字典；不存在返回默认成人档案 + {not_found: True}
    """
    storage = get_storage()
    profile = storage.load_user_profile(user_id)
    if profile is None:
        # 返回默认档案（成年男性，轻体力），供 RNI 计算兜底
        default = UserProfile(
            user_id=user_id,
            age=30,
            gender="male",
            height_cm=175,
            weight_kg=70,
            activity_level="轻度",
            goal="maintain",
            life_stage="成人",
        )
        result = default.model_dump()
        result["not_found"] = True
        return result
    return profile.model_dump()
