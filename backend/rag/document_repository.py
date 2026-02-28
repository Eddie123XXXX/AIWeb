"""
documents 表 CRUD (asyncpg)

提供文档元数据的全生命周期管理：创建、查重、状态流转、列表查询。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional, Sequence

import asyncpg


def _get_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "aiweb")
    password = os.getenv("POSTGRES_PASSWORD", "aiweb")
    database = os.getenv("POSTGRES_DB", "aiweb")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def _conn() -> asyncpg.Connection:
    return await asyncpg.connect(_get_dsn())


def _row_to_dict(row: asyncpg.Record | None) -> dict[str, Any]:
    if row is None:
        return {}
    d = dict(row)
    if "metadata" in d and isinstance(d["metadata"], str):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d


_COLUMNS = """
    id, notebook_id, user_id,
    filename, file_hash, byte_size, storage_path,
    parser_engine, parser_version, chunking_strategy,
    status, error_log, metadata, summary,
    created_at, updated_at
"""


class DocumentRepository:

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------
    async def create(
        self,
        *,
        id: str,
        notebook_id: str,
        user_id: int,
        filename: str,
        file_hash: str,
        byte_size: int,
        storage_path: str,
        parser_engine: str = "MinerU",
        parser_version: str = "v1.0.0",
        chunking_strategy: str = "semantic_recursive",
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        conn = await _conn()
        try:
            row = await conn.fetchrow(
                f"""
                INSERT INTO documents (
                id, notebook_id, user_id,
                filename, file_hash, byte_size, storage_path,
                parser_engine, parser_version, chunking_strategy,
                metadata, summary
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, NULL
                )
                RETURNING {_COLUMNS}
                """,
                id, notebook_id, user_id,
                filename, file_hash, byte_size, storage_path,
                parser_engine, parser_version, chunking_strategy,
                json.dumps(metadata, ensure_ascii=False) if metadata else None,
            )
            return _row_to_dict(row)
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 查重 (同笔记本同哈希)
    # ------------------------------------------------------------------
    async def find_by_notebook_and_hash(
        self, notebook_id: str, file_hash: str
    ) -> dict[str, Any]:
        conn = await _conn()
        try:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM documents WHERE notebook_id = $1 AND file_hash = $2",
                notebook_id, file_hash,
            )
            return _row_to_dict(row)
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 跨笔记本查哈希 (用于秒传复制)
    # ------------------------------------------------------------------
    async def find_any_by_hash(self, file_hash: str) -> dict[str, Any]:
        """找到任意一份已 READY 的同哈希文档 (用于跨笔记本秒传)"""
        conn = await _conn()
        try:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM documents WHERE file_hash = $1 AND status = 'READY' LIMIT 1",
                file_hash,
            )
            return _row_to_dict(row)
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 按 ID 查询
    # ------------------------------------------------------------------
    async def get_by_id(self, doc_id: str) -> dict[str, Any]:
        conn = await _conn()
        try:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM documents WHERE id = $1", doc_id,
            )
            return _row_to_dict(row)
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 状态流转
    # ------------------------------------------------------------------
    async def update_status(
        self,
        doc_id: str,
        status: str,
        error_log: str | None = None,
    ) -> dict[str, Any]:
        conn = await _conn()
        try:
            row = await conn.fetchrow(
                f"""
                UPDATE documents
                SET status = $2, error_log = $3, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                RETURNING {_COLUMNS}
                """,
                doc_id, status, error_log,
            )
            return _row_to_dict(row)
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 笔记本下文档列表
    # ------------------------------------------------------------------
    async def list_by_notebook(
        self,
        notebook_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conn = await _conn()
        try:
            rows = await conn.fetch(
                f"""
                SELECT {_COLUMNS}
                FROM documents
                WHERE notebook_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                notebook_id, limit, offset,
            )
            return [_row_to_dict(r) for r in rows]
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 文档总结（来源指南）
    # ------------------------------------------------------------------
    async def update_summary(self, doc_id: str, summary: str) -> bool:
        conn = await _conn()
        try:
            result = await conn.execute(
                "UPDATE documents SET summary = $2, updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                doc_id, summary,
            )
            return result.endswith("1")
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 删除文档 (级联删除 chunks)
    # ------------------------------------------------------------------
    async def delete(self, doc_id: str) -> bool:
        conn = await _conn()
        try:
            result = await conn.execute(
                "DELETE FROM documents WHERE id = $1", doc_id,
            )
            return result.endswith("1")
        finally:
            await conn.close()


document_repository = DocumentRepository()
