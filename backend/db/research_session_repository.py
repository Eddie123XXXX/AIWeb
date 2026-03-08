"""
research_sessions 表 CRUD，使用 asyncpg 连接 PostgreSQL。
深度研究会话与 conversations 分离，前端召回历史时与聊天对话互不冲突。
依赖: 已执行 db/schema_research_sessions.sql 建表，且 users 表已存在。
"""
import json
import os
import ast
from typing import Any

import asyncpg


def _decode_json_field(value: Any) -> Any:
    """兼容 asyncpg 返回 json/jsonb 为字符串的情况。"""
    decoded = value
    for _ in range(3):
        if isinstance(decoded, (dict, list)) or decoded is None:
            return decoded
        if not isinstance(decoded, str):
            return decoded
        try:
            next_value = json.loads(decoded)
        except json.JSONDecodeError:
            try:
                next_value = ast.literal_eval(decoded)
            except (ValueError, SyntaxError):
                return decoded
        if next_value == decoded:
            return decoded
        decoded = next_value
    return decoded


def _normalize_reference(raw: Any) -> dict[str, Any] | None:
    """仓储层最小化归一化，避免依赖 deepresearch 包导致循环导入。"""
    if not isinstance(raw, dict):
        return None
    title = raw.get("title") or raw.get("source") or raw.get("source_name") or raw.get("name") or raw.get("url") or raw.get("source_url") or "N/A"
    link = raw.get("link") or raw.get("url") or raw.get("source_url") or ""
    content = raw.get("content") or raw.get("snippet") or raw.get("summary") or ""
    source = raw.get("source") or raw.get("source_name") or raw.get("source_type") or title
    return {
        "id": raw.get("id"),
        "title": str(title or "N/A"),
        "link": str(link or ""),
        "content": str(content or "")[:500],
        "source": str(source or "N/A"),
    }


def _merge_unique_references(existing: list[dict[str, Any]] | None, incoming: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """按 link+title 去重并重排 id。"""
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in (existing or []) + (incoming or []):
        normalized = _normalize_reference(item)
        if normalized is None:
            continue
        key = (
            (normalized.get("link") or "").strip().lower(),
            (normalized.get("title") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized)
    for idx, item in enumerate(merged, start=1):
        item["id"] = idx
    return merged


def _get_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "aiweb")
    password = os.getenv("POSTGRES_PASSWORD", "aiweb")
    database = os.getenv("POSTGRES_DB", "aiweb")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def _get_conn() -> asyncpg.Connection:
    return await asyncpg.connect(_get_dsn())


def _row_to_session(row: asyncpg.Record) -> dict[str, Any]:
    """将 research_sessions 一行转为字典。sources 以 references 键返回供前端使用。"""
    ui_state = _decode_json_field(row["ui_state"] if "ui_state" in row and row["ui_state"] is not None else None)
    sources = _decode_json_field(row["sources"] if "sources" in row and row["sources"] is not None else None)
    normalized_refs = _merge_unique_references(
        sources if isinstance(sources, list) else [],
        (ui_state or {}).get("references") if isinstance(ui_state, dict) and isinstance((ui_state or {}).get("references"), list) else [],
    )
    out = {
        "id": row["id"],
        "user_id": row["user_id"],
        "query": row["query"],
        "title": row["title"],
        "status": row["status"],
        "final_report": row["final_report"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "deleted_at": row["deleted_at"],
    }
    if normalized_refs:
        out["references"] = normalized_refs
    elif isinstance(ui_state, dict) and isinstance(ui_state.get("search_results"), list):
        out["references"] = _merge_unique_references([], ui_state.get("search_results"))
    if ui_state is not None:
        out["ui_state"] = ui_state
    return out


class ResearchSessionRepository:
    """深度研究会话表仓储。"""

    async def create(
        self,
        session_id: str,
        user_id: int,
        query: str,
        title: str | None = None,
        status: str = "running",
    ) -> dict[str, Any]:
        """创建一条研究会话；session_id 建议使用 UUID，与 Deep Research 流式请求一致。"""
        conn = await _get_conn()
        try:
            title = title or (query[:200] + ("..." if len(query) > 200 else "")) if query else "深度研究"
            row = await conn.fetchrow(
                """
                INSERT INTO research_sessions (id, user_id, query, title, status)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, user_id, query, title, status, final_report, sources, ui_state, created_at, updated_at, deleted_at
                """,
                session_id,
                user_id,
                query,
                title,
                status,
            )
            return _row_to_session(row)
        finally:
            await conn.close()

    async def get_by_id(self, session_id: str) -> dict[str, Any] | None:
        """按会话 ID 查询，已软删除的不返回。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, query, title, status, final_report, sources, ui_state, created_at, updated_at, deleted_at
                FROM research_sessions WHERE id = $1 AND deleted_at IS NULL
                """,
                session_id,
            )
            return _row_to_session(row) if row else None
        finally:
            await conn.close()

    async def list_by_user(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """按用户查询研究会话列表，按 updated_at 倒序，排除已软删除。"""
        conn = await _get_conn()
        try:
            rows = await conn.fetch(
                """
                SELECT id, user_id, query, title, status, final_report, sources, ui_state, created_at, updated_at, deleted_at
                FROM research_sessions
                WHERE user_id = $1 AND deleted_at IS NULL
                ORDER BY updated_at DESC
                LIMIT $2 OFFSET $3
                """,
                user_id,
                limit,
                offset,
            )
            return [_row_to_session(r) for r in rows]
        finally:
            await conn.close()

    async def update_status(
        self,
        session_id: str,
        status: str,
        final_report: str | None = None,
        title: str | None = None,
        references: list[dict[str, Any]] | None = None,
        ui_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """更新会话状态与报告快照；完成时可写 final_report、references、ui_state。已软删除的不更新。"""
        conn = await _get_conn()
        try:
            updates = ["status = $1", "updated_at = CURRENT_TIMESTAMP"]
            args: list[Any] = [status]
            n = 2
            if final_report is not None:
                updates.append(f"final_report = ${n}")
                args.append(final_report)
                n += 1
            if title is not None:
                updates.append(f"title = ${n}")
                args.append(title)
                n += 1
            if references is not None:
                updates.append(f"sources = ${n}::jsonb")
                args.append(json.dumps(references))
                n += 1
            if ui_state is not None:
                updates.append(f"ui_state = ${n}::jsonb")
                args.append(json.dumps(ui_state))
                n += 1
            args.append(session_id)
            pid = len(args)
            row = await conn.fetchrow(
                f"""
                UPDATE research_sessions SET {", ".join(updates)}
                WHERE id = ${pid} AND deleted_at IS NULL
                RETURNING id, user_id, query, title, status, final_report, sources, ui_state, created_at, updated_at, deleted_at
                """,
                *args,
            )
            return _row_to_session(row) if row else None
        finally:
            await conn.close()

    async def update_progress(
        self,
        session_id: str,
        *,
        status: str | None = None,
        ui_state_update: dict[str, Any] | None = None,
        append_panel_log: dict[str, Any] | None = None,
        final_report: str | None = None,
        references: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """增量更新进度：合并 ui_state、可选追加 panel_log、更新 status/final_report/sources，用于每步实时落库与断点恢复。已软删除的不更新。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, status, ui_state, final_report, sources
                FROM research_sessions WHERE id = $1 AND deleted_at IS NULL
                """,
                session_id,
            )
            if not row:
                return None
            new_status = status if status is not None else row["status"]
            current_ui = _decode_json_field(row["ui_state"])
            existing_ui = current_ui if isinstance(current_ui, dict) else {}
            new_ui = {**existing_ui, **(ui_state_update or {})}
            if append_panel_log is not None:
                new_ui["panel_log"] = list(new_ui.get("panel_log") or []) + [append_panel_log]
            new_report = final_report if final_report is not None else row["final_report"]
            current_sources = _decode_json_field(row["sources"])
            new_sources = references if references is not None else current_sources
            row2 = await conn.fetchrow(
                """
                UPDATE research_sessions
                SET status = $1, ui_state = $2::jsonb, final_report = $3, sources = $4::jsonb, updated_at = CURRENT_TIMESTAMP
                WHERE id = $5 AND deleted_at IS NULL
                RETURNING id, user_id, query, title, status, final_report, sources, ui_state, created_at, updated_at, deleted_at
                """,
                new_status,
                json.dumps(new_ui),
                new_report,
                json.dumps(new_sources) if new_sources is not None else None,
                session_id,
            )
            return _row_to_session(row2) if row2 else None
        finally:
            await conn.close()

    async def update_ui_state(self, session_id: str, ui_state: dict[str, Any]) -> dict[str, Any] | None:
        """合并更新会话的 ui_state（用于前端在 research_complete 后提交思考过程等）。已软删除的不更新。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                SELECT ui_state FROM research_sessions WHERE id = $1 AND deleted_at IS NULL
                """,
                session_id,
            )
            if not row:
                return None
            existing = _decode_json_field(row["ui_state"])
            if not isinstance(existing, dict):
                existing = {}
            merged = {**existing, **ui_state}
            row2 = await conn.fetchrow(
                """
                UPDATE research_sessions SET ui_state = $1::jsonb, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2 AND deleted_at IS NULL
                RETURNING id, user_id, query, title, status, final_report, sources, ui_state, created_at, updated_at, deleted_at
                """,
                json.dumps(merged),
                session_id,
            )
            return _row_to_session(row2) if row2 else None
        finally:
            await conn.close()

    async def update_report(self, session_id: str, final_report: str) -> dict[str, Any] | None:
        """仅更新会话的 final_report（用户编辑后保存）。已软删除的不更新。"""
        conn = await _get_conn()
        try:
            row = await conn.fetchrow(
                """
                UPDATE research_sessions SET final_report = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2 AND deleted_at IS NULL
                RETURNING id, user_id, query, title, status, final_report, sources, ui_state, created_at, updated_at, deleted_at
                """,
                final_report,
                session_id,
            )
            return _row_to_session(row) if row else None
        finally:
            await conn.close()

    async def update_outline_state(
        self,
        session_id: str,
        *,
        outline_draft_full: list[dict[str, Any]] | None = None,
        editable_outline: list[dict[str, Any]] | None = None,
        active_outline: list[dict[str, Any]] | None = None,
        outline: list[dict[str, Any]] | None = None,
        research_questions: list[str] | None = None,
        outline_approval_status: str | None = None,
        awaiting_user_input: str | None = None,
        phase: str | None = None,
        phase_detail: str | None = None,
        research_steps: list[dict[str, Any]] | None = None,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        """更新章节框架相关状态，统一维护 waiting_approval / approved outline 等字段。"""
        ui_state_update: dict[str, Any] = {}
        if outline_draft_full is not None:
            ui_state_update["outline_draft_full"] = outline_draft_full
        if editable_outline is not None:
            ui_state_update["editable_outline"] = editable_outline
        if active_outline is not None:
            ui_state_update["active_outline"] = active_outline
        if outline is not None:
            ui_state_update["outline"] = outline
        if research_questions is not None:
            ui_state_update["research_questions"] = research_questions
        if outline_approval_status is not None:
            ui_state_update["outline_approval_status"] = outline_approval_status
        if awaiting_user_input is not None:
            ui_state_update["awaiting_user_input"] = awaiting_user_input
        if phase is not None:
            ui_state_update["phase"] = phase
        if phase_detail is not None:
            ui_state_update["phase_detail"] = phase_detail
        if research_steps is not None:
            ui_state_update["research_steps"] = research_steps
        return await self.update_progress(
            session_id,
            status=status,
            ui_state_update=ui_state_update,
        )

    async def touch(self, session_id: str) -> bool:
        """仅刷新 updated_at。返回是否更新了行。"""
        conn = await _get_conn()
        try:
            result = await conn.execute(
                "UPDATE research_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = $1 AND deleted_at IS NULL",
                session_id,
            )
            return result.split()[-1] == "1"
        finally:
            await conn.close()

    async def soft_delete(self, session_id: str) -> bool:
        """软删除会话。返回是否实际更新了行。"""
        conn = await _get_conn()
        try:
            result = await conn.execute(
                """
                UPDATE research_sessions SET deleted_at = CURRENT_TIMESTAMP
                WHERE id = $1 AND deleted_at IS NULL
                """,
                session_id,
            )
            return result.split()[-1] == "1"
        finally:
            await conn.close()


research_session_repository = ResearchSessionRepository()
