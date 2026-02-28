"""
从 RAG 数据库中选择一个 document_id，将其还原为 Markdown 文件。

主要用途：调试观察 MinerU + 切块后的还原效果。

行为说明：
- 从 PostgreSQL 的 documents / document_chunks 读数据
- 仅使用「父块 + 独立块」内容，还原 Markdown，避免 Parent/Child 重复
- 按 chunk_index 顺序拼接为一个 .md 文件，输出到 backend/rag/exports/

使用方式（在 backend 目录下）：
    cd backend
    python -m rag.export_markdown
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any, List, Tuple

import asyncpg


def _get_pg_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "aiweb")
    password = os.getenv("POSTGRES_PASSWORD", "aiweb")
    database = os.getenv("POSTGRES_DB", "aiweb")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def _sanitize_filename(name: str) -> str:
    name = name.strip() or "document"
    # 去掉路径分隔符等非法字符
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    # 控制长度，避免太长
    if len(name) > 80:
        name = name[:80]
    return name


async def _choose_document(conn: asyncpg.Connection) -> Tuple[str, str]:
    """
    交互式选择一个 document。
    返回: (document_id, filename)
    """
    rows: List[asyncpg.Record] = await conn.fetch(
        """
        SELECT id, filename, status, notebook_id, created_at
        FROM documents
        ORDER BY created_at DESC
        LIMIT 50
        """
    )
    if not rows:
        raise RuntimeError("当前数据库中没有任何 documents 记录。")

    print("最近的文档列表（最多 50 条）：")
    for idx, r in enumerate(rows, start=1):
        print(
            f"[{idx:2d}] id={r['id']} | status={r['status']} | "
            f"nb={r['notebook_id']} | filename={r['filename']}"
        )

    print()
    raw = input("请输入要导出的文档序号（或直接粘贴 document_id）：").strip()
    if not raw:
        raise RuntimeError("未选择任何文档。")

    # 支持直接输入 UUID
    if "-" in raw and len(raw) >= 8:
        doc_id = raw
        row = await conn.fetchrow(
            "SELECT id, filename FROM documents WHERE id = $1",
            doc_id,
        )
        if not row:
            raise RuntimeError(f"未找到指定 document_id: {doc_id}")
        return row["id"], row["filename"]

    # 按序号选择
    try:
        idx = int(raw)
    except ValueError:
        raise RuntimeError(f"非法输入: {raw!r}，既不是 UUID 也不是序号。")

    if idx < 1 or idx > len(rows):
        raise RuntimeError(f"序号超出范围: 1~{len(rows)}")

    chosen = rows[idx - 1]
    return chosen["id"], chosen["filename"]


async def _load_chunks(conn: asyncpg.Connection, doc_id: str) -> List[dict[str, Any]]:
    """
    加载指定文档的所有活跃切片，按 chunk_index 排序。
    """
    rows = await conn.fetch(
        """
        SELECT
            id,
            parent_chunk_id,
            chunk_index,
            content,
            chunk_type,
            page_numbers,
            is_active
        FROM document_chunks
        WHERE document_id = $1
          AND is_active = TRUE
        ORDER BY chunk_index
        """,
        doc_id,
    )
    return [dict(r) for r in rows]


def _reconstruct_markdown(chunks: List[dict[str, Any]]) -> str:
    """
    根据 chunk 列表还原 Markdown：
    - 优先使用「父块」：即被其它切片引用为 parent_chunk_id 的那些行
    - 其次使用「独立块」：parent_chunk_id IS NULL 且没有任何子块引用的行
    - 按 chunk_index 排序拼接 content，中间用空行分隔
    """
    if not chunks:
        return ""

    # 所有被引用的 parent id
    referenced_parent_ids = {
        c["parent_chunk_id"]
        for c in chunks
        if c.get("parent_chunk_id")
    }

    # 认为“父块”的行：自己的 id 出现在别人的 parent_chunk_id 中
    parents = [c for c in chunks if c["id"] in referenced_parent_ids]

    # 独立块：没有 parent_chunk_id，且自己也没有被引用（可能是短文、附录等）
    standalone = [
        c
        for c in chunks
        if c.get("parent_chunk_id") is None and c["id"] not in referenced_parent_ids
    ]

    def _key(c: dict[str, Any]) -> int:
        return int(c.get("chunk_index", 0))

    ordered = sorted(parents, key=_key) + sorted(standalone, key=_key)

    parts: List[str] = []
    for c in ordered:
        text = (c.get("content") or "").rstrip()
        if not text:
            continue
        parts.append(text)

    return "\n\n".join(parts) + "\n"


async def main() -> None:
    dsn = _get_pg_dsn()
    print(f"[RAG] 连接 PostgreSQL: {dsn}")
    conn = await asyncpg.connect(dsn)
    try:
        doc_id, filename = await _choose_document(conn)
        print(f"[RAG] 已选择文档: id={doc_id}, filename={filename}")

        chunks = await _load_chunks(conn, doc_id)
        if not chunks:
            print("[RAG] 该文档没有任何活跃切片，无法导出。")
            return

        markdown = _reconstruct_markdown(chunks)
        if not markdown.strip():
            print("[RAG] 还原结果为空文本，已放弃写入文件。")
            return

        base_dir = Path(__file__).resolve().parent
        export_dir = base_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        safe_name = _sanitize_filename(filename)
        out_path = export_dir / f"{doc_id[:8]}_{safe_name}.md"

        out_path.write_text(markdown, encoding="utf-8")
        print(f"[RAG] 已导出 Markdown 到: {out_path}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

