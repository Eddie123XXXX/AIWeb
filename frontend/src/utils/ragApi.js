/**
 * RAG 知识库 API 封装
 * 与后端 /api/rag 路由对接
 */
import { apiUrl } from './api';
import { getAuthHeaders } from './auth';

/** 默认笔记本 ID，新建笔记时使用（无 notebook 时） */
export const DEFAULT_NOTEBOOK_ID = 'default';

/**
 * 获取笔记本列表
 * @returns {Promise<Array<{ id: string, title: string, source_count: number, last_updated?: string }>>}
 */
export async function listNotebooks() {
  const resp = await fetch(apiUrl('/api/rag/notebooks?limit=50&offset=0'), {
    headers: getAuthHeaders(),
  });
  if (!resp.ok) {
    if (resp.status === 404) return [];
    throw new Error(`获取笔记本列表失败: ${resp.status}`);
  }
  const data = await resp.json();
  return Array.isArray(data) ? data : [];
}

/**
 * 创建笔记本
 * @param {{ title?: string }} params
 * @returns {Promise<{ id: string, title: string }>}
 */
export async function createNotebook({ title = '未命名笔记本' } = {}) {
  const resp = await fetch(apiUrl('/api/rag/notebooks'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ title }),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(err || `创建笔记本失败: ${resp.status}`);
  }
  return resp.json();
}

/**
 * 更新笔记本（如重命名）
 * @param {string} notebookId
 * @param {{ title: string }} params
 * @returns {Promise<{ id: string, title: string }>}
 */
export async function updateNotebook(notebookId, { title }) {
  const resp = await fetch(apiUrl(`/api/rag/notebooks/${notebookId}`), {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ title: title || '未命名笔记本' }),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(err || `更新笔记本失败: ${resp.status}`);
  }
  return resp.json();
}

/**
 * 删除笔记本
 * @param {string} notebookId
 * @returns {Promise<{ deleted: string }>}
 */
export async function deleteNotebook(notebookId) {
  const resp = await fetch(apiUrl(`/api/rag/notebooks/${notebookId}`), {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(err || `删除笔记本失败: ${resp.status}`);
  }
  return resp.json();
}

/**
 * 混合检索
 * @param {{ notebook_id: string, query: string, document_ids?: string[] }} params
 * @returns {Promise<{ query: string, hits: Array<{ chunk_id: string, document_id: string, content: string, score: number }>, total: number }>}
 */
export async function ragSearch({ notebook_id, query, document_ids }) {
  const resp = await fetch(apiUrl('/api/rag/search'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      notebook_id,
      query: query.trim(),
      document_ids: document_ids || undefined,
    }),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(err || `RAG 检索失败: ${resp.status}`);
  }
  return resp.json();
}

/**
 * 获取笔记本下的文档列表
 * @param {string} notebookId
 * @returns {Promise<Array<{ id: string, filename: string, byte_size: number, status: string }>>}
 */
export async function listRAGDocuments(notebookId) {
  const resp = await fetch(
    apiUrl(`/api/rag/documents?notebook_id=${encodeURIComponent(notebookId)}&limit=50&offset=0`),
    { headers: getAuthHeaders() }
  );
  if (!resp.ok) {
    if (resp.status === 404) return [];
    throw new Error(`获取文档列表失败: ${resp.status}`);
  }
  const data = await resp.json();
  return Array.isArray(data) ? data : [];
}

/**
 * 从检索结果构建注入 LLM 的上下文文本
 * @param {{ hits: Array<{ content: string, document_id?: string }> }} searchResult
 * @returns {string}
 */
export function buildRAGContextFromHits(searchResult) {
  const hits = searchResult?.hits || [];
  if (hits.length === 0) {
    return '未检索到相关知识库内容。';
  }
  return hits
    .map((h, i) => `[${i + 1}] ${(h.content || '').trim()}`)
    .filter(Boolean)
    .join('\n\n');
}

/**
 * 上传文档到知识库
 * @param {{ file: File, notebook_id: string }} params
 * @returns {Promise<{ id: string, filename: string, status: string }>}
 */
export async function uploadRAGDocument({ file, notebook_id }) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('notebook_id', notebook_id);
  const resp = await fetch(apiUrl('/api/rag/documents/upload'), {
    method: 'POST',
    headers: getAuthHeaders(),
    body: formData,
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(err || `上传失败: ${resp.status}`);
  }
  return resp.json();
}

/**
 * 触发文档解析流水线
 * @param {string} docId
 * @returns {Promise<{ id: string, status: string }>}
 */
export async function processRAGDocument(docId) {
  const resp = await fetch(apiUrl(`/api/rag/documents/${docId}/process`), {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(err || `解析失败: ${resp.status}`);
  }
  return resp.json();
}

/**
 * 获取文档还原的 Markdown 片段（供「展开文件」预览）
 * @param {string} docId
 * @returns {Promise<{ filename: string, segments: Array<{ type: 'parent'|'standalone', content: string }> }>}
 */
export async function getDocumentMarkdown(docId) {
  const resp = await fetch(apiUrl(`/api/rag/documents/${docId}/markdown`), {
    headers: getAuthHeaders(),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(err || `获取文档失败: ${resp.status}`);
  }
  return resp.json();
}

/**
 * 删除知识库文档
 * @param {string} docId
 * @returns {Promise<void>}
 */
export async function deleteRAGDocument(docId) {
  const resp = await fetch(apiUrl(`/api/rag/documents/${docId}`), {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(err || `删除失败: ${resp.status}`);
  }
}
