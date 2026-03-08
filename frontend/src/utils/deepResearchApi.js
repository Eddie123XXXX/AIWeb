/**
 * 深度研究 API：流式研究、历史列表、会话详情
 * 与后端 /api/agentic/deepresearch 对接
 */
import { apiUrl } from './api';
import { getAuthHeaders } from './auth';

/**
 * 发起流式深度研究（POST），返回 Response，调用方自行 read body 解析 SSE
 */
export function startResearchStream(body, signal) {
  return fetch(apiUrl('/api/agentic/deepresearch/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
    signal,
  });
}

export function continueResearchStream(sessionId, body = {}, signal) {
  return fetch(apiUrl(`/api/agentic/deepresearch/sessions/${encodeURIComponent(sessionId)}/continue`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
    signal,
  });
}

/**
 * 获取当前用户的深度研究历史列表
 */
export async function listResearchSessions(userId, limit = 50, offset = 0) {
  const url = apiUrl(`/api/agentic/deepresearch/sessions?user_id=${encodeURIComponent(userId)}&limit=${limit}&offset=${offset}`);
  const res = await fetch(url, { headers: getAuthHeaders() });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * 获取单条深度研究会话详情（含 final_report）
 */
export async function getResearchSession(sessionId) {
  const res = await fetch(apiUrl(`/api/agentic/deepresearch/sessions/${encodeURIComponent(sessionId)}`), {
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    if (res.status === 404) return null;
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * 更新会话的报告正文（用户在前端编辑 Markdown 后保存）
 */
export async function updateResearchReport(sessionId, finalReport) {
  const res = await fetch(apiUrl(`/api/agentic/deepresearch/sessions/${encodeURIComponent(sessionId)}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ final_report: finalReport }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * 更新会话的 UI 状态（思考过程：outline、panel_log、chart_count），用于 research_complete 后保存与刷新恢复
 */
export async function updateResearchUiState(sessionId, uiState) {
  const res = await fetch(apiUrl(`/api/agentic/deepresearch/sessions/${encodeURIComponent(sessionId)}/ui-state`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ ui_state: uiState }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function updateResearchOutline(sessionId, outline) {
  const res = await fetch(apiUrl(`/api/agentic/deepresearch/sessions/${encodeURIComponent(sessionId)}/outline`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ outline }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function rewriteResearchOutline(sessionId, instruction) {
  const res = await fetch(apiUrl(`/api/agentic/deepresearch/sessions/${encodeURIComponent(sessionId)}/rewrite-outline`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify({ instruction }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function rewriteResearchSelection(sessionId, body) {
  const res = await fetch(apiUrl(`/api/agentic/deepresearch/sessions/${encodeURIComponent(sessionId)}/rewrite-selection`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function downloadResearchPdf(sessionId, body) {
  const res = await fetch(apiUrl(`/api/agentic/deepresearch/sessions/${encodeURIComponent(sessionId)}/export-pdf`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  const blob = await res.blob();
  const disposition = res.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const filename = match ? decodeURIComponent(match[1]) : 'deep-research-report.pdf';
  return { blob, filename };
}
