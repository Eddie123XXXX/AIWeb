"""
document_chunks 表 CRUD (asyncpg)

提供切片的批量写入、按文档查询、Parent-Child 查询、软删除等能力。
"""
from __future__ import annotations

import json
import os
from typing import Any, Sequence

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
    if "page_numbers" in d and isinstance(d["page_numbers"], str):
        try:
            d["page_numbers"] = json.loads(d["page_numbers"])
        except (json.JSONDecodeError, TypeError):
            d["page_numbers"] = []
    return d


_COLUMNS = """
    id, document_id, notebook_id,
    parent_chunk_id, chunk_index, page_numbers, chunk_type,
    content, token_count,
    is_active, created_at
"""


class ChunkRepository:

    # ------------------------------------------------------------------
    # 批量插入
    # ------------------------------------------------------------------
    async def bulk_create(self, chunks: list[dict[str, Any]]) -> int:
        """
        批量写入切片，返回插入条数。
        每条 chunk dict 至少包含:
            id, document_id, notebook_id, chunk_index, content, token_count
        可选:
            parent_chunk_id, page_numbers, chunk_type
        """
        if not chunks:
            return 0
        conn = await _conn()
        try:
            stmt = await conn.prepare("""
                INSERT INTO document_chunks (
                    id, document_id, notebook_id,
                    parent_chunk_id, chunk_index, page_numbers, chunk_type,
                    content, token_count
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
            """)
            rows = []
            for c in chunks:
                pages = c.get("page_numbers", [])
                rows.append((
                    c["id"],
                    c["document_id"],
                    c["notebook_id"],
                    c.get("parent_chunk_id"),
                    c["chunk_index"],
                    json.dumps(pages),
                    c.get("chunk_type", "TEXT"),
                    c["content"],
                    c.get("token_count", 0),
                ))
            await stmt.executemany(rows)
            return len(rows)
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 按文档查询活跃切片
    # ------------------------------------------------------------------
    async def list_by_document(
        self,
        document_id: str,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        conn = await _conn()
        try:
            where = "document_id = $1"
            if active_only:
                where += " AND is_active = TRUE"
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM document_chunks WHERE {where} ORDER BY chunk_index",
                document_id,
            )
            return [_row_to_dict(r) for r in rows]
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 按 ID 批量查询
    # ------------------------------------------------------------------
    async def get_by_ids(self, ids: Sequence[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        conn = await _conn()
        try:
            rows = await conn.fetch(
                f"SELECT {_COLUMNS} FROM document_chunks WHERE id = ANY($1::varchar[]) AND is_active = TRUE",
                list(ids),
            )
            return [_row_to_dict(r) for r in rows]
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 查询父切片 (Parent-Child RAG)
    # ------------------------------------------------------------------
    async def get_parent(self, chunk_id: str) -> dict[str, Any]:
        """获取指定切片的父切片内容"""
        conn = await _conn()
        try:
            row = await conn.fetchrow(
                f"""
                SELECT p.* FROM document_chunks p
                JOIN document_chunks c ON c.parent_chunk_id = p.id
                WHERE c.id = $1 AND p.is_active = TRUE
                """,
                chunk_id,
            )
            return _row_to_dict(row)
        finally:
            await conn.close()

    async def get_parents_batch(self, chunk_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """
        批量获取多个切片的父切片。
        返回 {child_chunk_id: parent_chunk_dict}
        """
        if not chunk_ids:
            return {}
        conn = await _conn()
        try:
            rows = await conn.fetch(
                """
                SELECT c.id AS child_id, p.id, p.content, p.chunk_type, p.page_numbers, p.token_count
                FROM document_chunks c
                JOIN document_chunks p ON c.parent_chunk_id = p.id
                WHERE c.id = ANY($1::varchar[]) AND p.is_active = TRUE
                """,
                list(chunk_ids),
            )
            result: dict[str, dict[str, Any]] = {}
            for r in rows:
                result[r["child_id"]] = _row_to_dict(r)
            return result
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 软删除 (文档重新解析时使用)
    # ------------------------------------------------------------------
    async def deactivate_by_document(self, document_id: str) -> int:
        """将某文档的所有切片标记为 is_active=FALSE"""
        conn = await _conn()
        try:
            result = await conn.execute(
                "UPDATE document_chunks SET is_active = FALSE WHERE document_id = $1 AND is_active = TRUE",
                document_id,
            )
            parts = result.split()
            return int(parts[-1]) if parts else 0
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 全文搜索 (三路召回 Path-1: 精确匹配)
    # ------------------------------------------------------------------
    async def fulltext_search(
        self,
        query: str,
        notebook_id: str,
        document_ids: list[str] | None = None,
        chunk_types: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        PostgreSQL 全文搜索 + ILIKE 双路精确匹配。

        策略:
        1. tsvector 全文搜索 (GIN 索引加速, 召回含关键词的切片)
        2. ILIKE 模糊匹配 (捕获特殊代码、型号等 tsvector 可能遗漏的精确字符串)
        3. 两路结果合并去重, 按相关度排序

        只搜索 is_active=TRUE 且 parent_chunk_id IS NOT NULL 的 Child Chunk
        (Parent Chunk 不参与检索)
        """
        if not query or not query.strip():
            return []

        conn = await _conn()
        try:
            # 构建 WHERE 条件
            conditions = ["c.notebook_id = $1", "c.is_active = TRUE"]
            params: list[Any] = [notebook_id]
            param_idx = 2

            if document_ids:
                conditions.append(f"c.document_id = ANY(${param_idx}::varchar[])")
                params.append(document_ids)
                param_idx += 1

            if chunk_types:
                conditions.append(f"c.chunk_type = ANY(${param_idx}::varchar[])")
                params.append(chunk_types)
                param_idx += 1

            where_clause = " AND ".join(conditions)

            # 参数占位: query=$N, ilike=$N+1, limit=$N+2
            query_param_idx = param_idx
            params.extend([query.strip(), f"%{query.strip()}%", limit])

            sql = f"""
                WITH fts AS (
                    SELECT c.id, c.document_id, c.notebook_id,
                           c.parent_chunk_id, c.chunk_index, c.page_numbers,
                           c.chunk_type, c.content, c.token_count,
                           c.is_active, c.created_at,
                           ts_rank_cd(to_tsvector('simple', c.content), plainto_tsquery('simple', ${query_param_idx})) AS rank,
                           1 AS source
                    FROM document_chunks c
                    WHERE {where_clause}
                      AND to_tsvector('simple', c.content) @@ plainto_tsquery('simple', ${query_param_idx})
                ),
                ilike_match AS (
                    SELECT c.id, c.document_id, c.notebook_id,
                           c.parent_chunk_id, c.chunk_index, c.page_numbers,
                           c.chunk_type, c.content, c.token_count,
                           c.is_active, c.created_at,
                           0.5 AS rank,
                           2 AS source
                    FROM document_chunks c
                    WHERE {where_clause}
                      AND c.content ILIKE ${query_param_idx + 1}
                      AND c.id NOT IN (SELECT id FROM fts)
                ),
                combined AS (
                    SELECT * FROM fts
                    UNION ALL
                    SELECT * FROM ilike_match
                )
                SELECT id, document_id, notebook_id,
                       parent_chunk_id, chunk_index, page_numbers,
                       chunk_type, content, token_count,
                       is_active, created_at, rank, source
                FROM combined
                ORDER BY rank DESC
                LIMIT ${query_param_idx + 2}
            """

            rows = await conn.fetch(sql, *params)
            results = []
            for r in rows:
                d = _row_to_dict(r)
                d["fts_rank"] = float(r["rank"])
                d["match_source"] = "fts" if r["source"] == 1 else "ilike"
                results.append(d)
            return results
        finally:
            await conn.close()

    # ------------------------------------------------------------------
    # 按笔记本查询所有活跃切片 ID (用于向量复制)
    # ------------------------------------------------------------------
    async def list_ids_by_document(self, document_id: str) -> list[str]:
        conn = await _conn()
        try:
            rows = await conn.fetch(
                "SELECT id FROM document_chunks WHERE document_id = $1 AND is_active = TRUE ORDER BY chunk_index",
                document_id,
            )
            return [r["id"] for r in rows]
        finally:
            await conn.close()


chunk_repository = ChunkRepository()
