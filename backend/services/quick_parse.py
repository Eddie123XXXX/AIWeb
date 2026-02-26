"""
Quick Parse：临时文件解析（仅注入当前轮对话的工作记忆，不写入长期记忆/RAG）。

设计要点：
- 前端先将文件上传到 MinIO 等对象存储，拿到可访问 URL（通常是预签名链接）；
- 后端基于 URL 拉取原始文件，根据类型做针对性解析，统一转换为 Markdown/纯文本；
- 在发送给大模型前，将解析结果作为额外的 system 消息拼入 prompt；
- 通过字符数近似控制上下文长度，必要时做「前后保留 + 中间省略」截断。
"""

from __future__ import annotations

import io
import logging
import mimetypes
import os
from dataclasses import dataclass
from typing import List, Optional

import httpx

from models import QuickParseFile

logger = logging.getLogger(__name__)

# 近似的 Quick Parse 上下文上限（仅用于文件内容，不含历史对话），单位：token 近似值
_DEFAULT_MAX_TOKENS = int(os.getenv("QUICK_PARSE_MAX_TOKENS", "96000"))


@dataclass
class QuickParseResult:
    filename: str
    mime_type: str
    markdown: str
    truncated: bool = False


class QuickParseError(Exception):
    """Quick Parse 解析异常（调用方可根据需要返回给前端友好提示）。"""


async def build_quick_parse_system_content(
    files: List[QuickParseFile],
    *,
    max_tokens: Optional[int] = None,
) -> str:
    """
    将一批 Quick Parse 文件解析为单条可注入 system 的 Markdown 文本。

    - 解析失败时仅记录日志并跳过单个文件，不阻塞整轮对话；
    - 统一在末尾做一次「前后保留 + 中间省略」截断，避免爆上下文。
    """
    if not files:
        return ""

    results: List[QuickParseResult] = []

    for f in files:
        try:
            result = await _parse_single_file(f)
        except QuickParseError as e:
            logger.warning("Quick Parse 解析失败（用户可见） url=%s: %s", f.url, e)
            continue
        except Exception as e:  # noqa: BLE001
            logger.warning("Quick Parse 解析异常（忽略单文件） url=%s: %s", f.url, e)
            continue
        if result.markdown.strip():
            results.append(result)

    if not results:
        return ""

    blocks: list[str] = []
    for idx, r in enumerate(results, start=1):
        title = r.filename or f"文档{idx}"
        header = f"【Quick Parse 文档 {idx}: {title}】(type={r.mime_type})"
        body = r.markdown
        if r.truncated:
            body += "\n\n...[内容已省略，为控制上下文长度，部分中间内容未注入 Quick Parse]..."
        blocks.append(header + "\n\n" + body)

    combined = ("\n\n" + "-" * 40 + "\n\n").join(blocks)

    max_total_tokens = max_tokens or _DEFAULT_MAX_TOKENS
    truncated_text, did_truncate = _truncate_by_tokens(combined, max_total_tokens)
    if did_truncate:
        logger.info(
            "Quick Parse 总内容触发截断 | approx_tokens>=%s max_tokens=%s",
            _estimate_tokens(combined),
            max_total_tokens,
        )
    return truncated_text


async def _parse_single_file(f: QuickParseFile) -> QuickParseResult:
    """根据文件类型选择合适的解析策略，输出 Markdown 文本。"""
    if not f.url:
        raise QuickParseError("文件 URL 不能为空")

    raw_bytes = await _download_file(f.url)
    mime = _guess_mime_type(f)
    filename = f.filename or _derive_name_from_url(f.url)

    markdown: str

    if mime in ("application/pdf",):
        markdown = _parse_pdf(raw_bytes, filename)
    elif mime in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        markdown = _parse_docx(raw_bytes, filename)
    elif mime in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ):
        markdown = _parse_excel(raw_bytes, filename)
    elif mime in ("text/csv", "application/csv", "text/plain"):
        markdown = _parse_text_like(raw_bytes, filename)
    else:
        # 兜底：按 UTF-8 文本处理
        markdown = _parse_text_like(raw_bytes, filename)

    approx_tokens = _estimate_tokens(markdown)
    max_tokens = _DEFAULT_MAX_TOKENS
    if approx_tokens > max_tokens:
        markdown, _ = _truncate_by_tokens(markdown, max_tokens)
        return QuickParseResult(
            filename=filename,
            mime_type=mime,
            markdown=markdown,
            truncated=True,
        )

    return QuickParseResult(
        filename=filename,
        mime_type=mime,
        markdown=markdown,
        truncated=False,
    )


async def _download_file(url: str) -> bytes:
    """从对象存储或任意 HTTP URL 拉取文件内容。"""
    timeout = httpx.Timeout(30.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url)
        if resp.status_code >= 400:
            raise QuickParseError(f"下载文件失败（HTTP {resp.status_code}）")
        return resp.content


def _guess_mime_type(f: QuickParseFile) -> str:
    """优先使用请求中显式给出的 MIME，其次使用文件名后缀推断。"""
    if f.mime_type:
        return f.mime_type
    name = f.filename or _derive_name_from_url(f.url)
    mime, _ = mimetypes.guess_type(name)
    return mime or "application/octet-stream"


def _derive_name_from_url(url: str) -> str:
    return url.split("?")[0].rstrip("/").split("/")[-1] or "file"


def _parse_text_like(raw: bytes, filename: str) -> str:
    """解析纯文本 / CSV 等，以 UTF-8 为主，失败则回退到 latin-1。"""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="ignore")

    return f"[File: {filename}]\n\n{text}"


def _parse_pdf(raw: bytes, filename: str) -> str:
    """
    解析 PDF 为 Markdown 文本。

    优先使用 pdfplumber，如未安装则回退为简单文本提示，避免中断主流程。
    """
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError:
        logger.warning("pdfplumber 未安装，PDF Quick Parse 退化为占位提示")
        return f"[File: {filename}]\n\n[提示] 当前后端未安装 pdfplumber，无法解析 PDF 正文。"

    output_lines: list[str] = [f"[File: {filename}]"]
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            output_lines.append(f"\n\n[Page {page_idx}]\n")
            output_lines.append(text)

    return "\n".join(output_lines)


def _parse_docx(raw: bytes, filename: str) -> str:
    """
    解析 Word 文档为 Markdown 文本。

    优先使用 python-docx，如未安装则返回占位提示。
    """
    try:
        from docx import Document  # type: ignore[import]
    except ImportError:
        logger.warning("python-docx 未安装，DOCX Quick Parse 退化为占位提示")
        return f"[File: {filename}]\n\n[提示] 当前后端未安装 python-docx，无法解析 Word 正文。"

    document = Document(io.BytesIO(raw))
    lines: list[str] = [f"[File: {filename}]"]
    for para in document.paragraphs:
        text = para.text.strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _parse_excel(raw: bytes, filename: str) -> str:
    """
    解析 Excel 为 Markdown 友好的表格文本。

    使用 pandas 读取多 sheet，并以 Markdown 表格或 CSV 形式输出。
    """
    try:
        import pandas as pd  # type: ignore[import]
    except ImportError:
        logger.warning("pandas 未安装，Excel Quick Parse 退化为占位提示")
        return f"[File: {filename}]\n\n[提示] 当前后端未安装 pandas，无法解析 Excel。"

    buf = io.BytesIO(raw)
    sheets = pd.read_excel(buf, sheet_name=None)  # type: ignore[call-arg]

    lines: list[str] = [f"[File: {filename}]"]
    for sheet_name, df in sheets.items():
        lines.append(f"\n\n[Sheet: {sheet_name}]\n")
        if df.empty:
            lines.append("(空表)")
            continue
        # 将 DataFrame 转为简单 Markdown 表格：表头 + 行
        headers = [str(c) for c in df.columns.tolist()]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        for _, row in df.iterrows():
            cells = [str(v) if v is not None else "" for v in row.tolist()]
            lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def _estimate_tokens(text: str) -> int:
    """
    粗略估算 token 数。

    这里采用「中文/英文混排 ≈ 2 字符一个 token」的经验值，仅用于护栏级别的判断。
    """
    if not text:
        return 0
    return max(1, len(text) // 2)


def _truncate_by_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """
    按近似 token 上限做「前后保留，中间省略」截断。

    返回 (截断后的文本, 是否发生截断)。
    """
    if max_tokens <= 0:
        return text, False

    approx_tokens = _estimate_tokens(text)
    if approx_tokens <= max_tokens:
        return text, False

    # 近似为 2 字符 / token，按字符长度做裁剪
    max_chars = max_tokens * 2
    if len(text) <= max_chars:
        return text, False

    head_chars = int(max_chars * 0.6)
    tail_chars = max_chars - head_chars

    head = text[:head_chars]
    tail = text[-tail_chars:] if tail_chars > 0 else ""
    omitted = "\n\n...[内容已省略，为控制上下文长度，部分中间内容未注入 Quick Parse]...\n\n"
    return head + omitted + tail, True

