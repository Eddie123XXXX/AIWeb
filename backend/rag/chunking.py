"""
版面感知切块引擎 (Layout-Aware Chunking)

基于 MinerU 解析产出的结构化 JSON Block 实现真正的 Parent-Child 语义切块:

Parent Chunk (父块):
  以文档标题层级 (Heading) 为界限。例如从 "2.1 架构设计" 到 "2.2 部署方案"
  之间的所有内容合并为一个 Parent Chunk，提供完整全局上下文给 LLM。
  父块 **不进入 Milvus**，只存 PostgreSQL。

Child Chunk (子块):
  父块内部每一个自然段落 (text)、每一张表格 (table)、每一个图片描述
  (image_caption) 各自作为独立 Child Chunk。短小精悍，专门用于 Dense+Sparse
  向量检索。子块进入 Milvus + PostgreSQL 双写。

防踩坑:
  - 表格防撕裂: MinerU 已将完整表格识别为独立 Block，整块写入 chunk_type=TABLE
  - 大百科全书效应: Parent Chunk 不做 Embedding，避免长文本语义模糊
  - Markdown 降级: 若 MinerU 只返回 Markdown (无结构化 JSON)，自动降级为标题分段
"""
from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Chunk:
    """切片数据对象"""
    id: str
    document_id: str
    notebook_id: str
    chunk_index: int
    content: str
    token_count: int
    chunk_type: str = "TEXT"
    page_numbers: list[int] = field(default_factory=list)
    parent_chunk_id: Optional[str] = None
    is_parent: bool = False


# ---------------------------------------------------------------------------
# Token 计数
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """
    近似 token 估算:
    - 英文: ~4 字符/token
    - 中文: ~1.5 字符/token
    """
    if not text:
        return 0
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    other_chars = len(text) - cn_chars
    return int(cn_chars / 1.5 + other_chars / 4) + 1


def get_content_for_embedding(
    chunk: "Chunk | dict[str, Any]",
    max_tokens: int | None = None,
) -> str:
    """
    巨型 Chunk 护栏: 获取用于 Embedding 的文本。

    当表格/段落超过 Embedding 模型最大 Token 限制时，截断以避免向量失真。
    完整 content 仍保留在 Chunk 中，检索时返回完整内容给 LLM。

    图片类 (IMAGE_CAPTION): 仅用 VLM 生成的文字做 embedding，不用图片 URL，
    因 content 存为 "url\\nVLM文字"，取第一行之后部分参与向量化。
    """
    import os
    if max_tokens is None:
        max_tokens = int(os.getenv("RAG_MAX_EMBEDDING_TOKENS", "2048"))

    content = chunk.content if hasattr(chunk, "content") else chunk.get("content", "")
    chunk_type = (chunk.chunk_type if hasattr(chunk, "chunk_type") else chunk.get("chunk_type", "") or "").strip().upper()

    # 图片类 chunk：仅用 VLM 生成的文字做 embedding，不用 URL（content 格式为 url\nVLM文字）
    if chunk_type == "IMAGE_CAPTION" and content:
        if "\n" in content:
            content = content.split("\n", 1)[1].strip()
        else:
            content = ""  # 仅 URL 或 [图片] 时不做语义向量化

    if not content or estimate_tokens(content) <= max_tokens:
        return content

    # 巨型 Chunk: 截断保留前 max_tokens 对应字符，加省略提示
    approx_char_per_token = 3
    max_chars = int(max_tokens * approx_char_per_token) - 20  # 留空间给省略符
    truncated = content[:max_chars].rstrip()
    suffix = "\n\n[... 内容过长已截断，完整内容检索时仍会返回 ...]"
    return truncated + suffix


# ---------------------------------------------------------------------------
# 核心: 版面感知切块 (Layout-Aware Chunking)
# ---------------------------------------------------------------------------

# MinerU 完整 type 清单：噪声丢弃 / 原子块聚合 / 常规文本
NOISE_TYPES = frozenset({"header", "footer", "page_number", "phonetic"})
TABLE_FAMILY = frozenset({"table_caption", "table", "table_footnote"})
IMAGE_FAMILY = frozenset({"image", "image_caption", "image_footnote", "image_body"})
CODE_FAMILY = frozenset({"code", "code_caption", "algorithm"})


def _get_block_display_text(block: dict[str, Any], block_type: str) -> str:
    """从 block 中取出用于展示/入库的文本（兼容 pipeline 与 VLM 字段名）"""
    # 表格 VLM 可能用 table_body
    if block_type in TABLE_FAMILY:
        return (block.get("table_body") or block.get("text") or block.get("content") or "").strip()
    return (block.get("text") or block.get("content") or "").strip()


def _block_type_to_chunk_type(block_type: str) -> str:
    """将 MinerU block type 映射为 chunk_type"""
    mapping = {
        "text": "TEXT",
        "title": "TEXT",
        "equation": "TEXT",
        "interline_equation": "TEXT",
        "table": "TABLE",
        "table_caption": "TABLE",
        "table_footnote": "TABLE",
        "image": "IMAGE_CAPTION",
        "image_caption": "IMAGE_CAPTION",
        "image_footnote": "IMAGE_CAPTION",
        "image_body": "IMAGE_CAPTION",
        "code": "CODE",
        "code_caption": "CODE",
        "algorithm": "CODE",
        "list": "TEXT",
        "ref_text": "TEXT",
        "page_footnote": "TEXT",
        "aside_text": "TEXT",
    }
    return mapping.get(block_type, "TEXT")


def _normalize_block_type(raw_type: Any) -> str:
    """统一 MinerU / mineru.net 各版本的 block type，便于 IMAGE_FAMILY 等正确识别"""
    if isinstance(raw_type, int):
        type_map = {0: "text", 1: "title", 2: "text", 3: "table", 4: "image", 5: "image_caption"}
        return type_map.get(raw_type, "text")
    s = (str(raw_type) or "text").strip().lower()
    if s in ("title", "heading", "header"):
        return "title"
    if s in ("table",):
        return "table"
    if s in ("image", "figure", "image_body", "img", "picture"):
        return "image"
    if s in ("image_caption", "figure_caption", "caption"):
        return "image_caption"
    if s in ("interline_equation", "equation"):
        return "interline_equation"
    return s if s else "text"


def _normalize_page_idx(page_idx: Any) -> list[int]:
    """统一 MinerU 各版本的 page_idx 格式为 list[int]"""
    if isinstance(page_idx, int):
        return [page_idx]
    if isinstance(page_idx, (list, tuple)):
        return [int(p) for p in page_idx]
    return []


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except Exception:
        return default


_PSEUDO_TITLE_PATTERNS = [
    # Markdown / 编号标题 / 中文章节标题
    re.compile(r"^\s{0,3}#{1,6}\s+\S+"),
    re.compile(r"^\s*(第[一二三四五六七八九十百千万0-9]+[章节部分篇])"),
    re.compile(r"^\s*(\d+(?:\.\d+){0,3}|[一二三四五六七八九十]+)\s*[、.)）．]\s*\S+"),
    re.compile(r"^\s*(附录|目录|前言|引言|总结|结论|参考文献|致谢)\s*$"),
]


def _is_pseudo_title(text: str, max_chars: int) -> bool:
    """识别 MinerU 漏标为 text 的标题行。"""
    s = (text or "").strip()
    if not s:
        return False
    if "\n" in s:
        return False
    if len(s) > max_chars:
        return False
    if re.search(r"[。！？!?；;]$", s):
        return False
    return any(p.search(s) for p in _PSEUDO_TITLE_PATTERNS)


def process_mineru_blocks(
    blocks: list[dict[str, Any]],
    document_id: str,
    notebook_id: str,
    max_child_tokens: int = 512,
    max_parent_tokens: int | None = None,
) -> list[Chunk]:
    """
    版面感知切块：将 MinerU 结构化 JSON Block 转化为 Parent-Child 切片集合。

    Args:
        blocks: MinerU 解析产出的 Block 列表，每个 Block 包含:
            - type: "title" | "text" | "table" | "image" | "image_caption" ...
            - text: 文本内容 (Markdown 格式)
            - page_idx: 页码 (int 或 list[int])
            - img_path: (可选) 图片路径
        document_id: 文档 ID
        notebook_id: 笔记本 ID
        max_child_tokens: 子块最大 token 数 (超过时递归分割)
        max_parent_tokens: 父块最大 token 数。超过时强制截断 parent（即使未遇到 title）

    环境变量:
        RAG_PARENT_MAX_TOKENS=2000
        RAG_PARENT_SPLIT_ENABLE_PSEUDO_TITLE=true
        RAG_PARENT_SPLIT_ENABLE_PAGE_BREAK=true
        RAG_PARENT_SPLIT_ENABLE_TYPE_SHIFT=true
        RAG_PARENT_SPLIT_MIN_PARENT_TOKENS=600
        RAG_PARENT_SPLIT_MIN_CHILDREN=3
        RAG_PARENT_PSEUDO_TITLE_MAX_CHARS=64

    Returns:
        Parent + Child Chunk 列表。
        Parent: is_parent=True, parent_chunk_id=None (不进 Milvus)
        Child: is_parent=False, parent_chunk_id=<parent_id> (进 Milvus)
    """
    if not blocks:
        return []
    if max_parent_tokens is None:
        try:
            max_parent_tokens = int(os.getenv("RAG_PARENT_MAX_TOKENS", "2000"))
        except Exception:
            max_parent_tokens = 2000
    max_parent_tokens = max(256, max_parent_tokens)
    split_on_pseudo_title = _env_bool("RAG_PARENT_SPLIT_ENABLE_PSEUDO_TITLE", True)
    split_on_page_break = _env_bool("RAG_PARENT_SPLIT_ENABLE_PAGE_BREAK", True)
    split_on_type_shift = _env_bool("RAG_PARENT_SPLIT_ENABLE_TYPE_SHIFT", True)
    split_min_parent_tokens = max(128, _env_int("RAG_PARENT_SPLIT_MIN_PARENT_TOKENS", 600))
    split_min_children = max(1, _env_int("RAG_PARENT_SPLIT_MIN_CHILDREN", 3))
    pseudo_title_max_chars = max(16, _env_int("RAG_PARENT_PSEUDO_TITLE_MAX_CHARS", 64))

    all_chunks: list[Chunk] = []
    chunk_index = 0

    # 状态指针: 当前正在构建的 Parent Chunk
    current_parent_id: str = str(uuid.uuid4())
    current_parent_content: list[str] = []
    current_parent_pages: set[int] = set()
    current_parent_tokens: int = 0
    pending_children: list[Chunk] = []
    last_non_heading_block_type: str | None = None

    def flush_parent():
        """将当前收集的父块内容打包，并把暂存的子块关联上"""
        nonlocal current_parent_id, current_parent_content, current_parent_pages
        nonlocal current_parent_tokens, pending_children, chunk_index

        if current_parent_content:
            parent = Chunk(
                id=current_parent_id,
                document_id=document_id,
                notebook_id=notebook_id,
                chunk_index=chunk_index,
                content="\n\n".join(current_parent_content),
                token_count=estimate_tokens("\n\n".join(current_parent_content)),
                chunk_type="TEXT",
                page_numbers=sorted(current_parent_pages),
                parent_chunk_id=None,
                is_parent=True,
            )
            all_chunks.append(parent)
            chunk_index += 1

            for child in pending_children:
                child.parent_chunk_id = current_parent_id
                child.chunk_index = chunk_index
                all_chunks.append(child)
                chunk_index += 1
        elif pending_children:
            for child in pending_children:
                child.chunk_index = chunk_index
                all_chunks.append(child)
                chunk_index += 1

        # 重置
        current_parent_id = str(uuid.uuid4())
        current_parent_content = []
        current_parent_pages = set()
        current_parent_tokens = 0
        pending_children = []

    # 原子块收集缓冲：表格/图片/代码 按族聚合后再打成一块
    pending_table_blocks: list[tuple[dict[str, Any], list[int]]] = []
    pending_image_blocks: list[tuple[dict[str, Any], list[int]]] = []
    pending_code_blocks: list[tuple[dict[str, Any], list[int]]] = []

    def flush_pending_table() -> None:
        nonlocal current_parent_content, current_parent_pages, current_parent_tokens
        nonlocal pending_children, pending_table_blocks, last_non_heading_block_type
        if not pending_table_blocks:
            return
        parts = []
        all_pages: set[int] = set()
        for blk, pidx in pending_table_blocks:
            t = _get_block_display_text(blk, blk.get("type", "table"))
            if t:
                parts.append(t)
            all_pages.update(pidx)
        combined = "\n\n".join(parts).strip()
        pending_table_blocks.clear()
        if not combined:
            return
        current_parent_content.append(combined)
        current_parent_pages.update(all_pages)
        current_parent_tokens += estimate_tokens(combined)
        child = Chunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            notebook_id=notebook_id,
            chunk_index=0,
            content=combined,
            token_count=estimate_tokens(combined),
            chunk_type="TABLE",
            page_numbers=sorted(all_pages),
            is_parent=False,
        )
        pending_children.append(child)
        last_non_heading_block_type = "table"

    def flush_pending_image() -> None:
        nonlocal current_parent_content, current_parent_pages, current_parent_tokens
        nonlocal pending_children, pending_image_blocks, last_non_heading_block_type
        if not pending_image_blocks:
            return
        # 有 _image_url 的 block：每个图片一个 chunk，内容为图片 URL（可选追加 VLM 说明）
        blocks_with_url = [(blk, pidx) for blk, pidx in pending_image_blocks if blk.get("_image_url")]
        if blocks_with_url:
            for blk, pidx in blocks_with_url:
                url = blk.get("_image_url", "")
                text = _get_block_display_text(blk, blk.get("type", "image_caption"))
                content = url + ("\n" + text if text else "")
                current_parent_content.append(content)
                current_parent_pages.update(pidx)
                current_parent_tokens += estimate_tokens(content)
                child = Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    notebook_id=notebook_id,
                    chunk_index=0,
                    content=content,
                    token_count=estimate_tokens(content),
                    chunk_type="IMAGE_CAPTION",
                    page_numbers=sorted(pidx),
                    is_parent=False,
                )
                pending_children.append(child)
            # 剩余无 URL 的 block 合并为一个 chunk（兜底）
            rest = [(blk, pidx) for blk, pidx in pending_image_blocks if not blk.get("_image_url")]
            if rest:
                parts = []
                all_pages_rest = set()
                for blk, pidx in rest:
                    t = _get_block_display_text(blk, blk.get("type", "image_caption"))
                    if t:
                        parts.append(t)
                    all_pages_rest.update(pidx)
                combined_rest = "\n\n".join(parts).strip() if parts else "[图片]"
                current_parent_content.append(combined_rest)
                current_parent_pages.update(all_pages_rest)
                current_parent_tokens += estimate_tokens(combined_rest)
                child_rest = Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    notebook_id=notebook_id,
                    chunk_index=0,
                    content=combined_rest,
                    token_count=estimate_tokens(combined_rest),
                    chunk_type="IMAGE_CAPTION",
                    page_numbers=sorted(all_pages_rest),
                    is_parent=False,
                )
                pending_children.append(child_rest)
            pending_image_blocks.clear()
            last_non_heading_block_type = "image_caption"
            return
        # 无 _image_url：沿用原逻辑，合并为一块
        parts = []
        all_pages = set()
        for blk, pidx in pending_image_blocks:
            t = _get_block_display_text(blk, blk.get("type", "image_caption"))
            if t:
                parts.append(t)
            all_pages.update(pidx)
        combined = "\n\n".join(parts).strip() if parts else ""
        pending_image_blocks.clear()
        if not combined:
            combined = "[图片]"
        current_parent_content.append(combined)
        current_parent_pages.update(all_pages)
        current_parent_tokens += estimate_tokens(combined)
        child = Chunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            notebook_id=notebook_id,
            chunk_index=0,
            content=combined,
            token_count=estimate_tokens(combined),
            chunk_type="IMAGE_CAPTION",
            page_numbers=sorted(all_pages),
            is_parent=False,
        )
        pending_children.append(child)
        last_non_heading_block_type = "image_caption"

    def flush_pending_code() -> None:
        nonlocal current_parent_content, current_parent_pages, current_parent_tokens
        nonlocal pending_children, pending_code_blocks, last_non_heading_block_type
        if not pending_code_blocks:
            return
        parts = []
        all_pages = set()
        for blk, pidx in pending_code_blocks:
            t = _get_block_display_text(blk, blk.get("type", "code"))
            if t:
                parts.append(t)
            all_pages.update(pidx)
        combined = "\n\n".join(parts).strip()
        pending_code_blocks.clear()
        if not combined:
            return
        wrapped = "\n```\n" + combined + "\n```\n"
        current_parent_content.append(wrapped)
        current_parent_pages.update(all_pages)
        current_parent_tokens += estimate_tokens(wrapped)
        child = Chunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            notebook_id=notebook_id,
            chunk_index=0,
            content=wrapped,
            token_count=estimate_tokens(wrapped),
            chunk_type="CODE",
            page_numbers=sorted(all_pages),
            is_parent=False,
        )
        pending_children.append(child)
        last_non_heading_block_type = "code"

    for block in blocks:
        raw_type = block.get("type") or block.get("content_type") or block.get("block_type") or "text"
        block_type = _normalize_block_type(raw_type)
        page_idx = _normalize_page_idx(block.get("page_idx", block.get("page_no", 0)))
        text_content = _get_block_display_text(block, block_type)

        # ① 噪声：直接丢弃
        if block_type in NOISE_TYPES:
            continue

        # ② 先结算原子块：遇到非本族 block 时把已收集的表格/图片/代码打成一块
        if block_type not in TABLE_FAMILY:
            flush_pending_table()
        if block_type not in IMAGE_FAMILY:
            flush_pending_image()
        if block_type not in CODE_FAMILY:
            flush_pending_code()

        # ③ 当前 block 属于原子块族：只收集，本轮不生成 chunk
        if block_type in TABLE_FAMILY:
            pending_table_blocks.append((block, page_idx))
            continue
        if block_type in IMAGE_FAMILY:
            pending_image_blocks.append((block, page_idx))
            continue
        if block_type in CODE_FAMILY:
            pending_code_blocks.append((block, page_idx))
            continue

        # ④ 公式 / 旁注 格式化
        if block_type == "equation" and text_content:
            text_content = "\n$$\n" + text_content + "\n$$\n"
        elif block_type == "aside_text" and text_content:
            text_content = "（旁注：" + text_content + "）"

        text_content = text_content.strip()
        if not text_content:
            continue

        block_tokens = estimate_tokens(text_content)

        maybe_pseudo_title = (
            split_on_pseudo_title
            and block_type == "text"
            and _is_pseudo_title(text_content, max_chars=pseudo_title_max_chars)
        )
        is_heading = block_type == "title" or maybe_pseudo_title

        # ① 遇到标题（真实/伪标题）→ 截断 Parent，开启新的 Parent 段
        if is_heading:
            flush_parent()
            current_parent_content.append(text_content)
            current_parent_pages.update(page_idx)
            current_parent_tokens += block_tokens
            last_non_heading_block_type = None
            continue

        # ①.5 多信号分段:
        # - 跨页且当前父块已有一定体量
        # - 类型突变（text/table/code/image 等）且当前父块已有一定体量
        _content_types = {"text", "title", "table", "table_caption", "table_footnote", "image", "image_caption", "image_footnote", "image_body", "code", "code_caption", "algorithm", "equation", "list", "ref_text", "page_footnote", "aside_text"}
        should_soft_split = False
        if current_parent_content and current_parent_tokens >= split_min_parent_tokens and len(pending_children) >= split_min_children:
            if split_on_page_break and page_idx and current_parent_pages:
                if not set(page_idx).issubset(current_parent_pages):
                    should_soft_split = True

            if (
                split_on_type_shift
                and not should_soft_split
                and last_non_heading_block_type is not None
                and block_type != last_non_heading_block_type
                and block_type in _content_types
                and last_non_heading_block_type in _content_types
            ):
                should_soft_split = True

        if should_soft_split:
            flush_parent()

        # ①.6 父块安全阀: 未遇到标题时也要防止单个 parent 无限膨胀
        if (
            current_parent_content
            and (current_parent_tokens >= max_parent_tokens or current_parent_tokens + block_tokens > max_parent_tokens)
        ):
            flush_parent()

        # ② 累加到当前 Parent 的全局上下文
        current_parent_content.append(text_content)
        current_parent_pages.update(page_idx)
        current_parent_tokens += block_tokens

        # ③ 构造 Child Chunk（表格/图片/代码已在原子块中处理，此处仅剩正文类）
        chunk_type = _block_type_to_chunk_type(block_type)

        if estimate_tokens(text_content) > max_child_tokens:
            # 超长段落 → 递归分割成多个 Child
            sub_texts = _recursive_split(text_content, max_tokens=max_child_tokens)
            for st in sub_texts:
                st = st.strip()
                if not st:
                    continue
                child = Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    notebook_id=notebook_id,
                    chunk_index=0,
                    content=st,
                    token_count=estimate_tokens(st),
                    chunk_type=chunk_type,
                    page_numbers=page_idx,
                    is_parent=False,
                )
                pending_children.append(child)
            last_non_heading_block_type = block_type
        else:
            child = Chunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                notebook_id=notebook_id,
                chunk_index=0,
                content=text_content,
                token_count=estimate_tokens(text_content),
                chunk_type=chunk_type,
                page_numbers=page_idx,
                is_parent=False,
            )
            pending_children.append(child)
            last_non_heading_block_type = block_type

    # 循环结束：先结算未刷新的原子块，再结算最后一个 Parent
    flush_pending_table()
    flush_pending_image()
    flush_pending_code()
    flush_parent()

    return all_chunks


# ---------------------------------------------------------------------------
# Markdown 降级切块 (MinerU 未返回结构化 JSON 时的 fallback)
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def chunk_markdown(
    markdown: str,
    document_id: str,
    notebook_id: str,
    max_child_tokens: int = 512,
) -> list[Chunk]:
    """
    降级方案: 将 Markdown 文本按标题分段，产出 Parent-Child 结构。
    当 MinerU 只返回纯 Markdown (无结构化 JSON) 时使用。
    """
    if not markdown or not markdown.strip():
        return []

    # 将 Markdown 按标题模拟转换为 Block 列表
    blocks = _markdown_to_blocks(markdown)
    return process_mineru_blocks(blocks, document_id, notebook_id, max_child_tokens)


def _markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    """将 Markdown 文本模拟转换为 MinerU Block 格式"""
    blocks: list[dict[str, Any]] = []
    heading_positions = list(_HEADING_RE.finditer(markdown))

    if not heading_positions:
        for para in _split_paragraphs(markdown):
            if para.strip():
                blocks.append({
                    "type": _detect_block_type(para),
                    "text": para.strip(),
                    "page_idx": [],
                })
        return blocks

    # 标题前的前言
    if heading_positions[0].start() > 0:
        preamble = markdown[:heading_positions[0].start()].strip()
        if preamble:
            for para in _split_paragraphs(preamble):
                if para.strip():
                    blocks.append({"type": _detect_block_type(para), "text": para.strip(), "page_idx": []})

    for i, match in enumerate(heading_positions):
        start = match.start()
        end = heading_positions[i + 1].start() if i + 1 < len(heading_positions) else len(markdown)
        section = markdown[start:end].strip()

        lines = section.split("\n", 1)
        title_line = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""

        blocks.append({"type": "title", "text": title_line, "page_idx": []})

        if body:
            for para in _split_paragraphs(body):
                if para.strip():
                    blocks.append({"type": _detect_block_type(para), "text": para.strip(), "page_idx": []})

    return blocks


def _split_paragraphs(text: str) -> list[str]:
    """按双换行分段"""
    return [p for p in text.split("\n\n") if p.strip()]


_TABLE_RE = re.compile(r"^\|.+\|$", re.MULTILINE)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _detect_block_type(text: str) -> str:
    """从 Markdown 内容推断 block type"""
    stripped = text.strip()
    lines = [l for l in stripped.split("\n") if l.strip()]
    pipe_lines = [l for l in lines if l.strip().startswith("|") and l.strip().endswith("|")]
    if len(pipe_lines) >= 2:
        return "table"
    if _IMAGE_RE.search(stripped):
        return "image_caption"
    return "text"


# ---------------------------------------------------------------------------
# 递归分割 (用于超长段落)
# ---------------------------------------------------------------------------

def _split_by_separators(text: str, separators: list[str]) -> list[str]:
    if not separators:
        return [text]

    sep = separators[0]
    rest = separators[1:]

    parts = text.split(sep)
    parts = [p for p in parts if p.strip()]

    if len(parts) <= 1 and rest:
        return _split_by_separators(text, rest)

    return parts


def _recursive_split(
    text: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[str]:
    """递归分割超长文本到目标 token 数以内"""
    if estimate_tokens(text) <= max_tokens:
        return [text]

    separators = ["\n\n", "\n", "。", ". ", "；", "; ", "，", ", "]
    parts = _split_by_separators(text, separators)

    if len(parts) <= 1:
        return _force_split(text, max_tokens, overlap_tokens)

    result: list[str] = []
    buffer = ""

    for part in parts:
        candidate = (buffer + "\n\n" + part).strip() if buffer else part
        if estimate_tokens(candidate) <= max_tokens:
            buffer = candidate
        else:
            if buffer:
                result.append(buffer)
            if estimate_tokens(part) > max_tokens:
                result.extend(_recursive_split(part, max_tokens, overlap_tokens))
                buffer = ""
            else:
                buffer = part

    if buffer:
        result.append(buffer)

    return result


def _force_split(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """按字符强制切割"""
    approx_char_per_token = 3
    chunk_size = max_tokens * approx_char_per_token
    overlap_size = overlap_tokens * approx_char_per_token

    result: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        result.append(text[start:end])
        start = end - overlap_size if end < len(text) else end

    return result
