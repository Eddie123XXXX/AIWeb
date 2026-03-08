"""
DeepResearch HTTP 路由

深度研究：多智能体协作（规划→搜索→写作→审核/修订），流式 SSE。
与 research_sessions 表打通：创建会话、更新状态、历史列表与详情。
"""
import json
import logging
import asyncio
import re
import uuid
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from db import research_session_repository
from routers.models import get_model_config_by_id

from .service import ResearchService
from .pdf_exporter import generate_pdf_bytes, resolve_pdf_title
from .utils import (
    append_section_markdown,
    build_research_steps,
    merge_unique_references,
    normalize_editable_outline,
    normalize_outline_item,
    normalize_outline_for_ui,
    normalize_reference,
    serialize_event,
)

logger = logging.getLogger("agentic.deepresearch")

# 深度研究当前固定使用 DeepSeek V3.2，不接收前端 model_id 覆盖。
# 这样做是为了保证规划 / 写作 / 审校链路使用同一组已验证过的提示词与模型行为。
DEEPRESEARCH_MODEL_ID = "deepseek-v3.2"

router = APIRouter(prefix="/deepresearch", tags=["deepresearch"])


class DeepResearchRequest(BaseModel):
    """深度研究请求体"""
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={
            "example": {
                "query": "AI发展趋势",
                "max_iterations": 3,
                "search_web": True,
                "search_local": False,
            }
        },
    )

    query: str
    session_id: Optional[str] = None
    max_iterations: int = 3
    model_id: str = "default"  # 忽略：深度研究固定使用 DeepSeek V3.2
    user_id: Optional[int] = None
    search_web: Optional[bool] = True
    search_local: Optional[bool] = False
    mode: Literal["planning_only"] = "planning_only"


class ContinueResearchBody(BaseModel):
    search_web: Optional[bool] = True
    search_local: Optional[bool] = False


class UpdateOutlineBody(BaseModel):
    outline: list[dict]


class RewriteOutlineBody(BaseModel):
    instruction: str


class RewriteSelectionBody(BaseModel):
    selected_text: str
    instruction: str
    full_report: str
    start_offset: int
    end_offset: int


class ExportPdfBody(BaseModel):
    title: Optional[str] = None
    markdown: Optional[str] = None


def _get_ui_state(session: Optional[dict]) -> dict:
    if session and isinstance(session.get("ui_state"), dict):
        return dict(session.get("ui_state") or {})
    return {}


def _create_research_stream_response(
    *,
    service: ResearchService,
    session_id: str,
    query: str,
    user_id: Optional[int],
    search_web: bool,
    search_local: bool,
    mode: str,
    approved_outline: Optional[list[dict]] = None,
    create_session: bool = False,
):
    # 这里一边向前端推 SSE，一边把关键中间态落到 research_sessions。
    # 这样刷新页面后，前端可以用 ui_state 恢复章节、步骤条、思考面板和引用来源。
    async def process_research(queue: asyncio.Queue[str | None]):
        try:
            if create_session and user_id is not None:
                existing_session = await research_session_repository.get_by_id(session_id)
                if existing_session is None:
                    try:
                        await research_session_repository.create(
                            session_id=session_id,
                            user_id=user_id,
                            query=query,
                            title=(query[:200] + ("..." if len(query) > 200 else "")),
                        )
                        logger.info("DeepResearch session created: session_id=%s user_id=%s", session_id, user_id)
                    except Exception as e:
                        logger.warning("DeepResearch create session failed (continue stream): %s", e)

            # sources / references 需要按事件逐步累积，否则研究中途刷新后会丢掉已收集来源。
            refs_accumulator = []

            async for event in service.research_stream(
                query=query,
                session_id=session_id,
                user_id=user_id,
                search_web=search_web,
                search_local=search_local,
                mode=mode,
                approved_outline=approved_outline,
            ):
                try:
                    obj = json.loads(event)
                    if user_id is not None:
                        ev_type = obj.get("type")
                        if ev_type == "phase":
                            phase_name = obj.get("phase") or ""
                            phase_detail = obj.get("content") or ""
                            if mode == "planning_only" and phase_name not in ("planning", ""):
                                logger.error(
                                    "DeepResearch planning_only received unexpected phase: session_id=%s phase=%s",
                                    session_id,
                                    phase_name,
                                )
                                await research_session_repository.update_status(session_id, "failed")
                                await queue.put(
                                    f"data: {serialize_event({'type': 'error', 'content': 'Planning-only flow entered an unexpected phase'})}\n\n"
                                )
                                break
                            research_steps = build_research_steps(phase_name)
                            await research_session_repository.update_progress(
                                session_id,
                                status="running",
                                ui_state_update={
                                    "phase": phase_name,
                                    "phase_detail": phase_detail if isinstance(phase_detail, str) else "",
                                    "research_steps": research_steps,
                                    "awaiting_user_input": None,
                                },
                            )
                        elif ev_type == "thought":
                            content = obj.get("content")
                            text = content.get("content", "") if isinstance(content, dict) else (content or "")
                            if isinstance(text, str) and text.strip():
                                await research_session_repository.update_progress(
                                    session_id,
                                    append_panel_log={"type": "thought", "text": text.strip()[:2000]},
                                )
                        elif ev_type == "phase_detail":
                            content = obj.get("content")
                            text = content.get("content", "") if isinstance(content, dict) else (content or "")
                            if isinstance(text, str) and text.strip():
                                await research_session_repository.update_progress(
                                    session_id,
                                    append_panel_log={"type": "phase_detail", "text": text.strip()[:2000]},
                                )
                        elif ev_type == "outline":
                            content = obj.get("content") or {}
                            outline_list = content.get("outline") if isinstance(content.get("outline"), list) else None
                            rq = content.get("research_questions") if isinstance(content.get("research_questions"), list) else None
                            full_outline = normalize_editable_outline(outline_list, query=query) if outline_list is not None else None
                            n_sections = len(full_outline) if full_outline else 0
                            if full_outline is not None:
                                await research_session_repository.update_outline_state(
                                    session_id,
                                    outline_draft_full=full_outline,
                                    editable_outline=full_outline,
                                    outline=normalize_outline_for_ui(full_outline),
                                    research_questions=rq,
                                )
                            elif rq is not None:
                                await research_session_repository.update_outline_state(
                                    session_id,
                                    research_questions=rq,
                                )
                            if n_sections:
                                await research_session_repository.update_progress(
                                    session_id,
                                    append_panel_log={"type": "outline", "text": f"已生成 {n_sections} 个章节"},
                                )
                        elif ev_type == "awaiting_outline_confirmation":
                            content = obj.get("content") or {}
                            outline_list = content.get("outline") if isinstance(content.get("outline"), list) else None
                            rq = content.get("research_questions") if isinstance(content.get("research_questions"), list) else None
                            message = content.get("message") if isinstance(content.get("message"), str) else "请确认章节框架后继续研究"
                            full_outline = normalize_editable_outline(outline_list, query=query) if outline_list is not None else []
                            await research_session_repository.update_outline_state(
                                session_id,
                                outline_draft_full=full_outline,
                                editable_outline=full_outline,
                                outline=normalize_outline_for_ui(full_outline),
                                research_questions=rq,
                                outline_approval_status="pending",
                                awaiting_user_input="outline_approval",
                                phase="waiting_approval",
                                phase_detail=message,
                                research_steps=build_research_steps("waiting_approval"),
                                status="waiting_approval",
                            )
                        elif ev_type == "search_result":
                            content = obj.get("content") or {}
                            fact = content.get("fact") if isinstance(content.get("fact"), dict) else None
                            if fact:
                                normalized_ref = normalize_reference(fact=fact)
                                refs_accumulator = merge_unique_references(refs_accumulator, [normalized_ref] if normalized_ref else [])
                                session_row = await research_session_repository.get_by_id(session_id)
                                existing_ui = _get_ui_state(session_row)
                                existing_results = existing_ui.get("search_results") if isinstance(existing_ui.get("search_results"), list) else []
                                search_results = merge_unique_references(existing_results, [normalized_ref] if normalized_ref else [])
                                await research_session_repository.update_progress(
                                    session_id,
                                    references=refs_accumulator,
                                    ui_state_update={
                                        "search_results": search_results,
                                        "references": refs_accumulator,
                                    },
                                )
                        elif ev_type == "report_draft":
                            content = obj.get("content") or {}
                            report_text = content.get("content") if isinstance(content.get("content"), str) else None
                            if report_text is not None:
                                await research_session_repository.update_progress(
                                    session_id,
                                    final_report=report_text,
                                    ui_state_update={"streaming_report": report_text},
                                )
                        elif ev_type == "section_content":
                            content = obj.get("content") or {}
                            sid = content.get("section_id")
                            section_title = content.get("section_title") if isinstance(content.get("section_title"), str) else ""
                            section_text = content.get("content") if isinstance(content.get("content"), str) else None
                            if sid and section_text is not None:
                                session_row = await research_session_repository.get_by_id(session_id)
                                existing = _get_ui_state(session_row)
                                draft_sections = dict(existing.get("draft_sections") or {})
                                draft_sections[sid] = section_text
                                streaming_report = append_section_markdown(
                                    existing.get("streaming_report", "") if isinstance(existing.get("streaming_report"), str) else "",
                                    section_title,
                                    section_text,
                                )
                                await research_session_repository.update_progress(
                                    session_id,
                                    ui_state_update={
                                        "draft_sections": draft_sections,
                                        "streaming_report": streaming_report,
                                    },
                                )
                        elif ev_type == "research_complete":
                            refs_from_event = obj.get("references")
                            final_report = obj.get("final_report") or ""
                            outline = obj.get("outline")
                            refs_to_save = merge_unique_references(
                                refs_accumulator,
                                refs_from_event if isinstance(refs_from_event, list) else [],
                            )
                            session_row = await research_session_repository.get_by_id(session_id)
                            existing_ui = _get_ui_state(session_row)
                            ui_state = {**existing_ui}
                            if outline is not None:
                                ui_state["outline"] = [normalize_outline_item(item) for item in outline if isinstance(item, dict)]
                            ui_state["research_steps"] = build_research_steps("completed")
                            ui_state["phase"] = "completed"
                            ui_state["phase_detail"] = ""
                            ui_state["references"] = refs_to_save
                            ui_state["outline_approval_status"] = "approved"
                            ui_state["awaiting_user_input"] = None
                            if not isinstance(ui_state.get("search_results"), list) or not ui_state.get("search_results"):
                                ui_state["search_results"] = refs_to_save
                            ui_state["streaming_report"] = final_report
                            updated = await research_session_repository.update_status(
                                session_id,
                                "completed",
                                final_report=final_report,
                                references=refs_to_save,
                                ui_state=ui_state,
                            )
                            if updated:
                                logger.info(
                                    "DeepResearch session updated: session_id=%s final_report_len=%s refs=%s",
                                    session_id, len(final_report), len(refs_to_save) if refs_to_save else 0,
                                )
                            else:
                                logger.warning("DeepResearch update_status returned None for session_id=%s", session_id)
                        elif ev_type == "error":
                            await research_session_repository.update_status(session_id, "failed")
                except (json.JSONDecodeError, TypeError):
                    pass
                except Exception as e:
                    logger.exception("DeepResearch process event failed: %s", e)
                await queue.put(f"data: {event}\n\n")
        except Exception as e:
            logger.exception("DeepResearch stream error: %s", e)
            if user_id is not None:
                try:
                    await research_session_repository.update_status(session_id, "failed")
                except Exception as e2:
                    logger.warning("DeepResearch update_status failed: %s", e2)
            await queue.put(f"data: {serialize_event({'type': 'error', 'content': str(e)})}\n\n")
        await queue.put(f"data: {serialize_event({'type': 'done'})}\n\n")
        await queue.put(None)

    async def generate_sse():
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        worker = asyncio.create_task(process_research(queue))
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        except asyncio.CancelledError:
            logger.info("DeepResearch client disconnected: session_id=%s", session_id)
            raise
        finally:
            if worker.done():
                try:
                    await worker
                except Exception:
                    logger.exception("DeepResearch worker failed after stream end: session_id=%s", session_id)

    return StreamingResponse(generate_sse(), media_type="text/event-stream")


@router.post("/stream")
async def stream_research_post(body: DeepResearchRequest):
    """深度研究 - 流式输出 (POST)。固定使用 DeepSeek V3.2；与 research_sessions 表打通。"""
    try:
        get_model_config_by_id(DEEPRESEARCH_MODEL_ID)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(
                status_code=503,
                detail="深度研究需配置 DeepSeek V3.2：请设置环境变量 DEEPSEEK_API_KEY 后重启服务",
            ) from e
        raise
    session_id = body.session_id or str(uuid.uuid4())
    user_id = body.user_id
    service = ResearchService(model_id=DEEPRESEARCH_MODEL_ID)
    return _create_research_stream_response(
        service=service,
        session_id=session_id,
        query=body.query,
        user_id=user_id,
        search_web=body.search_web if body.search_web is not None else True,
        search_local=body.search_local if body.search_local is not None else False,
        mode="planning_only",
        create_session=True,
    )


@router.get("/stream")
async def stream_research_get(
    query: str = Query(..., description="研究问题"),
    max_iterations: int = Query(1, ge=1, le=5, description="最大迭代次数"),
    user_id: Optional[int] = Query(None, description="用户 ID，检索该用户全部知识库"),
    search_web: bool = Query(True, description="是否搜索网络"),
    search_local: bool = Query(False, description="是否搜索本地知识库"),
):
    """深度研究 - 流式输出 (GET)。固定使用 DeepSeek V3.2。"""
    service = ResearchService(model_id=DEEPRESEARCH_MODEL_ID)

    async def generate_sse():
        try:
            async for event in service.research_stream(
                query=query,
                session_id=None,
                user_id=user_id,
                search_web=search_web,
                search_local=search_local,
            ):
                yield f"data: {event}\n\n"
        except Exception as e:
            logger.exception("DeepResearch stream error: %s", e)
            yield f"data: {serialize_event({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(generate_sse(), media_type="text/event-stream")


@router.get("/sessions")
async def list_sessions(
    user_id: int = Query(..., description="用户 ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """深度研究历史列表，按更新时间倒序。"""
    items = await research_session_repository.list_by_user(user_id=user_id, limit=limit, offset=offset)
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """单条深度研究会话详情（含 final_report）。"""
    session = await research_session_repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/sessions/{session_id}/outline")
async def update_session_outline(session_id: str, body: UpdateOutlineBody):
    """保存用户编辑后的章节框架。"""
    session = await research_session_repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    outline = normalize_editable_outline(body.outline, query=session.get("query") or "")
    updated = await research_session_repository.update_outline_state(
        session_id,
        editable_outline=outline,
        outline=normalize_outline_for_ui(outline),
        outline_approval_status="pending",
        awaiting_user_input="outline_approval",
        phase="waiting_approval",
        phase_detail="请确认章节框架后继续研究",
        research_steps=build_research_steps("waiting_approval"),
        status="waiting_approval",
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return updated


@router.post("/sessions/{session_id}/rewrite-outline")
async def rewrite_session_outline(session_id: str, body: RewriteOutlineBody):
    """根据用户自然语言描述重构章节框架。"""
    session = await research_session_repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    ui_state = _get_ui_state(session)
    base_outline = ui_state.get("editable_outline") or ui_state.get("outline_draft_full")
    if not isinstance(base_outline, list) or not base_outline:
        raise HTTPException(status_code=400, detail="No outline available to rewrite")
    service = ResearchService(model_id=DEEPRESEARCH_MODEL_ID)
    rewritten_outline = await service.rewrite_outline(
        query=session.get("query") or "",
        outline=base_outline,
        instruction=body.instruction,
    )
    updated = await research_session_repository.update_outline_state(
        session_id,
        editable_outline=rewritten_outline,
        outline=normalize_outline_for_ui(rewritten_outline),
        outline_approval_status="pending",
        awaiting_user_input="outline_approval",
        phase="waiting_approval",
        phase_detail="请确认章节框架后继续研究",
        research_steps=build_research_steps("waiting_approval"),
        status="waiting_approval",
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return updated


@router.post("/sessions/{session_id}/rewrite-selection")
async def rewrite_session_selection(session_id: str, body: RewriteSelectionBody):
    """对已完成报告中的选中片段生成候选改写。"""
    session = await research_session_repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    selected_text = body.selected_text
    instruction = body.instruction.strip()
    full_report = body.full_report or ""
    if not selected_text or not selected_text.strip():
        raise HTTPException(status_code=400, detail="selected_text is required")
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction is required")
    if body.start_offset < 0 or body.end_offset <= body.start_offset or body.end_offset > len(full_report):
        raise HTTPException(status_code=400, detail="Invalid selection offsets")
    selected_from_offsets = full_report[body.start_offset:body.end_offset]
    if selected_from_offsets != selected_text:
        raise HTTPException(status_code=400, detail="Selection text does not match the provided offsets")
    service = ResearchService(model_id=DEEPRESEARCH_MODEL_ID)
    result = await service.rewrite_selection(
        query=session.get("query") or "",
        full_report=full_report,
        selected_text=selected_text,
        instruction=instruction,
        start_offset=body.start_offset,
        end_offset=body.end_offset,
    )
    return {
        "suggestion_id": str(uuid.uuid4()),
        "selected_text": selected_text,
        "rewritten_text": result["rewritten_text"],
        "summary": result["summary"],
        "start_offset": body.start_offset,
        "end_offset": body.end_offset,
    }


@router.post("/sessions/{session_id}/export-pdf")
async def export_session_pdf(session_id: str, body: ExportPdfBody):
    """将当前报告导出为 PDF。"""
    session = await research_session_repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    markdown = body.markdown if isinstance(body.markdown, str) and body.markdown.strip() else (session.get("final_report") or "")
    if not markdown.strip():
        raise HTTPException(status_code=400, detail="No report content available for PDF export")
    resolved_title = resolve_pdf_title("", markdown)
    pdf_bytes = generate_pdf_bytes(title="", markdown=markdown)
    safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", resolved_title).strip("-_.") or "deep-research-report"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'{safe_name}.pdf')}"
    }
    return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf", headers=headers)


@router.post("/sessions/{session_id}/continue")
async def continue_session_research(session_id: str, body: ContinueResearchBody):
    """用户确认章节框架后，从 research 阶段继续流式执行。"""
    session = await research_session_repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    ui_state = _get_ui_state(session)
    editable_outline = ui_state.get("editable_outline") or ui_state.get("outline_draft_full")
    if not isinstance(editable_outline, list) or not editable_outline:
        raise HTTPException(status_code=400, detail="No confirmed outline available")
    active_outline = normalize_editable_outline(editable_outline, query=session.get("query") or "")
    updated = await research_session_repository.update_outline_state(
        session_id,
        active_outline=active_outline,
        editable_outline=active_outline,
        outline=normalize_outline_for_ui(active_outline),
        outline_approval_status="approved",
        awaiting_user_input="",
        phase="researching",
        phase_detail="深度搜索中",
        research_steps=build_research_steps("researching"),
        status="running",
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    service = ResearchService(model_id=DEEPRESEARCH_MODEL_ID)
    return _create_research_stream_response(
        service=service,
        session_id=session_id,
        query=session.get("query") or "",
        user_id=session.get("user_id"),
        search_web=body.search_web if body.search_web is not None else True,
        search_local=body.search_local if body.search_local is not None else False,
        mode="continue",
        approved_outline=active_outline,
        create_session=False,
    )


class UpdateReportBody(BaseModel):
    """更新报告正文（用户编辑后保存）"""
    final_report: str


class UpdateUiStateBody(BaseModel):
    """更新思考过程等 UI 状态（outline、panel_log 等），与 research_complete 后前端提交一致"""
    ui_state: dict


@router.patch("/sessions/{session_id}/ui-state")
async def update_session_ui_state(session_id: str, body: UpdateUiStateBody):
    """合并更新会话的 ui_state（思考过程、过程日志、图表数等），用于 research_complete 后前端提交与刷新恢复。"""
    session = await research_session_repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    updated = await research_session_repository.update_ui_state(session_id, body.ui_state)
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return updated


@router.patch("/sessions/{session_id}")
async def update_session_report(session_id: str, body: UpdateReportBody):
    """更新会话的报告正文（Markdown），用于前端编辑后保存。"""
    session = await research_session_repository.get_by_id(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    updated = await research_session_repository.update_report(session_id, body.final_report)
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return updated
