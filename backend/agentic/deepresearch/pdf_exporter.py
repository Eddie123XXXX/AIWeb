"""
DeepResearch PDF 导出

将 Markdown 报告转换为更接近正式研究报告的 PDF 字节流。
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)
from reportlab.platypus.tableofcontents import TableOfContents


PDF_FONT_NAME = "STSong-Light"
PAGE_WIDTH, PAGE_HEIGHT = A4


def _ensure_cjk_font() -> str:
    """注册可显示中文的 CID 字体。"""
    registerFont(UnicodeCIDFont(PDF_FONT_NAME))
    return PDF_FONT_NAME


def _clean_title(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _first_heading(markdown: str) -> str:
    for raw_line in (markdown or "").splitlines():
        stripped = raw_line.strip()
        match = re.match(r"^#\s+(.*)$", stripped)
        if match:
            return _clean_title(match.group(1))
    return ""


def _first_subheading(markdown: str) -> str:
    for raw_line in (markdown or "").splitlines():
        stripped = raw_line.strip()
        match = re.match(r"^##\s+(.*)$", stripped)
        if match:
            return _clean_title(match.group(1))
    return ""


def _strip_title_markup(text: str) -> str:
    value = _clean_title(text)
    value = re.sub(r"^\*\*(.+)\*\*$", r"\1", value)
    value = re.sub(r"^\*(.+)\*$", r"\1", value)
    value = re.sub(r"^`(.+)`$", r"\1", value)
    return _clean_title(value)


def resolve_pdf_title(title: str, markdown: str) -> str:
    """优先且尽量只从 Markdown 正文中提取报告标题。"""
    heading_title = _first_heading(markdown or "")
    if heading_title:
        return _clean_title(heading_title)

    subheading_title = _first_subheading(markdown or "")
    if subheading_title:
        return _clean_title(subheading_title)

    lines = [line.strip() for line in (markdown or "").splitlines()]
    non_empty = [(index, line) for index, line in enumerate(lines) if line]
    if non_empty:
        first_index, first_line = non_empty[0]
        normalized_first_line = _strip_title_markup(first_line)
        next_non_empty = non_empty[1][1] if len(non_empty) > 1 else ""
        looks_like_plain_title = (
            len(normalized_first_line) <= 120
            and not re.match(r"^(#{1,6}\s|[-*]\s|\d+\.\s|>|```)", first_line)
            and not re.match(r"^https?://", normalized_first_line, re.I)
            and not re.search(r"[。！？.!?]$", normalized_first_line)
        )
        next_is_section = bool(
            re.match(r"^(#{2,6}\s|[-*]\s|\d+\.\s|>)", next_non_empty)
        )
        next_is_setext = first_index + 1 < len(lines) and bool(re.match(r"^[=-]{3,}$", lines[first_index + 1]))
        looks_like_report_title = bool(re.search(r"(报告|研究|analysis|report)", normalized_first_line, re.I))
        if looks_like_plain_title and (next_is_section or next_is_setext or len(non_empty) == 1 or looks_like_report_title):
            return normalized_first_line

    return _clean_title(title or "")


def _escape_href(url: str) -> str:
    return escape((url or "").strip(), {'"': "&quot;"})


def _slugify_anchor(text: str, index: int) -> str:
    base = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", _clean_title(text)).strip("-").lower()
    base = base or "section"
    return f"{base}-{index}"


def _link_markup(label: str, href: str) -> str:
    safe_label = escape(label.strip() or href.strip())
    safe_href = _escape_href(href)
    return f'<link href="{safe_href}" color="#2563EB"><u>{safe_label}</u></link>'


def _replace_markdown_links(text: str, add_token) -> str:
    result: list[str] = []
    i = 0
    text_length = len(text)

    while i < text_length:
        if text[i] != "[":
            result.append(text[i])
            i += 1
            continue

        label_end = text.find("]", i + 1)
        if label_end == -1 or label_end + 1 >= text_length or text[label_end + 1] != "(":
            result.append(text[i])
            i += 1
            continue

        href_start = label_end + 2
        depth = 1
        cursor = href_start
        while cursor < text_length and depth > 0:
            char = text[cursor]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            cursor += 1

        if depth != 0:
            result.append(text[i])
            i += 1
            continue

        label = text[i + 1 : label_end].strip()
        href = text[href_start : cursor - 1].strip()
        if label and re.match(r"^https?://", href):
            result.append(add_token(_link_markup(label, href)))
            i = cursor
            continue

        result.append(text[i])
        i += 1

    return "".join(result)


def _apply_link_tokens(text: str) -> str:
    token_map: dict[str, str] = {}
    token_index = 0

    def add_token(markup: str) -> str:
        nonlocal token_index
        token = f"__PDF_LINK_{token_index}__"
        token_index += 1
        token_map[token] = markup
        return token

    def replace_markdown_link(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        href = match.group(2).strip()
        return add_token(_link_markup(label, href))

    text = _replace_markdown_links(text, add_token)

    def replace_bare_url(match: re.Match[str]) -> str:
        href = match.group(1).strip()
        return add_token(_link_markup(href, href))

    text = re.sub(r"(?<![\"'(=])\b(https?://[^\s<>\])]+)", replace_bare_url, text)
    escaped = escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", escaped)
    for token, markup in token_map.items():
        escaped = escaped.replace(token, markup)
    return escaped


def _apply_inline_markup(text: str) -> str:
    escaped = _apply_link_tokens(text)
    return escaped.replace("\n", "<br/>")


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "DeepResearchPdfCoverKicker",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=11,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#6B7280"),
            spaceAfter=8,
        ),
        "cover_title": ParagraphStyle(
            "DeepResearchPdfCoverTitle",
            parent=sample["Title"],
            fontName=font_name,
            fontSize=24,
            leading=32,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
            spaceAfter=12,
        ),
        "cover_meta": ParagraphStyle(
            "DeepResearchPdfCoverMeta",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=15,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#4B5563"),
            spaceAfter=4,
        ),
        "toc_title": ParagraphStyle(
            "DeepResearchPdfTocTitle",
            parent=sample["Heading1"],
            fontName=font_name,
            fontSize=18,
            leading=24,
            textColor=colors.HexColor("#111827"),
            spaceAfter=12,
        ),
        "toc_item_l1": ParagraphStyle(
            "DeepResearchPdfTocItemL1",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#111827"),
            leftIndent=0,
            spaceAfter=5,
        ),
        "toc_item_l2": ParagraphStyle(
            "DeepResearchPdfTocItemL2",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=10.3,
            leading=15,
            textColor=colors.HexColor("#334155"),
            leftIndent=12,
            spaceAfter=4,
        ),
        "toc_item_l3": ParagraphStyle(
            "DeepResearchPdfTocItemL3",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=9.8,
            leading=14,
            textColor=colors.HexColor("#475569"),
            leftIndent=24,
            spaceAfter=3,
        ),
        "toc_empty": ParagraphStyle(
            "DeepResearchPdfTocEmpty",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=10.3,
            leading=16,
            textColor=colors.HexColor("#6B7280"),
            spaceAfter=4,
        ),
        "section_title": ParagraphStyle(
            "DeepResearchPdfSectionTitle",
            parent=sample["Heading1"],
            fontName=font_name,
            fontSize=18,
            leading=24,
            textColor=colors.HexColor("#0F172A"),
            borderPadding=(0, 0, 6, 0),
            borderWidth=0,
            borderColor=colors.HexColor("#CBD5E1"),
            spaceBefore=18,
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "DeepResearchPdfH1",
            parent=sample["Heading1"],
            fontName=font_name,
            fontSize=16,
            leading=22,
            textColor=colors.HexColor("#111827"),
            spaceBefore=16,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "DeepResearchPdfH2",
            parent=sample["Heading2"],
            fontName=font_name,
            fontSize=13.5,
            leading=19,
            textColor=colors.HexColor("#1F2937"),
            spaceBefore=12,
            spaceAfter=5,
        ),
        "h3": ParagraphStyle(
            "DeepResearchPdfH3",
            parent=sample["Heading3"],
            fontName=font_name,
            fontSize=11.8,
            leading=17,
            textColor=colors.HexColor("#374151"),
            spaceBefore=10,
            spaceAfter=4,
        ),
        "h4": ParagraphStyle(
            "DeepResearchPdfH4",
            parent=sample["Heading4"],
            fontName=font_name,
            fontSize=10.8,
            leading=16,
            textColor=colors.HexColor("#4B5563"),
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "DeepResearchPdfBody",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=10.5,
            leading=18,
            textColor=colors.HexColor("#111827"),
            spaceAfter=8,
        ),
        "quote": ParagraphStyle(
            "DeepResearchPdfQuote",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=10.2,
            leading=17,
            leftIndent=14,
            rightIndent=4,
            backColor=colors.HexColor("#F8FAFC"),
            borderColor=colors.HexColor("#CBD5E1"),
            borderWidth=1,
            borderPadding=8,
            borderLeft=True,
            textColor=colors.HexColor("#334155"),
            spaceAfter=8,
        ),
        "code_label": ParagraphStyle(
            "DeepResearchPdfCodeLabel",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#6B7280"),
            spaceBefore=4,
            spaceAfter=2,
        ),
        "code": ParagraphStyle(
            "DeepResearchPdfCode",
            parent=sample["Code"],
            fontName="Courier",
            fontSize=9.2,
            leading=13,
            backColor=colors.HexColor("#F3F4F6"),
            borderPadding=8,
            leftIndent=6,
            rightIndent=6,
            spaceAfter=8,
        ),
        "list": ParagraphStyle(
            "DeepResearchPdfList",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=10.3,
            leading=17,
            textColor=colors.HexColor("#111827"),
            spaceAfter=0,
        ),
        "reference_list": ParagraphStyle(
            "DeepResearchPdfReferenceList",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=9.7,
            leading=14,
            textColor=colors.HexColor("#111827"),
            spaceAfter=0,
        ),
        "footer_left": ParagraphStyle(
            "DeepResearchPdfFooterLeft",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=8.5,
            leading=10,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#6B7280"),
        ),
        "footer_right": ParagraphStyle(
            "DeepResearchPdfFooterRight",
            parent=sample["BodyText"],
            fontName=font_name,
            fontSize=8.5,
            leading=10,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#6B7280"),
        ),
    }


def _flush_paragraph(buffer: list[str], story: list, style: ParagraphStyle) -> None:
    if not buffer:
        return
    text = "\n".join(buffer).strip()
    if text:
        story.append(Paragraph(_apply_inline_markup(text), style))
    buffer.clear()


def _flush_list(items: list[str], story: list, style: ParagraphStyle, bullet_type: str) -> None:
    if not items:
        return
    flowable_items = [ListItem(Paragraph(_apply_inline_markup(item), style)) for item in items if item.strip()]
    if flowable_items:
        compact = style.name == "DeepResearchPdfReferenceList"
        story.append(
            ListFlowable(
                flowable_items,
                bulletType=bullet_type,
                start="1" if bullet_type == "1" else None,
                leftIndent=12 if compact else 16,
                bulletFontName=style.fontName,
                bulletFontSize=style.fontSize,
            )
        )
        story.append(Spacer(1, 3 if compact else 5))
    items.clear()


def _flush_code_block(code_buffer: list[str], story: list, styles: dict[str, ParagraphStyle], language: str) -> None:
    if not code_buffer:
        return
    label = language or "code"
    story.append(Paragraph(_apply_inline_markup(label.upper()), styles["code_label"]))
    story.append(Preformatted("\n".join(code_buffer), styles["code"]))
    code_buffer.clear()


def _append_cover_page(story: list, styles: dict[str, ParagraphStyle], title: str, subtitle: str) -> None:
    exported_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Spacer(1, 42 * mm))
    story.append(Paragraph("Deep Research Report", styles["cover_kicker"]))
    story.append(Paragraph(_apply_inline_markup(title), styles["cover_title"]))
    if subtitle:
        story.append(Paragraph(_apply_inline_markup(subtitle), styles["cover_meta"]))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(f"导出时间 / Exported at {exported_at}", styles["cover_meta"]))
    story.append(Paragraph("Generated by AIWeb DeepResearch", styles["cover_meta"]))
    story.append(Spacer(1, 22 * mm))
    story.append(
        HRFlowable(
            width="58%",
            thickness=1,
            lineCap="round",
            color=colors.HexColor("#CBD5E1"),
            spaceBefore=0,
            spaceAfter=0,
            hAlign="CENTER",
        )
    )
    story.append(PageBreak())


def _build_toc(styles: dict[str, ParagraphStyle]) -> TableOfContents:
    toc = TableOfContents()
    toc.levelStyles = [
        styles["toc_item_l1"],
        styles["toc_item_l2"],
        styles["toc_item_l3"],
    ]
    return toc


def _append_toc_page(story: list, styles: dict[str, ParagraphStyle]) -> None:
    story.append(Paragraph("目录 / Contents", styles["toc_title"]))
    story.append(
        HRFlowable(
            width="100%",
            thickness=0.9,
            lineCap="round",
            color=colors.HexColor("#E5E7EB"),
            spaceBefore=0,
            spaceAfter=10,
        )
    )
    story.append(_build_toc(styles))
    story.append(PageBreak())


def _is_reference_heading(text: str) -> bool:
    normalized = _clean_title(text).strip().lower().rstrip(":：")
    return normalized in {"references", "reference", "参考文献", "参考资料"}


class _DeepResearchDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable) -> None:
        toc_level = getattr(flowable, "_toc_level", None)
        toc_text = getattr(flowable, "_toc_text", "")
        bookmark_name = getattr(flowable, "_bookmark_name", "")
        if toc_level is None or not toc_text:
            return
        if bookmark_name:
            self.canv.bookmarkPage(bookmark_name)
        self.notify("TOCEntry", (toc_level, toc_text, max(self.page - 1, 1), bookmark_name or None))


def _draw_page_frame(canvas, doc, report_title: str) -> None:
    if doc.page <= 1:
        return
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#E5E7EB"))
    canvas.setLineWidth(0.6)
    canvas.line(doc.leftMargin, PAGE_HEIGHT - 14 * mm, PAGE_WIDTH - doc.rightMargin, PAGE_HEIGHT - 14 * mm)
    canvas.line(doc.leftMargin, 12 * mm, PAGE_WIDTH - doc.rightMargin, 12 * mm)

    canvas.setFont(PDF_FONT_NAME, 8.5)
    canvas.setFillColor(colors.HexColor("#6B7280"))
    canvas.drawString(doc.leftMargin, PAGE_HEIGHT - 11 * mm, _clean_title(report_title)[:48])
    canvas.drawRightString(PAGE_WIDTH - doc.rightMargin, 9 * mm, f"Page {doc.page - 1}")
    canvas.restoreState()


def _build_story(*, title: str, markdown: str, styles: dict[str, ParagraphStyle]) -> list:
    story: list = []
    article_title = resolve_pdf_title(title, markdown)
    primary_title = _clean_title(article_title or title or "Deep Research Report")
    # 若正文已有正式报告标题，则封面不再显示用户原始 query（如 "ai"）作为副标题。
    subtitle = ""
    skipped_title = _first_heading(markdown) or ""

    _append_cover_page(story, styles, primary_title, subtitle)
    _append_toc_page(story, styles)

    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []
    ordered_list_buffer: list[str] = []
    code_buffer: list[str] = []
    in_code_block = False
    code_language = ""
    heading_index = 0
    reference_section_level: int | None = None
    body_start_index = len(story)

    def current_list_style() -> ParagraphStyle:
        return styles["reference_list"] if reference_section_level is not None else styles["list"]

    def flush_bullet_list() -> None:
        _flush_list(list_buffer, story, current_list_style(), "bullet")

    def flush_ordered_list() -> None:
        _flush_list(ordered_list_buffer, story, current_list_style(), "1")

    for raw_line in (markdown or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            _flush_paragraph(paragraph_buffer, story, styles["body"])
            flush_bullet_list()
            flush_ordered_list()
            if in_code_block:
                _flush_code_block(code_buffer, story, styles, code_language)
                code_language = ""
            else:
                code_language = stripped[3:].strip()
            in_code_block = not in_code_block
            continue

        if in_code_block:
            code_buffer.append(line)
            continue

        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            _flush_paragraph(paragraph_buffer, story, styles["body"])
            flush_bullet_list()
            flush_ordered_list()
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.8,
                    lineCap="round",
                    color=colors.HexColor("#E5E7EB"),
                    spaceBefore=6,
                    spaceAfter=10,
                )
            )
            continue

        if not stripped:
            _flush_paragraph(paragraph_buffer, story, styles["body"])
            flush_bullet_list()
            flush_ordered_list()
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading_match:
            _flush_paragraph(paragraph_buffer, story, styles["body"])
            flush_bullet_list()
            flush_ordered_list()
            hashes, heading_text = heading_match.groups()
            heading_text = heading_text.strip()
            clean_heading = _clean_title(heading_text)
            if len(hashes) == 1 and skipped_title and clean_heading == skipped_title:
                skipped_title = ""
                continue
            if _is_reference_heading(clean_heading):
                reference_section_level = len(hashes)
            elif reference_section_level is not None and len(hashes) <= reference_section_level:
                reference_section_level = None
            style_key = {1: "section_title", 2: "h1", 3: "h2", 4: "h3"}[len(hashes)]
            anchor = _slugify_anchor(clean_heading, heading_index)
            heading_index += 1
            paragraph = Paragraph(f'<a name="{anchor}"/>{_apply_inline_markup(heading_text)}', styles[style_key])
            if len(hashes) <= 3:
                paragraph._toc_level = len(hashes) - 1
                paragraph._toc_text = clean_heading
                paragraph._bookmark_name = anchor
            block = [paragraph]
            if len(hashes) == 1:
                block.append(
                    HRFlowable(
                        width="100%",
                        thickness=1.2,
                        lineCap="round",
                        color=colors.HexColor("#CBD5E1"),
                        spaceBefore=0,
                        spaceAfter=6,
                    )
                )
            story.append(KeepTogether(block))
            continue

        bullet_match = re.match(r"^[-*]\s+(.*)$", stripped)
        if bullet_match:
            _flush_paragraph(paragraph_buffer, story, styles["body"])
            flush_ordered_list()
            list_buffer.append(bullet_match.group(1))
            continue

        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ordered_match:
            _flush_paragraph(paragraph_buffer, story, styles["body"])
            flush_bullet_list()
            ordered_list_buffer.append(ordered_match.group(1))
            continue

        if stripped.startswith(">"):
            _flush_paragraph(paragraph_buffer, story, styles["body"])
            flush_bullet_list()
            flush_ordered_list()
            quote_text = re.sub(r"^>\s?", "", stripped)
            story.append(Paragraph(_apply_inline_markup(quote_text), styles["quote"]))
            continue

        paragraph_buffer.append(stripped)

    _flush_paragraph(paragraph_buffer, story, styles["body"])
    flush_bullet_list()
    flush_ordered_list()
    _flush_code_block(code_buffer, story, styles, code_language)

    if len(story) == body_start_index:
        story.append(Paragraph(_apply_inline_markup(primary_title), styles["section_title"]))

    return story


def generate_pdf_bytes(*, title: str, markdown: str) -> bytes:
    font_name = _ensure_cjk_font()
    styles = _build_styles(font_name)
    export_title = _clean_title(title or "")
    document_title = resolve_pdf_title(export_title, markdown or "") or "Deep Research Report"
    story = _build_story(title=export_title, markdown=markdown or "", styles=styles)

    buffer = BytesIO()
    doc = _DeepResearchDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title=document_title,
        author="AIWeb DeepResearch",
        subject="Deep Research PDF Export",
    )
    doc.multiBuild(
        story,
        onFirstPage=lambda canvas, pdf_doc: _draw_page_frame(canvas, pdf_doc, document_title),
        onLaterPages=lambda canvas, pdf_doc: _draw_page_frame(canvas, pdf_doc, document_title),
    )
    return buffer.getvalue()
