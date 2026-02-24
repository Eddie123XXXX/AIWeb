"""
基于艾宾浩斯遗忘曲线的记忆遗忘模块。

长期不被召回的记忆会随时间衰减，保持率低于阈值时可软删除，释放存储并避免无关记忆干扰。
遗忘时同步删除 Milvus 中对应向量，避免孤儿数据。
"""
import logging
from datetime import datetime, timezone
from typing import Any

from db.agent_memory_repository import agent_memory_repository

logger = logging.getLogger("memory")
from memory.vector_store import delete_memories


class EbbinghausForgetting:
    """
    基于艾宾浩斯遗忘曲线的记忆保持率计算。

    - base_retention: 基础遗忘率（如 0.9 表示每小时衰减到 0.9）
    - strengthening_factor: 访问次数的强化系数，每次召回会提高抗遗忘能力
    """

    def __init__(
        self,
        base_retention: float = 0.9,
        strengthening_factor: float = 1.5,
    ):
        self.base_retention = base_retention
        self.strengthening_factor = strengthening_factor

    def calculate_retention(
        self,
        memory: dict[str, Any],
        current_time: datetime | None = None,
    ) -> float:
        """
        计算记忆保持率。

        - memory: 记忆 dict，需含 last_accessed_at、access_count、importance_score
        - memory_type=reflection 的记忆可设置豁免（不参与遗忘）
        """
        now = current_time or datetime.now(timezone.utc)
        last_accessed = memory.get("last_accessed_at") or memory.get("created_at")
        if not last_accessed:
            return 1.0

        if last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        hours_since_access = (now - last_accessed).total_seconds() / 3600
        access_count = int(memory.get("access_count") or 0)
        importance = float(memory.get("importance_score") or 0.0)

        # 访问次数的强化效应：越常被召回，遗忘越慢
        strength_multiplier = self.strengthening_factor ** access_count

        # 艾宾浩斯曲线：时间越长，保持率越低
        retention = self.base_retention ** (
            hours_since_access / (24 * strength_multiplier)
        )

        # 重要性加成：高重要性记忆更抗遗忘
        retention *= 0.5 + 0.5 * importance

        return max(0.0, min(1.0, retention))

    def cleanup_forgotten(
        self,
        memories: list[dict[str, Any]],
        threshold: float = 0.1,
        current_time: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        将记忆按保持率分为保留与遗忘。

        - threshold: 保持率低于此值的记忆视为已遗忘
        - 返回 (retained, forgotten)
        """
        now = current_time or datetime.now(timezone.utc)
        retained: list[dict[str, Any]] = []
        forgotten: list[dict[str, Any]] = []
        for m in memories:
            r = self.calculate_retention(m, now)
            if r >= threshold:
                retained.append(m)
            else:
                forgotten.append(m)
        return retained, forgotten


async def cleanup_forgotten_memories(
    user_id: int,
    *,
    base_retention: float = 0.9,
    strengthening_factor: float = 1.5,
    threshold: float = 0.1,
    exclude_memory_types: list[str] | None = None,
) -> int:
    """
    定期清理：将长期不被召回、保持率低于阈值的记忆软删除。

    - user_id: 用户 ID
    - base_retention: 艾宾浩斯基础遗忘率
    - strengthening_factor: 访问强化系数
    - threshold: 保持率低于此值的记忆将被软删除
    - exclude_memory_types: 不参与遗忘的记忆类型（如 ["reflection"]）

    返回：实际软删除的记忆条数。
    """
    logger.info(
        "[Memory] 遗忘清理 cleanup_forgotten_memories | user_id=%s threshold=%.2f",
        user_id,
        threshold,
    )
    exclude = set(exclude_memory_types or [])

    memories = await agent_memory_repository.list_by_user_for_retention(user_id)
    if not memories:
        return 0

    # 过滤豁免类型
    to_check = [
        m for m in memories
        if m.get("memory_type") not in exclude
    ]
    if not to_check:
        return 0

    ebbinghaus = EbbinghausForgetting(
        base_retention=base_retention,
        strengthening_factor=strengthening_factor,
    )
    _, forgotten = ebbinghaus.cleanup_forgotten(to_check, threshold=threshold)

    if not forgotten:
        return 0

    ids = [m["id"] for m in forgotten]
    deleted = await agent_memory_repository.soft_delete_many(ids)
    if deleted > 0:
        logger.info("[Memory] 遗忘清理结果 | 软删除 %d 条", deleted)

    # 同步删除 Milvus 中对应向量，避免孤儿数据占用存储并干扰检索
    if deleted > 0:
        try:
            await delete_memories(ids=ids)
        except Exception as e:
            logger.warning("[Memory] 遗忘 Milvus 删除异常: %s", e)

    return deleted
