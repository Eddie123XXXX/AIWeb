import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme';
import { useLocale, useTranslation } from '../context/LocaleContext';
import { Sidebar } from '../components/Sidebar';
import { InputArea } from '../components/InputArea';
import { getStoredUser } from '../utils/auth';
import { parseMarkdownWithLatex, processMarkdownHtml } from '../utils/markdown';
import {
  continueResearchStream,
  downloadResearchPdf,
  getResearchSession,
  listResearchSessions,
  rewriteResearchOutline,
  rewriteResearchSelection,
  startResearchStream,
  updateResearchOutline,
  updateResearchReport,
  updateResearchUiState,
} from '../utils/deepResearchApi';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';

/** 阶段与前端步骤对应：planning->0, researching->1, writing->2, reviewing->3 */
const PHASE_ORDER = ['planning', 'researching', 'writing', 'reviewing'];

const STEP_DEFS = [
  { id: '1', icon: 'architecture', labelKey: 'deepResearchStepPlan', descKey: 'deepResearchStepPlanDesc', color: 'blue' },
  { id: '2', icon: 'search', labelKey: 'deepResearchStepSearch', descKey: 'deepResearchStepSearchDesc', color: 'blue' },
  { id: '3', icon: 'edit_note', labelKey: 'deepResearchStepWrite', descKey: 'deepResearchStepWriteDesc', color: 'purple' },
  { id: '4', icon: 'rate_review', labelKey: 'deepResearchStepReview', descKey: 'deepResearchStepReviewDesc', color: 'primary' },
];

const iconColorMap = { blue: 'var(--color-primary)', purple: '#a78bfa', emerald: '#34d399', primary: 'var(--color-primary)' };

/** 运行中按阶段显示状态（不展开 panel 也能看到当前步骤，模仿 agentic 状态变化） */
const PHASE_STATUS_KEYS = {
  planning: 'deepResearchStatusPlanning',
  waiting_approval: 'deepResearchOutlinePending',
  researching: 'deepResearchStatusResearching',
  writing: 'deepResearchStatusWriting',
  reviewing: 'deepResearchStatusReviewing',
  re_researching: 'deepResearchStatusReResearching',
  rewriting: 'deepResearchStatusRewriting',
  revising: 'deepResearchStatusRevising',
};

function getPhaseStatusLabel(phase, t) {
  const key = PHASE_STATUS_KEYS[phase];
  return key ? t(key) : t('agenticStatusThinking');
}

function getPanelCopy(locale) {
  const isEn = locale === 'en';
  return {
    cockpit: isEn ? 'Research Topic' : '研究主题',
    deepResearch: isEn ? 'Deep Research' : '深度研究',
    sections: isEn ? 'Sections' : '章节',
    sources: isEn ? 'Sources' : '来源',
    words: isEn ? 'Words' : '字数',
    logs: isEn ? 'Logs' : '记录',
    status: isEn ? 'Status' : '状态',
    progress: isEn ? 'Current Progress' : '当前进度',
    outlineStructure: isEn ? 'Outline' : '章节结构',
    outlineGenerated: (count) => (isEn ? `${count} sections generated` : `已生成 ${count} 个章节`),
    chapterFallback: (index) => (isEn ? `Section ${index + 1}` : `章节 ${index + 1}`),
    notStarted: isEn ? 'Not started' : '未开始',
    running: isEn ? 'Running' : '进行中',
    done: isEn ? 'Completed' : '已完成',
    pending: isEn ? 'Pending' : '待处理',
    phaseLabels: {
      planning: isEn ? 'Planning' : '规划中',
      waiting_approval: isEn ? 'Waiting for approval' : '等待确认',
      researching: isEn ? 'Researching' : '检索中',
      writing: isEn ? 'Writing' : '撰写中',
      reviewing: isEn ? 'Reviewing' : '审核中',
      re_researching: isEn ? 'Re-researching' : '补充检索',
      rewriting: isEn ? 'Rewriting' : '重新撰写',
      revising: isEn ? 'Revising' : '修订中',
      completed: isEn ? 'Completed' : '已完成',
    },
    stepLabels: {
      '1': isEn ? 'Planning' : '规划问题',
      '2': isEn ? 'Research' : '检索资料',
      '3': isEn ? 'Writing' : '撰写报告',
      '4': isEn ? 'Review' : '审核修订',
    },
    stepSubtitles: {
      '1': isEn ? 'Outline' : '章节框架',
      '2': isEn ? 'Sources' : '来源汇总',
      '3': isEn ? 'Drafting' : '报告生成',
      '4': isEn ? 'Final check' : '结果确认',
    },
  };
}

function getPanelPhaseText(currentPhase, phaseDetail, t, panelCopy) {
  if (currentPhase === 'completed') return panelCopy.phaseLabels.completed;
  if (currentPhase && panelCopy.phaseLabels[currentPhase]) return panelCopy.phaseLabels[currentPhase];
  if (phaseDetail) return phaseDetail;
  return t('agenticStatusThinking');
}

function getPanelStepStateText(step, panelCopy) {
  if (step.active) return panelCopy.running;
  if (step.done) return panelCopy.done;
  return panelCopy.pending;
}

/** 仅当该步骤已执行或有内容时才在 panel 中展示（对应 agent 未被调用时不显示） */
function stepShouldShow(step, { outlineSections, sources, panelLog, report }) {
  if (step.active || step.done) return true;
  switch (step.id) {
    case '1': return outlineSections.length > 0;
    case '2': return sources.length > 0;
    case '3': return (report && report.length > 0) || panelLog.some((e) => e.type === 'thought');
    case '4': return false; // 审核仅通过 active/done 显示
    default: return false;
  }
}

const LAST_SESSION_KEY = 'deep_research_last_session_id';
function getLastSessionId() {
  try { return window.localStorage.getItem(LAST_SESSION_KEY); } catch { return null; }
}
function setLastSessionId(id) {
  try { if (id) window.localStorage.setItem(LAST_SESSION_KEY, id); else window.localStorage.removeItem(LAST_SESSION_KEY); } catch (_) {} 
}

function getPhaseStepState(currentPhase) {
  const phaseToStep = {
    planning: { doneCount: 0, activeIndex: 0 },
    waiting_approval: { doneCount: 1, activeIndex: -1 },
    researching: { doneCount: 1, activeIndex: 1 },
    re_researching: { doneCount: 1, activeIndex: 1 },
    writing: { doneCount: 2, activeIndex: 2 },
    rewriting: { doneCount: 2, activeIndex: 2 },
    reviewing: { doneCount: 3, activeIndex: 3 },
    revising: { doneCount: 3, activeIndex: 3 },
    completed: { doneCount: PHASE_ORDER.length, activeIndex: -1 },
  };
  return phaseToStep[currentPhase] || { doneCount: 0, activeIndex: -1 };
}

function buildStepsFromPhase(currentPhase, phaseDetail) {
  const { doneCount, activeIndex } = getPhaseStepState(currentPhase);
  return STEP_DEFS.map((s, idx) => ({
    ...s,
    done: idx < doneCount,
    active: idx === activeIndex,
    desc: phaseDetail && idx === activeIndex ? phaseDetail : undefined,
  }));
}

/** 从 DB 的 research_steps 构建步骤条（与子项目一致），便于恢复时展示各阶段完成情况 */
function buildStepsFromResearchSteps(researchSteps, phaseDetail) {
  if (!Array.isArray(researchSteps) || researchSteps.length === 0) return null;
  const typeToIdx = {
    planning: 0,
    researching: 1,
    re_researching: 1,
    writing: 2,
    rewriting: 2,
    reviewing: 3,
    revising: 3,
  };
  let activeIndex = -1;
  const stepStatusByIdx = {};
  researchSteps.forEach((s) => {
    const idx = typeToIdx[s.type];
    if (idx === undefined) return;
    stepStatusByIdx[idx] = s.status;
    if (s.status === 'running') activeIndex = idx;
  });
  const mappedStatuses = Object.values(stepStatusByIdx);
  const allCompleted = mappedStatuses.length === PHASE_ORDER.length && mappedStatuses.every((status) => status === 'completed');
  if (activeIndex < 0 && allCompleted) activeIndex = PHASE_ORDER.length;
  return STEP_DEFS.map((s, idx) => ({
    ...s,
    done: stepStatusByIdx[idx] === 'completed' || (activeIndex >= 0 && idx < activeIndex),
    active: idx === activeIndex,
    desc: phaseDetail && idx === activeIndex ? phaseDetail : undefined,
  }));
}

function normalizeSourceItem(raw, index = 0) {
  if (!raw || typeof raw !== 'object') return null;
  const title = raw.title || raw.source || raw.source_name || raw.name || raw.url || raw.source_url || 'N/A';
  const link = raw.link || raw.url || raw.source_url || '';
  const content = raw.content || raw.snippet || raw.summary || '';
  return {
    id: String(raw.id != null ? raw.id : index + 1),
    title,
    snippet: String(content || '').slice(0, 200),
    link,
    iconColor: 'blue',
  };
}

function normalizeOutlineSection(raw, index = 0) {
  if (!raw || typeof raw !== 'object') return null;
  return {
    id: String(raw.id || `sec_${index + 1}`),
    title: String(raw.title || ''),
    description: String(raw.description || ''),
    section_type: raw.section_type || 'mixed',
    requires_data: Boolean(raw.requires_data),
    requires_chart: Boolean(raw.requires_chart),
    priority: Number(raw.priority || index + 1),
    search_queries: Array.isArray(raw.search_queries) ? raw.search_queries.map((item) => String(item || '').trim()).filter(Boolean) : [],
    status: raw.status || 'pending',
  };
}

function normalizeOutlineList(list) {
  if (!Array.isArray(list)) return [];
  return list
    .map((item, index) => normalizeOutlineSection(item, index))
    .filter(Boolean)
    .map((item, index) => ({
      ...item,
      id: item.id || `sec_${index + 1}`,
      priority: index + 1,
    }));
}

function normalizeSourceList(list) {
  if (!Array.isArray(list)) return [];
  const seen = new Set();
  const normalized = [];
  list.forEach((item, index) => {
    const source = normalizeSourceItem(item, index);
    if (!source) return;
    const key = `${(source.link || '').trim().toLowerCase()}|${(source.title || '').trim().toLowerCase()}`;
    if (seen.has(key)) return;
    seen.add(key);
    normalized.push({ ...source, id: String(normalized.length + 1) });
  });
  return normalized;
}

function normalizeCanvasSuggestion(raw, reportText) {
  if (!raw || typeof raw !== 'object') return null;
  const startOffset = Number(raw.startOffset);
  const endOffset = Number(raw.endOffset);
  const previewStartOffset = Number(raw.previewStartOffset ?? raw.preview_start_offset);
  const previewEndOffset = Number(raw.previewEndOffset ?? raw.preview_end_offset);
  const rewrittenText = String(raw.rewrittenText || raw.rewritten_text || '');
  if (!Number.isFinite(startOffset) || !Number.isFinite(endOffset) || startOffset < 0 || endOffset <= startOffset) {
    return null;
  }
  if (typeof reportText !== 'string' || endOffset > reportText.length) {
    return null;
  }
  return {
    id: String(raw.id || `suggestion-${startOffset}-${endOffset}`),
    startOffset,
    endOffset,
    previewStartOffset: Number.isFinite(previewStartOffset) ? previewStartOffset : null,
    previewEndOffset: Number.isFinite(previewEndOffset) ? previewEndOffset : null,
    originalText: String(raw.originalText || raw.original_text || reportText.slice(startOffset, endOffset)),
    rewrittenText,
    instruction: String(raw.instruction || ''),
    summary: String(raw.summary || raw.reason || ''),
    status: raw.status || 'pending',
  };
}

function annotatePreviewRange(report, previewStart, previewEnd, annotationBuilder) {
  const baseHtml = report ? processMarkdownHtml(parseMarkdownWithLatex(report)) : '';
  if (typeof document === 'undefined' || !baseHtml || !Number.isFinite(previewStart) || !Number.isFinite(previewEnd) || previewEnd <= previewStart) {
    return baseHtml;
  }
  const wrapper = document.createElement('div');
  wrapper.innerHTML = baseHtml;
  const walker = document.createTreeWalker(wrapper, NodeFilter.SHOW_TEXT);
  const textEntries = [];
  let currentNode = walker.nextNode();
  let offset = 0;
  while (currentNode) {
    const text = currentNode.textContent || '';
    if (text.length) {
      textEntries.push({
        node: currentNode,
        start: offset,
        end: offset + text.length,
      });
      offset += text.length;
    }
    currentNode = walker.nextNode();
  }
  const startEntry = textEntries.find((entry) => entry.start <= previewStart && previewStart < entry.end);
  const endEntry = textEntries.find((entry) => entry.start < previewEnd && previewEnd <= entry.end);
  if (!startEntry || !endEntry) return baseHtml;
  const splitStartNode = startEntry.node.splitText(previewStart - startEntry.start);
  let endTargetNode = endEntry.node;
  if (startEntry.node === endEntry.node) {
    endTargetNode = splitStartNode;
  }
  const afterEndNode = endTargetNode.splitText(previewEnd - Math.max(previewStart, endEntry.start));
  const range = document.createRange();
  range.setStartBefore(splitStartNode);
  range.setEndBefore(afterEndNode);
  const extractedContents = range.extractContents();
  const fragment = annotationBuilder(extractedContents);
  range.insertNode(fragment);
  return wrapper.innerHTML;
}

function buildPreviewDiffHtml(report, suggestion) {
  if (!suggestion?.originalText) {
    return report ? processMarkdownHtml(parseMarkdownWithLatex(report)) : '';
  }
  const previewText = extractPreviewPlainText(report);
  const previewStart = Number.isFinite(suggestion.previewStartOffset)
    ? suggestion.previewStartOffset
    : previewText.indexOf(suggestion.originalText);
  if (previewStart < 0) {
    return report ? processMarkdownHtml(parseMarkdownWithLatex(report)) : '';
  }
  const previewEnd = Number.isFinite(suggestion.previewEndOffset)
    ? suggestion.previewEndOffset
    : previewStart + suggestion.originalText.length;
  return annotatePreviewRange(report, previewStart, previewEnd, (extractedContents) => {
    const deleteSpan = document.createElement('span');
    deleteSpan.className = 'deep-research-canvas__segment deep-research-canvas__segment--delete';
    deleteSpan.appendChild(extractedContents);
    const insertSpan = document.createElement('span');
    insertSpan.className = 'deep-research-canvas__segment deep-research-canvas__segment--insert';
    insertSpan.textContent = suggestion.rewrittenText || '';
    const fragment = document.createDocumentFragment();
    fragment.appendChild(deleteSpan);
    fragment.appendChild(insertSpan);
    return fragment;
  });
}

function buildPreviewSelectionHtml(report, selection) {
  if (!selection?.text) {
    return report ? processMarkdownHtml(parseMarkdownWithLatex(report)) : '';
  }
  const previewText = extractPreviewPlainText(report);
  const previewStart = Number.isFinite(selection.previewStartOffset)
    ? selection.previewStartOffset
    : previewText.indexOf(selection.text);
  if (previewStart < 0) {
    return report ? processMarkdownHtml(parseMarkdownWithLatex(report)) : '';
  }
  const previewEnd = Number.isFinite(selection.previewEndOffset)
    ? selection.previewEndOffset
    : previewStart + selection.text.length;
  return annotatePreviewRange(report, previewStart, previewEnd, (extractedContents) => {
    const selectionSpan = document.createElement('span');
    selectionSpan.className = 'deep-research-canvas__segment deep-research-canvas__segment--selected';
    selectionSpan.appendChild(extractedContents);
    const fragment = document.createDocumentFragment();
    fragment.appendChild(selectionSpan);
    return fragment;
  });
}

function collectSubstringOffsets(text, query) {
  if (!text || !query) return [];
  const offsets = [];
  let cursor = 0;
  while (cursor <= text.length) {
    const matchIndex = text.indexOf(query, cursor);
    if (matchIndex < 0) break;
    offsets.push(matchIndex);
    cursor = matchIndex + Math.max(query.length, 1);
  }
  return offsets;
}

function extractPreviewPlainText(markdown) {
  if (typeof document === 'undefined' || !markdown) return '';
  const holder = document.createElement('div');
  holder.innerHTML = processMarkdownHtml(parseMarkdownWithLatex(markdown));
  return holder.textContent || '';
}

function resolvePreviewSelectionToReport(report, previewSelection) {
  if (!report || !previewSelection?.text) return null;
  const selectedText = previewSelection.text;
  const rawOffsets = collectSubstringOffsets(report, selectedText);
  if (rawOffsets.length === 1) {
    return {
      startOffset: rawOffsets[0],
      endOffset: rawOffsets[0] + selectedText.length,
      text: selectedText,
    };
  }
  const previewText = extractPreviewPlainText(report);
  const previewOffsets = collectSubstringOffsets(previewText, selectedText);
  if (!previewOffsets.length || !rawOffsets.length) return null;
  let occurrenceIndex = previewOffsets.findIndex((offset) => offset === previewSelection.startOffset);
  if (occurrenceIndex < 0) {
    occurrenceIndex = previewOffsets.findIndex(
      (offset) => offset <= previewSelection.startOffset && previewSelection.startOffset < offset + selectedText.length
    );
  }
  if (occurrenceIndex < 0) {
    occurrenceIndex = previewOffsets.reduce((bestIndex, offset, index) => (
      Math.abs(offset - previewSelection.startOffset) < Math.abs(previewOffsets[bestIndex] - previewSelection.startOffset)
        ? index
        : bestIndex
    ), 0);
  }
  const rawStart = rawOffsets[Math.min(occurrenceIndex, rawOffsets.length - 1)];
  if (rawStart == null) return null;
  return {
    startOffset: rawStart,
    endOffset: rawStart + selectedText.length,
    text: selectedText,
  };
}

function serializeInlineNode(node) {
  if (!node) return '';
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent || '';
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return '';
  }
  const tag = node.tagName.toLowerCase();
  const children = Array.from(node.childNodes).map((child) => serializeInlineNode(child)).join('');
  if (tag === 'br') return '\n';
  if (tag === 'strong' || tag === 'b') return `**${children}**`;
  if (tag === 'em' || tag === 'i') return `*${children}*`;
  if (tag === 'code') return `\`${children}\``;
  if (tag === 'a') {
    const href = node.getAttribute('href') || '';
    return href ? `[${children || href}](${href})` : children;
  }
  return children;
}

function serializeBlockNode(node, index = 0) {
  if (!node) return '';
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent || '';
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return '';
  }
  const tag = node.tagName.toLowerCase();
  const inlineContent = () => Array.from(node.childNodes).map((child) => serializeInlineNode(child)).join('').trim();
  const inlineContentFrom = (target) => Array.from(target.childNodes).map((child) => serializeInlineNode(child)).join('').trim();
  if (/^h[1-6]$/.test(tag)) {
    const level = Number(tag.slice(1));
    return `${'#'.repeat(level)} ${inlineContent()}\n\n`;
  }
  if (tag === 'p') {
    return `${inlineContent()}\n\n`;
  }
  if (tag === 'ul') {
    const items = Array.from(node.children)
      .filter((child) => child.tagName?.toLowerCase() === 'li')
      .map((child) => `- ${inlineContentFrom(child)}`)
      .join('\n');
    return `${items}\n\n`;
  }
  if (tag === 'ol') {
    const items = Array.from(node.children)
      .filter((child) => child.tagName?.toLowerCase() === 'li')
      .map((child, itemIndex) => `${itemIndex + 1}. ${inlineContentFrom(child)}`)
      .join('\n');
    return `${items}\n\n`;
  }
  if (tag === 'pre') {
    return `\`\`\`\n${node.textContent || ''}\n\`\`\`\n\n`;
  }
  if (tag === 'blockquote') {
    const content = inlineContent()
      .split('\n')
      .map((line) => `> ${line}`)
      .join('\n');
    return `${content}\n\n`;
  }
  if (tag === 'hr') {
    return '---\n\n';
  }
  if (tag === 'div') {
    const blockContent = Array.from(node.childNodes).map((child, childIndex) => serializeBlockNode(child, childIndex)).join('');
    return blockContent || `${inlineContent()}\n\n`;
  }
  return index === 0 ? `${inlineContent()}\n\n` : inlineContent();
}

function serializeEditableArticle(root) {
  if (!root) return '';
  const markdown = Array.from(root.childNodes)
    .map((child, index) => serializeBlockNode(child, index))
    .join('')
    .replace(/\u00a0/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  return markdown;
}

function appendSectionMarkdown(previous, sectionTitle, sectionContent) {
  const content = sectionContent || '';
  if (!content) return previous || '';
  const sectionMarkdown = sectionTitle ? `## ${sectionTitle}\n\n${content}` : content;
  if (!previous) return sectionMarkdown;
  if (previous.includes(sectionMarkdown)) return previous;
  return `${previous}\n\n${sectionMarkdown}`;
}

function autoResizeTextarea(target) {
  if (!target) return;
  const el = target;
  el.style.height = 'auto';
  el.style.height = `${el.scrollHeight}px`;
}

function firstNonEmptyArray(...candidates) {
  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) {
      return candidate;
    }
  }
  return [];
}

function buildDownloadFilename(title, fallback = 'deep-research-report') {
  const base = String(title || fallback)
    .trim()
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  return base || fallback;
}

const RESEARCH_PANEL_WIDTH = 320;

export function DeepResearch({ onLogout, onOpenProfile, onOpenMemoryManage }) {
  const { locale } = useLocale();
  const t = useTranslation();
  const navigate = useNavigate();
  const { toggleTheme } = useTheme();
  const location = useLocation();
  const appsMenuRef = useRef(null);
  const downloadMenuRef = useRef(null);
  const abortRef = useRef(null);

  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 768 : true
  );
  const [rightSidebarHidden, setRightSidebarHidden] = useState(false);
  const [appsMenuOpen, setAppsMenuOpen] = useState(false);
  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);

  const [sessions, setSessions] = useState([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [currentQuery, setCurrentQuery] = useState('');
  const [pendingStartQuery, setPendingStartQuery] = useState('');

  const [report, setReport] = useState('');
  const [reportTitle, setReportTitle] = useState('');
  const [sources, setSources] = useState([]);
  const [currentPhase, setCurrentPhase] = useState('');
  const [phaseDetail, setPhaseDetail] = useState('');
  const [steps, setSteps] = useState(() => buildStepsFromPhase('', ''));
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const [thinkingPanelCollapsed, setThinkingPanelCollapsed] = useState(false);
  const [panelLog, setPanelLog] = useState([]);
  const [outlineSections, setOutlineSections] = useState([]);
  const [outlineDraft, setOutlineDraft] = useState([]);
  const [outlineApprovalStatus, setOutlineApprovalStatus] = useState('idle');
  const [outlineEditorOpen, setOutlineEditorOpen] = useState(false);
  const [outlineNaturalLanguageInstruction, setOutlineNaturalLanguageInstruction] = useState('');
  const [isSubmittingOutline, setIsSubmittingOutline] = useState(false);
  const [isRewritingOutline, setIsRewritingOutline] = useState(false);
  const [isContinuingResearch, setIsContinuingResearch] = useState(false);
  const [reportViewMode, setReportViewMode] = useState('preview');
  const [reportSaveStatus, setReportSaveStatus] = useState(null);   // null | 'saving' | 'saved' | 'error'
  const [savedReportText, setSavedReportText] = useState('');
  const [selectionState, setSelectionState] = useState(null);
  const [rewriteInstruction, setRewriteInstruction] = useState('');
  const [activeSuggestion, setActiveSuggestion] = useState(null);
  const [isRewritingSelection, setIsRewritingSelection] = useState(false);
  const panelBodyRef = useRef(null);
  const hasRestoredSessionRef = useRef(false);
  const panelLogRef = useRef([]);
  const outlineSectionsRef = useRef([]);
  const sourcesRef = useRef([]);
  const reportRef = useRef('');
  const canvasPersistTimerRef = useRef(null);
  const previewArticleRef = useRef(null);
  const previewShellRef = useRef(null);
  const selectionPopoverRef = useRef(null);
  const previewBlurTimerRef = useRef(null);
  const autoSaveTimerRef = useRef(null);
  const previewDraftRef = useRef('');
  const [hasPreviewDraftChanges, setHasPreviewDraftChanges] = useState(false);
  const [selectionPopoverPosition, setSelectionPopoverPosition] = useState(null);
  const [suggestionActionPosition, setSuggestionActionPosition] = useState(null);

  const user = getStoredUser();
  const userId = user?.id != null ? Number(user.id) : null;
  const displayName = user?.nickname || user?.username || user?.email || t('user');

  const showWelcome = !currentSessionId && !report && !isStreaming && !error;

  const fetchSessions = useCallback(async () => {
    if (userId == null) return;
    setLoadingSessions(true);
    try {
      const data = await listResearchSessions(userId);
      setSessions(data.items || []);
    } catch (e) {
      console.error('Failed to load research sessions:', e);
    } finally {
      setLoadingSessions(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    panelLogRef.current = panelLog;
    outlineSectionsRef.current = outlineSections;
    sourcesRef.current = sources;
    reportRef.current = report;
  }, [panelLog, outlineSections, sources, report]);

  const applySessionToState = useCallback((session) => {
    if (!session) return;
    const ui = session.ui_state;
    const canvasState = ui && typeof ui.canvas_state === 'object' ? ui.canvas_state : {};
    setCurrentQuery(session.query || '');
    const persistedReport = typeof canvasState.working_report === 'string' ? canvasState.working_report : '';
    const restoredReport = persistedReport || session.final_report || (ui?.streaming_report || '');
    setReport(restoredReport);
    previewDraftRef.current = restoredReport;
    setHasPreviewDraftChanges(false);
    setSavedReportText(session.final_report || (ui?.streaming_report || '') || '');
    setReportTitle(session.title || session.query || '');
    const refs = normalizeSourceList(
      firstNonEmptyArray(session.references, ui?.references, ui?.search_results)
    );
    setSources(refs);
    const restoredOutline = normalizeOutlineList(
      firstNonEmptyArray(ui?.active_outline, ui?.editable_outline, ui?.outline_draft_full, ui?.outline)
    );
    setOutlineSections(restoredOutline);
    setOutlineDraft(restoredOutline);
    setOutlineApprovalStatus(ui?.outline_approval_status || (session.status === 'waiting_approval' ? 'pending' : 'idle'));
    setOutlineEditorOpen(session.status === 'waiting_approval' || ui?.awaiting_user_input === 'outline_approval');
    setOutlineNaturalLanguageInstruction('');
    setSelectionState(null);
    setRewriteInstruction('');
    setReportViewMode('preview');
    setActiveSuggestion(normalizeCanvasSuggestion(canvasState.active_suggestion, restoredReport));
    if (ui && typeof ui === 'object') {
      if (Array.isArray(ui.panel_log)) {
        setPanelLog(ui.panel_log);
      } else {
        setPanelLog([]);
      }
      // 优先用 DB 的 research_steps 恢复步骤条（与子项目一致）
      const stepsFromDb = buildStepsFromResearchSteps(ui.research_steps, ui.phase_detail);
      const phase = session.status === 'completed' ? 'completed' : (ui.phase || '');
      if (stepsFromDb) {
        setSteps(stepsFromDb);
        setCurrentPhase(phase);
        setPhaseDetail(ui.phase_detail || '');
      } else {
        setSteps(buildStepsFromPhase(phase, ui.phase_detail || ''));
        setCurrentPhase(phase);
        setPhaseDetail(ui.phase_detail || '');
      }
    } else {
      const phase = session.status === 'completed' ? 'completed' : '';
      setSteps(buildStepsFromPhase(phase, ''));
      setCurrentPhase(phase);
      setPhaseDetail('');
      setOutlineSections([]);
      setOutlineDraft([]);
      setOutlineApprovalStatus('idle');
      setOutlineEditorOpen(false);
      setOutlineNaturalLanguageInstruction('');
      setPanelLog([]);
      setSelectionState(null);
      setRewriteInstruction('');
      setSavedReportText(session.final_report || '');
      previewDraftRef.current = session.final_report || '';
      setHasPreviewDraftChanges(false);
      setReportViewMode('preview');
      setActiveSuggestion(null);
    }
  }, []);

  // 刷新后恢复上次查看的会话：从 localStorage 取 lastSessionId，先看列表是否包含，否则按 id 拉取；若 404 则清除过期 id 避免每次打开都请求
  useEffect(() => {
    if (loadingSessions || currentSessionId != null || hasRestoredSessionRef.current) return;
    const lastId = getLastSessionId();
    if (!lastId) return;
    hasRestoredSessionRef.current = true;
    getResearchSession(lastId)
      .then((session) => {
        if (session) {
          setCurrentSessionId(lastId);
          applySessionToState(session);
          if (sessions.length === 0) setSessions([{ id: session.id, title: session.title || session.query, query: session.query }]);
        } else {
          setLastSessionId(null);
        }
      })
      .catch((e) => {
        console.error('Failed to restore research session:', e);
        setLastSessionId(null);
      });
  }, [loadingSessions, sessions, currentSessionId, applySessionToState]);

  const handleSelectConversation = useCallback(
    async (id) => {
      if (!id) return;
      setCurrentSessionId(id);
      setLastSessionId(id);
      setCurrentQuery('');
      setReport('');
      setReportTitle('');
      setSources([]);
      setReportViewMode('preview');
      setReportSaveStatus(null);
      setSavedReportText('');
      previewDraftRef.current = '';
      setHasPreviewDraftChanges(false);
      setSelectionState(null);
      setRewriteInstruction('');
      setActiveSuggestion(null);
      setOutlineSections([]);
      setOutlineDraft([]);
      setOutlineApprovalStatus('idle');
      setOutlineEditorOpen(false);
      setOutlineNaturalLanguageInstruction('');
      setPanelLog([]);
      try {
        const session = await getResearchSession(id);
        if (session) {
          applySessionToState(session);
        } else {
          setLastSessionId(null);
          setCurrentSessionId(null);
          setCurrentQuery('');
        }
      } catch (e) {
        console.error('Failed to load session:', e);
        setCurrentSessionId(null);
        setCurrentQuery('');
      }
    },
    [applySessionToState]
  );

  const handleNewChat = useCallback(() => {
    setCurrentSessionId(null);
    setCurrentQuery('');
    setReport('');
    setReportTitle('');
    setSources([]);
    setCurrentPhase('');
    setPhaseDetail('');
    setSteps(buildStepsFromPhase('', ''));
    setError(null);
    setReportViewMode('preview');
    setReportSaveStatus(null);
    setSavedReportText('');
    previewDraftRef.current = '';
    setHasPreviewDraftChanges(false);
    setSelectionState(null);
    setRewriteInstruction('');
    setActiveSuggestion(null);
    setPanelLog([]);
    setOutlineSections([]);
    setOutlineDraft([]);
    setOutlineApprovalStatus('idle');
    setOutlineEditorOpen(false);
    setOutlineNaturalLanguageInstruction('');
  }, []);

  const handleRenameConversation = useCallback((id, newTitle) => {
    setSessions((prev) => prev.map((c) => (c.id === id ? { ...c, title: newTitle } : c)));
  }, []);

  const handleDeleteConversation = useCallback((id) => {
    setSessions((prev) => prev.filter((c) => c.id !== id));
    if (currentSessionId === id) {
      setCurrentSessionId(null);
      setCurrentQuery('');
      setReport('');
      setReportTitle('');
      setOutlineSections([]);
      setOutlineDraft([]);
      setOutlineApprovalStatus('idle');
      setOutlineEditorOpen(false);
      setOutlineNaturalLanguageInstruction('');
      setReportViewMode('preview');
      setReportSaveStatus(null);
      setSavedReportText('');
      previewDraftRef.current = '';
      setHasPreviewDraftChanges(false);
      setSelectionState(null);
      setRewriteInstruction('');
      setActiveSuggestion(null);
    }
  }, [currentSessionId]);

  const runStream = useCallback(
    async (query, sessionId, options = {}) => {
      const mode = options.mode || 'planning_only';
      const isContinueMode = mode === 'continue';
      setError(null);
      setCurrentQuery(query);
      if (!isContinueMode) {
        setReport('');
        setSavedReportText('');
        previewDraftRef.current = '';
        setHasPreviewDraftChanges(false);
        setReportTitle(query.slice(0, 80));
        setSources([]);
        setCurrentPhase('planning');
        setPhaseDetail('');
        setSteps(buildStepsFromPhase('planning', ''));
        setPanelLog([]);
        setOutlineSections([]);
        setOutlineDraft([]);
        setOutlineApprovalStatus('draft');
        setOutlineEditorOpen(false);
        setOutlineNaturalLanguageInstruction('');
        setReportViewMode('preview');
        setSelectionState(null);
        setRewriteInstruction('');
        setActiveSuggestion(null);
      } else {
        setCurrentPhase('researching');
        setPhaseDetail('');
        setSteps(buildStepsFromPhase('researching', ''));
        setOutlineApprovalStatus('approved');
        setOutlineEditorOpen(false);
        setIsContinuingResearch(true);
      }
      setIsStreaming(true);
      abortRef.current = new AbortController();
      try {
        const res = isContinueMode
          ? await continueResearchStream(
              sessionId,
              { search_web: true, search_local: false },
              abortRef.current.signal
            )
          : await startResearchStream(
              {
                query,
                session_id: sessionId,
                user_id: userId ?? undefined,
                model_id: 'default',
                search_web: true,
                search_local: false,
                mode: 'planning_only',
              },
              abortRef.current.signal
            );
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        let stopCurrentStream = false;
        while (true) {
          const { value, done: readerDone } = await reader.read();
          if (readerDone) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const raw = line.slice(6).trim();
              if (raw === '[DONE]' || raw === '') continue;
              try {
                const ev = JSON.parse(raw);
                const typ = ev.type;
                if (stopCurrentStream && typ !== 'awaiting_outline_confirmation' && typ !== 'done') {
                  continue;
                }
                if (typ === 'phase') {
                  setCurrentPhase(ev.phase || '');
                  setPhaseDetail(ev.content || '');
                  setSteps(buildStepsFromPhase(ev.phase || '', ev.content || ''));
                } else if (typ === 'research_step' && ev.content) {
                  setPhaseDetail(ev.content.subtitle || ev.content.title || '');
                } else if (typ === 'thought' && ev.content) {
                  const text = typeof ev.content === 'string' ? ev.content : (ev.content.content || '');
                  if (text) setPanelLog((prev) => [...prev.slice(-99), { type: 'thought', text }]);
                } else if (typ === 'phase_detail' && ev.content) {
                  const text = typeof ev.content === 'string' ? ev.content : (ev.content.content || '');
                  if (text) setPanelLog((prev) => [...prev.slice(-99), { type: 'phase_detail', text }]);
                } else if (typ === 'outline' && ev.content?.outline) {
                  const outline = normalizeOutlineList(ev.content.outline);
                  setOutlineSections(outline);
                  setOutlineDraft(outline);
                  setOutlineApprovalStatus('pending');
                  setPhaseDetail(t('deepResearchOutlineDone') || `已生成 ${outline.length} 个章节`);
                  setPanelLog((prev) => [...prev.slice(-99), { type: 'outline', text: `已生成 ${outline.length} 个章节` }]);
                } else if (typ === 'awaiting_outline_confirmation' && ev.content) {
                  const outline = normalizeOutlineList(ev.content.outline);
                  setOutlineSections(outline);
                  setOutlineDraft(outline);
                  setOutlineApprovalStatus('pending');
                  setOutlineEditorOpen(true);
                  setCurrentPhase('waiting_approval');
                  setPhaseDetail(ev.content.message || t('deepResearchOutlineWaitingHint'));
                  setSteps(buildStepsFromPhase('waiting_approval', ev.content.message || ''));
                  setIsStreaming(false);
                  setIsContinuingResearch(false);
                  stopCurrentStream = true;
                  fetchSessions();
                } else if (typ === 'search_result' && ev.content?.fact) {
                  if (!isContinueMode && stopCurrentStream) continue;
                  setSources((prev) => {
                    const f = ev.content.fact;
                    const next = normalizeSourceList([
                      ...prev,
                      {
                        title: f.title || f.source || f.source_name,
                        link: f.link || f.url || f.source_url,
                        content: f.content || f.snippet,
                        source: f.source || f.source_name,
                      },
                    ]);
                    return next;
                  });
                } else if (typ === 'section_content' && (ev.content?.markdown != null || ev.content?.content != null)) {
                  if (!isContinueMode && stopCurrentStream) continue;
                  const sectionText = ev.content.markdown ?? ev.content.content ?? '';
                  const sectionTitle = ev.content.section_title || '';
                  setReport((prev) => appendSectionMarkdown(prev, sectionTitle, sectionText));
                } else if (typ === 'report_draft' && (ev.content?.markdown != null || ev.content?.content != null)) {
                  if (!isContinueMode && stopCurrentStream) continue;
                  setReport(ev.content.markdown ?? ev.content.content ?? '');
                } else if (typ === 'research_complete') {
                  if (!isContinueMode && stopCurrentStream) continue;
                  if (ev.final_report != null) {
                    setReport(ev.final_report);
                    previewDraftRef.current = ev.final_report;
                    setHasPreviewDraftChanges(false);
                    setSavedReportText(ev.final_report);
                  }
                  setCurrentPhase('completed');
                  setPhaseDetail('');
                  setSteps(buildStepsFromPhase('completed', ''));
                  if (Array.isArray(ev.references) && ev.references.length) {
                    setSources(normalizeSourceList(ev.references));
                  }
                  if (ev.outline && Array.isArray(ev.outline)) {
                    const outline = normalizeOutlineList(ev.outline);
                    setOutlineSections(outline);
                    setOutlineDraft(outline);
                  }
                  setOutlineApprovalStatus('approved');
                  setOutlineEditorOpen(false);
                  setOutlineNaturalLanguageInstruction('');
                  setReportViewMode('preview');
                  setSelectionState(null);
                  setRewriteInstruction('');
                  setActiveSuggestion(null);
                  setIsStreaming(false);
                  setIsContinuingResearch(false);
                  fetchSessions();
                  const uiState = {
                    outline: ev.outline || outlineSectionsRef.current,
                    panel_log: panelLogRef.current,
                    references: Array.isArray(ev.references) ? ev.references : sourcesRef.current,
                    search_results: Array.isArray(ev.references) ? ev.references : sourcesRef.current,
                    streaming_report: ev.final_report ?? reportRef.current,
                  };
                  updateResearchUiState(sessionId, uiState).catch((err) => console.error('Save ui_state failed:', err));
                } else if (typ === 'error') {
                  setError(ev.content || 'Unknown error');
                  setIsStreaming(false);
                  setIsContinuingResearch(false);
                } else if (typ === 'done') {
                  setIsStreaming(false);
                  setIsContinuingResearch(false);
                  fetchSessions();
                }
              } catch (_) {}
            }
            if (stopCurrentStream) {
              try {
                await reader.cancel();
              } catch (_) {}
              break;
            }
          }
        }
        setIsStreaming(false);
        setIsContinuingResearch(false);
        fetchSessions();
      } catch (e) {
        if (e.name === 'AbortError') return;
        setError(e.message || 'Stream failed');
        setIsStreaming(false);
        setIsContinuingResearch(false);
      }
    },
    [userId, t, fetchSessions]
  );

  const handleOutlineItemChange = useCallback((index, field, value) => {
    setOutlineDraft((prev) => prev.map((item, itemIndex) => (
      itemIndex === index
        ? {
            ...item,
            [field]: value,
            search_queries:
              field === 'title' && (!Array.isArray(item.search_queries) || item.search_queries.length === 0)
                ? [value].filter(Boolean)
                : item.search_queries,
          }
        : item
    )));
    setOutlineApprovalStatus('editing');
  }, []);

  const handleAddOutlineItem = useCallback(() => {
    setOutlineDraft((prev) => [
      ...prev,
      normalizeOutlineSection({ title: t('deepResearchOutlineEmptyTitle') }, prev.length),
    ]);
    setOutlineApprovalStatus('editing');
  }, [t]);

  const handleDeleteOutlineItem = useCallback((index) => {
    setOutlineDraft((prev) => prev.filter((_, itemIndex) => itemIndex !== index).map((item, itemIndex) => ({
      ...item,
      priority: itemIndex + 1,
    })));
    setOutlineApprovalStatus('editing');
  }, []);

  const handleRewriteOutline = useCallback(async () => {
    if (!currentSessionId || !outlineNaturalLanguageInstruction.trim()) return;
    setIsRewritingOutline(true);
    try {
      const updated = await rewriteResearchOutline(currentSessionId, outlineNaturalLanguageInstruction.trim());
      applySessionToState(updated);
      setOutlineEditorOpen(true);
    } catch (e) {
      setError(e.message || 'Rewrite outline failed');
    } finally {
      setIsRewritingOutline(false);
    }
  }, [currentSessionId, outlineNaturalLanguageInstruction, applySessionToState]);

  const handleContinueResearch = useCallback(async () => {
    if (!currentSessionId || !currentQuery || outlineDraft.length === 0 || isStreaming) return;
    setIsSubmittingOutline(true);
    try {
      const updated = await updateResearchOutline(currentSessionId, outlineDraft);
      applySessionToState(updated);
      setOutlineEditorOpen(false);
      setOutlineApprovalStatus('approved');
      await runStream(currentQuery, currentSessionId, { mode: 'continue' });
    } catch (e) {
      setError(e.message || 'Continue research failed');
    } finally {
      setIsSubmittingOutline(false);
    }
  }, [currentSessionId, currentQuery, outlineDraft, isStreaming, applySessionToState, runStream]);

  const handleSend = useCallback(
    (text) => {
      const query = (text || '').trim();
      if (!query || isStreaming) return false;
      setPendingStartQuery(query);
      return false;
    },
    [isStreaming]
  );

  const handleConfirmStart = useCallback(() => {
    const query = pendingStartQuery.trim();
    if (!query || isStreaming) return;
    const sessionId = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `dr-${Date.now()}`;
    setCurrentSessionId(sessionId);
    setCurrentQuery(query);
    setLastSessionId(sessionId);
    setPendingStartQuery('');
    runStream(query, sessionId);
  }, [isStreaming, pendingStartQuery, runStream]);

  const handleCancelStart = useCallback(() => {
    setPendingStartQuery('');
  }, []);

  const handleCancelStream = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
  }, []);

  const persistReportDraft = useCallback(async (draftReport) => {
    if (!currentSessionId || draftReport == null) return;
    setReportSaveStatus('saving');
    try {
      await updateResearchReport(currentSessionId, draftReport);
      setSavedReportText(draftReport);
      previewDraftRef.current = draftReport;
      setHasPreviewDraftChanges(false);
      setReportSaveStatus('saved');
      setTimeout(() => setReportSaveStatus(null), 2000);
    } catch (e) {
      setReportSaveStatus('error');
      setTimeout(() => setReportSaveStatus(null), 3000);
    }
  }, [currentSessionId]);

  const handlePreviewInput = useCallback(() => {
    if (!previewArticleRef.current || activeSuggestion) return;
    previewDraftRef.current = serializeEditableArticle(previewArticleRef.current);
    setHasPreviewDraftChanges(true);
    setReportSaveStatus(null);
    setSelectionPopoverPosition(null);
  }, [activeSuggestion]);

  const handlePreviewBlur = useCallback(() => {
    if (!previewArticleRef.current || activeSuggestion) return;
    const nextReport = serializeEditableArticle(previewArticleRef.current);
    previewDraftRef.current = nextReport;
    setReport(nextReport);
    if (previewBlurTimerRef.current) {
      window.clearTimeout(previewBlurTimerRef.current);
    }
    previewBlurTimerRef.current = window.setTimeout(() => {
      const activeEl = document.activeElement;
      if (selectionPopoverRef.current && activeEl && selectionPopoverRef.current.contains(activeEl)) {
        return;
      }
      setSelectionPopoverPosition(null);
    }, 0);
  }, [activeSuggestion]);

  const syncPreviewSelection = useCallback(() => {
    const articleEl = previewArticleRef.current;
    if (!articleEl || reportViewMode !== 'preview' || currentPhase !== 'completed' || activeSuggestion) return;
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      setSelectionState(null);
      setSelectionPopoverPosition(null);
      return;
    }
    const range = selection.getRangeAt(0);
    if (!articleEl.contains(range.commonAncestorContainer)) {
      setSelectionState(null);
      setSelectionPopoverPosition(null);
      return;
    }
    const selectedText = selection.toString();
    if (!selectedText.trim()) {
      setSelectionState(null);
      setSelectionPopoverPosition(null);
      return;
    }
    const rangeRect = range.getBoundingClientRect();
    const shellRect = previewShellRef.current?.getBoundingClientRect();
    if (shellRect) {
      const estimatedWidth = Math.min(384, Math.max(shellRect.width - 32, 260));
      const centeredLeft = rangeRect.left + (rangeRect.width / 2) - shellRect.left;
      const maxLeft = Math.max(16, shellRect.width - estimatedWidth - 16);
      setSelectionPopoverPosition({
        top: rangeRect.bottom - shellRect.top + 12,
        left: Math.min(Math.max(16, centeredLeft - (estimatedWidth / 2)), maxLeft),
        width: estimatedWidth,
      });
    }
    const prefixRange = range.cloneRange();
    prefixRange.selectNodeContents(articleEl);
    prefixRange.setEnd(range.startContainer, range.startOffset);
    const previewSelection = {
      startOffset: prefixRange.toString().length,
      endOffset: prefixRange.toString().length + selectedText.length,
      text: selectedText,
    };
    const latestReport = serializeEditableArticle(articleEl) || report;
    previewDraftRef.current = latestReport;
    setHasPreviewDraftChanges(latestReport !== savedReportText);
    setReport(latestReport);
    const resolvedSelection = resolvePreviewSelectionToReport(latestReport, previewSelection);
    if (!resolvedSelection) {
      setSelectionState(null);
      setSelectionPopoverPosition(null);
      setError(t('deepResearchPreviewSelectionUnsupported'));
      return;
    }
    setError((prev) => (prev === t('deepResearchPreviewSelectionUnsupported') ? null : prev));
    setSelectionState({
      ...resolvedSelection,
      previewStartOffset: previewSelection.startOffset,
      previewEndOffset: previewSelection.endOffset,
    });
  }, [activeSuggestion, currentPhase, report, reportViewMode, savedReportText, t]);

  const handleRewriteSelection = useCallback(async () => {
    if (!currentSessionId || !selectionState || !rewriteInstruction.trim() || !selectionState.text.trim()) return;
    const latestReport = previewArticleRef.current && currentPhase === 'completed' && !activeSuggestion
      ? serializeEditableArticle(previewArticleRef.current) || report
      : report;
    setIsRewritingSelection(true);
    try {
      const result = await rewriteResearchSelection(currentSessionId, {
        selected_text: selectionState.text,
        instruction: rewriteInstruction.trim(),
        full_report: latestReport,
        start_offset: selectionState.startOffset,
        end_offset: selectionState.endOffset,
      });
      setReport(latestReport);
      previewDraftRef.current = latestReport;
      setActiveSuggestion(normalizeCanvasSuggestion({
        id: result.suggestion_id,
        startOffset: result.start_offset,
        endOffset: result.end_offset,
        previewStartOffset: selectionState.previewStartOffset,
        previewEndOffset: selectionState.previewEndOffset,
        originalText: result.selected_text,
        rewrittenText: result.rewritten_text,
        instruction: rewriteInstruction.trim(),
        summary: result.summary,
        status: 'pending',
      }, latestReport));
      setSelectionState(null);
      setSelectionPopoverPosition(null);
      setRewriteInstruction('');
    } catch (e) {
      setError(e.message || 'Rewrite selection failed');
    } finally {
      setIsRewritingSelection(false);
    }
  }, [activeSuggestion, currentPhase, currentSessionId, report, rewriteInstruction, selectionState]);

  const handleAcceptSuggestion = useCallback(() => {
    if (!activeSuggestion) return;
    const nextReport = `${report.slice(0, activeSuggestion.startOffset)}${activeSuggestion.rewrittenText}${report.slice(activeSuggestion.endOffset)}`;
    setReport(nextReport);
    previewDraftRef.current = nextReport;
    setHasPreviewDraftChanges(true);
    setReportSaveStatus(null);
    setActiveSuggestion(null);
    setSelectionState(null);
    setSelectionPopoverPosition(null);
    setSuggestionActionPosition(null);
    setRewriteInstruction('');
  }, [activeSuggestion, report]);

  const handleRejectSuggestion = useCallback(() => {
    setActiveSuggestion(null);
    setSelectionState(null);
    setSelectionPopoverPosition(null);
    setSuggestionActionPosition(null);
    setRewriteInstruction('');
  }, []);

  const getLatestExportMarkdown = useCallback(() => {
    if (previewArticleRef.current && currentPhase === 'completed' && !activeSuggestion) {
      return serializeEditableArticle(previewArticleRef.current) || report || '';
    }
    return report || '';
  }, [activeSuggestion, currentPhase, report]);

  const handleDownloadMarkdown = useCallback(() => {
    const markdown = getLatestExportMarkdown();
    if (!markdown) return;
    const filename = `${buildDownloadFilename(reportTitle || currentQuery || t('deepResearch'))}.md`;
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
    setDownloadMenuOpen(false);
  }, [currentQuery, getLatestExportMarkdown, reportTitle, t]);

  const handleDownloadPdf = useCallback(async () => {
    if (!currentSessionId) return;
    const markdown = getLatestExportMarkdown();
    if (!markdown) return;
    const title = reportTitle || currentQuery || t('deepResearch');
    try {
      const { blob, filename } = await downloadResearchPdf(currentSessionId, { title, markdown });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename || `${buildDownloadFilename(title)}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      setDownloadMenuOpen(false);
    } catch (e) {
      setError(e.message || 'Download PDF failed');
    }
  }, [currentQuery, currentSessionId, getLatestExportMarkdown, reportTitle, t]);

  useEffect(() => {
    setSteps(buildStepsFromPhase(currentPhase, phaseDetail));
  }, [currentPhase, phaseDetail]);

  useEffect(() => {
    if (!appsMenuOpen && !downloadMenuOpen) return;
    const handleClickOutside = (e) => {
      if (appsMenuRef.current && !appsMenuRef.current.contains(e.target)) setAppsMenuOpen(false);
      if (downloadMenuRef.current && !downloadMenuRef.current.contains(e.target)) setDownloadMenuOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [appsMenuOpen, downloadMenuOpen]);

  useEffect(() => {
    setAppsMenuOpen(false);
    setDownloadMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!outlineEditorOpen) return;
    const textareas = document.querySelectorAll('.deep-research-outline-editor__description-input');
    textareas.forEach((node) => autoResizeTextarea(node));
  }, [outlineEditorOpen, outlineDraft]);

  useEffect(() => {
    if (!activeSuggestion || !previewArticleRef.current || !previewShellRef.current) {
      setSuggestionActionPosition(null);
      return;
    }
    const anchor = previewArticleRef.current.querySelector(
      '.deep-research-canvas__segment--insert, .deep-research-canvas__segment--delete'
    );
    if (!anchor) {
      setSuggestionActionPosition(null);
      return;
    }
    const anchorRect = anchor.getBoundingClientRect();
    const shellRect = previewShellRef.current.getBoundingClientRect();
    const actionWidth = 96;
    const preferredLeft = anchorRect.right - shellRect.left - actionWidth;
    const maxLeft = Math.max(12, shellRect.width - actionWidth - 12);
    const preferredTop = anchorRect.top - shellRect.top - 42;
    setSuggestionActionPosition({
      top: preferredTop > 8 ? preferredTop : anchorRect.bottom - shellRect.top + 8,
      left: Math.min(Math.max(12, preferredLeft), maxLeft),
    });
  }, [activeSuggestion, report]);

  useEffect(() => () => {
    if (previewBlurTimerRef.current) {
      window.clearTimeout(previewBlurTimerRef.current);
    }
    if (autoSaveTimerRef.current) {
      window.clearTimeout(autoSaveTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (!currentSessionId || currentPhase !== 'completed') return;
    if (canvasPersistTimerRef.current) {
      clearTimeout(canvasPersistTimerRef.current);
    }
    const payload = {
      canvas_state: {
        view_mode: reportViewMode,
        working_report: report,
        active_suggestion: activeSuggestion
          ? {
              id: activeSuggestion.id,
              startOffset: activeSuggestion.startOffset,
              endOffset: activeSuggestion.endOffset,
              previewStartOffset: activeSuggestion.previewStartOffset,
              previewEndOffset: activeSuggestion.previewEndOffset,
              originalText: activeSuggestion.originalText,
              rewrittenText: activeSuggestion.rewrittenText,
              instruction: activeSuggestion.instruction,
              summary: activeSuggestion.summary,
              status: activeSuggestion.status,
            }
          : null,
      },
    };
    canvasPersistTimerRef.current = setTimeout(() => {
      updateResearchUiState(currentSessionId, payload).catch((err) => {
        console.error('Persist canvas state failed:', err);
      });
    }, 500);
    return () => {
      if (canvasPersistTimerRef.current) {
        clearTimeout(canvasPersistTimerRef.current);
      }
    };
  }, [activeSuggestion, currentPhase, currentSessionId, report, reportViewMode]);

  useEffect(() => {
    if (currentPhase !== 'completed' || !currentSessionId || activeSuggestion) return;
    if (!hasPreviewDraftChanges) return;
    if (autoSaveTimerRef.current) {
      window.clearTimeout(autoSaveTimerRef.current);
    }
    autoSaveTimerRef.current = window.setTimeout(() => {
      const nextReport = previewDraftRef.current || report;
      if (!nextReport || nextReport === savedReportText) return;
      persistReportDraft(nextReport);
    }, 1200);
    return () => {
      if (autoSaveTimerRef.current) {
        window.clearTimeout(autoSaveTimerRef.current);
      }
    };
  }, [activeSuggestion, currentPhase, currentSessionId, hasPreviewDraftChanges, persistReportDraft, report, savedReportText]);

  const conversationList = sessions.map((s) => ({ id: s.id, title: s.title || s.query || t('deepResearch') }));
  const panelCopy = getPanelCopy(locale);
  const hasRewriteInstruction = outlineNaturalLanguageInstruction.trim().length > 0;
  const showCanvasTab = currentPhase === 'completed' && Boolean(report);
  const hasUnsavedCanvasChanges = currentPhase === 'completed' && (hasPreviewDraftChanges || report !== savedReportText);
  const showSelectionPopover = showCanvasTab && Boolean(selectionState) && !activeSuggestion;
  const previewReportHtml = activeSuggestion
    ? buildPreviewDiffHtml(report, activeSuggestion)
    : selectionState
    ? buildPreviewSelectionHtml(report, selectionState)
    : (report ? processMarkdownHtml(parseMarkdownWithLatex(report)) : '');

  const stepsWithLabels = steps.map((s) => ({
    ...s,
    label: s.labelKey ? t(s.labelKey) : s.id,
    desc: s.desc || (s.descKey ? t(s.descKey) : ''),
  }));
  const reportLength = (report || '').replace(/\s+/g, '').length;

  return (
    <div className="rag-root">
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen((prev) => !prev)}
        onNewChat={handleNewChat}
        onLogout={onLogout}
        onOpenProfile={onOpenProfile}
        onOpenMemoryManage={onOpenMemoryManage}
        conversations={conversationList}
        currentConversationId={currentSessionId}
        onSelectConversation={handleSelectConversation}
        onRenameConversation={handleRenameConversation}
        onDeleteConversation={handleDeleteConversation}
        loadingConversations={loadingSessions}
      />

      <main className="rag-main">
        <header className="rag-header deep-research-header">
          <div className="rag-header__actions">
            <div className="header__model" ref={downloadMenuRef} style={{ position: 'relative' }}>
              <button
                type="button"
                className="header__icon-btn"
                title={t('download')}
                aria-label={t('download')}
                aria-haspopup="menu"
                aria-expanded={downloadMenuOpen}
                onClick={() => setDownloadMenuOpen((v) => !v)}
              >
                <span className="material-symbols-outlined">download</span>
              </button>
              {downloadMenuOpen && (
                <div className="header__model-menu header__apps-menu" role="menu">
                  <button
                    type="button"
                    className="header__model-menu-item"
                    role="menuitem"
                    onClick={handleDownloadMarkdown}
                    disabled={!report}
                  >
                    <span className="material-symbols-outlined header__model-menu-emoji">article</span>
                    <span>{t('deepResearchDownloadMarkdown')}</span>
                  </button>
                  <button
                    type="button"
                    className="header__model-menu-item"
                    role="menuitem"
                    onClick={handleDownloadPdf}
                    disabled={!report || !currentSessionId}
                  >
                    <span className="material-symbols-outlined header__model-menu-emoji">picture_as_pdf</span>
                    <span>{t('deepResearchDownloadPdf')}</span>
                  </button>
                </div>
              )}
            </div>
            <button
              type="button"
              className="header__icon-btn"
              title={t('theme')}
              aria-label={t('theme')}
              onClick={toggleTheme}
            >
              <span className="material-symbols-outlined theme-icon-light">light_mode</span>
              <span className="material-symbols-outlined theme-icon-dark" aria-hidden="true">
                dark_mode
              </span>
            </button>
            <div className="header__model" ref={appsMenuRef} style={{ position: 'relative' }}>
              <button
                type="button"
                className="header__icon-btn"
                title={t('apps')}
                aria-label={t('apps')}
                aria-haspopup="menu"
                aria-expanded={appsMenuOpen}
                onClick={() => setAppsMenuOpen((v) => !v)}
              >
                <span className="material-symbols-outlined">apps</span>
              </button>
              {appsMenuOpen && (
                <div className="header__model-menu header__apps-menu" role="menu">
                  <Link
                    to="/"
                    className={'header__model-menu-item' + (location.pathname === '/' ? ' header__model-menu-item--active' : '')}
                    role="menuitem"
                    onClick={() => setAppsMenuOpen(false)}
                  >
                    <span className="material-symbols-outlined header__model-menu-emoji">chat</span>
                    <span>{t('aiChat')}</span>
                  </Link>
                  <Link
                    to="/wiki"
                    className={'header__model-menu-item' + (location.pathname === '/wiki' ? ' header__model-menu-item--active' : '')}
                    role="menuitem"
                    onClick={() => setAppsMenuOpen(false)}
                  >
                    <span className="material-symbols-outlined header__model-menu-emoji">dashboard</span>
                    <span>{t('knowledgeBase')}</span>
                  </Link>
                  <Link
                    to="/deep-research"
                    className={'header__model-menu-item' + (location.pathname === '/deep-research' ? ' header__model-menu-item--active' : '')}
                    role="menuitem"
                    onClick={() => setAppsMenuOpen(false)}
                  >
                    <span className="material-symbols-outlined header__model-menu-emoji">search</span>
                    <span>{t('deepResearch')}</span>
                  </Link>
                </div>
              )}
            </div>
          </div>
        </header>

        {showWelcome ? (
          <section className="welcome welcome--deep-research">
            <div className="welcome__inner animate-fade-in">
              <div className="welcome__head">
                <h1 className="welcome__title">
                  <span className="welcome__title-logo-wrap">
                    <img src={logoImg} alt="" className="welcome__title-logo logo-img--light" />
                    <img src={logoImgDark} alt="" className="welcome__title-logo logo-img--dark" />
                  </span>
                  <span className="welcome__greeting">{t('hello')}{displayName}</span>
                </h1>
                <p className="welcome__subtitle">{t('deepResearchWelcomeSubtitle')}</p>
                {userId == null && (
                  <p className="welcome__hint" style={{ fontSize: '0.8rem', color: 'var(--color-charcoal-light)', marginTop: '0.5rem' }}>
                    {t('deepResearchLoginHint')}
                  </p>
                )}
              </div>
              <InputArea
                onSend={handleSend}
                isStreaming={isStreaming}
                onCancelStream={handleCancelStream}
                hasChat={false}
                showAttach={false}
                showMore={false}
              />
            </div>
          </section>
        ) : (
          <div className="deep-research-content">
            <aside
              className={`deep-research-thinking${thinkingPanelCollapsed ? ' deep-research-thinking--collapsed' : ''}`}
              style={{ width: thinkingPanelCollapsed ? 0 : RESEARCH_PANEL_WIDTH, minWidth: thinkingPanelCollapsed ? 0 : RESEARCH_PANEL_WIDTH, flexShrink: 0 }}
            >
              {/* 与 agentic 一致：无步骤时不展示 panel；运行中按阶段显示状态（规划中/检索中/撰写中等），不展开也能看到当前步骤 */}
              {(isStreaming || (stepsWithLabels.length > 0 && stepsWithLabels.some((s) => s.done || s.active))) && (
              <div className="agentic-panel agentic-panel--deep-research">
                <div className="agentic-panel__header">
                  <div className="agentic-panel__status">
                    <span
                      className={
                        isStreaming && currentPhase && currentPhase !== 'completed'
                          ? 'agentic-panel__logo agentic-panel__logo--spinning'
                          : 'agentic-panel__logo'
                      }
                    >
                      <img src={logoImg} alt="" className="agentic-panel__logo-img logo-img--light" />
                      <img src={logoImgDark} alt="" className="agentic-panel__logo-img logo-img--dark" />
                    </span>
                    <span className="agentic-panel__status-text">
                      <strong>
                        {isStreaming && currentPhase && currentPhase !== 'completed'
                          ? getPhaseStatusLabel(currentPhase, t)
                          : currentPhase === 'completed'
                          ? t('agenticStatusDone')
                          : stepsWithLabels.some((s) => s.done || s.active)
                          ? t('thinkingFlow')
                          : t('agenticStatusWaiting')}
                      </strong>
                    </span>
                  </div>
                </div>
                <div className="deep-research-panel__hero">
                  <div className="deep-research-panel__hero-top">
                    <div className="deep-research-panel__hero-title-wrap">
                      <div className="deep-research-panel__eyebrow">{panelCopy.cockpit}</div>
                      <div className="deep-research-panel__hero-title">{reportTitle || panelCopy.deepResearch}</div>
                    </div>
                  </div>
                </div>

                {stepsWithLabels.length > 0 && stepsWithLabels.some((s) => s.done || s.active) && (
                  <div className="agentic-panel__body" ref={panelBodyRef}>
                    {stepsWithLabels
                      .filter((step) => stepShouldShow(step, { outlineSections, sources, panelLog, report }))
                      .map((step) => {
                        const isStaticStep = step.id === '2' || step.id === '3';
                        const isPinnedExpandedStep = step.id === '4';
                        const isNonInteractiveStep = isStaticStep || isPinnedExpandedStep;
                        const summaryClassName = `deep-research-panel__step-summary${step.active ? ' deep-research-panel__step-summary--active' : ''}${isNonInteractiveStep ? ' deep-research-panel__step-summary--static' : ''}`;
                        const summaryContent = (
                          <span className={summaryClassName}>
                            <span className={`deep-research-panel__step-icon deep-research-panel__step-icon--${step.color}`}>
                              <span className="material-symbols-outlined">{step.icon}</span>
                            </span>
                            <span className="deep-research-panel__step-main">
                              <span className="deep-research-panel__step-label">{panelCopy.stepLabels[step.id] || step.label}</span>
                              <span className="deep-research-panel__step-subtitle">{panelCopy.stepSubtitles[step.id] || step.desc}</span>
                            </span>
                            <span className="deep-research-panel__step-trailing">
                              {step.id === '2' && sources.length > 0 && (
                                <span className="deep-research-panel__step-badge">{sources.length}</span>
                              )}
                              <span className={`deep-research-panel__step-state${step.active ? ' deep-research-panel__step-state--active' : step.done ? ' deep-research-panel__step-state--done' : ''}`}>
                                {getPanelStepStateText(step, panelCopy)}
                              </span>
                            </span>
                          </span>
                        );

                        if (isStaticStep) {
                          return (
                            <div
                              key={step.id}
                              className={`agentic-panel__event deep-research-panel__step deep-research-panel__step--static${step.active ? ' agentic-panel__event--active' : ''}`}
                            >
                              <div className="agentic-panel__event-summary deep-research-panel__step-summary-shell">
                                {summaryContent}
                              </div>
                            </div>
                          );
                        }

                        if (isPinnedExpandedStep) {
                          return (
                            <div
                              key={step.id}
                              className={`agentic-panel__event deep-research-panel__step deep-research-panel__step--pinned${step.active ? ' agentic-panel__event--active' : ''}`}
                            >
                              <div className="agentic-panel__event-summary deep-research-panel__step-summary-shell">
                                {summaryContent}
                              </div>
                              <div className="agentic-panel__event-content deep-research-panel__step-content">
                                <div className="deep-research-sidepanel__overview">
                                  <div className="deep-research-sidepanel__stats">
                                    <div className="deep-research-sidepanel__stat">
                                      <span>{panelCopy.logs}</span>
                                      <strong>{panelLog.length}</strong>
                                    </div>
                                    <div className="deep-research-sidepanel__stat">
                                      <span>{panelCopy.words}</span>
                                      <strong>{reportLength}</strong>
                                    </div>
                                    <div className="deep-research-sidepanel__stat">
                                      <span>{panelCopy.sections}</span>
                                      <strong>{outlineSections.length}</strong>
                                    </div>
                                    <div className="deep-research-sidepanel__stat">
                                      <span>{panelCopy.sources}</span>
                                      <strong>{sources.length}</strong>
                                    </div>
                                  </div>
                                  {phaseDetail && (
                                    <div className="deep-research-sidepanel__summary-card">
                                      <div className="deep-research-sidepanel__subhead">{panelCopy.progress}</div>
                                      <p>{phaseDetail}</p>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        }

                        return (
                          <details
                            key={step.id}
                            className={`agentic-panel__event deep-research-panel__step${step.active ? ' agentic-panel__event--active' : ''}`}
                            open={step.active || (step.id === '1' && currentPhase === 'waiting_approval')}
                          >
                            <summary className="agentic-panel__event-summary">
                              {summaryContent}
                            </summary>
                            <div className="agentic-panel__event-content deep-research-panel__step-content">
                              {step.id === '1' && outlineSections.length > 0 && (
                                <div className="deep-research-panel__outline">
                                  <p className="deep-research-panel__meta">{panelCopy.outlineGenerated(outlineSections.length)}</p>
                                  <div className="deep-research-sidepanel__summary-card">
                                    <div className="deep-research-sidepanel__subhead">{panelCopy.outlineStructure}</div>
                                    <ol className="deep-research-panel__list">
                                      {outlineSections.map((s, i) => (
                                        <li key={s.id || i}>
                                          {s.title || panelCopy.chapterFallback(i)}
                                        </li>
                                      ))}
                                    </ol>
                                    <div className="deep-research-outline-card__actions">
                                      {(currentPhase === 'waiting_approval' || outlineApprovalStatus === 'pending' || outlineApprovalStatus === 'editing') && (
                                        <p className="deep-research-outline-card__hint">{t('deepResearchOutlineWaitingHint')}</p>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          </details>
                        );
                      })}
                  </div>
                )}
              </div>
              )}

            </aside>

            <button
              type="button"
              className={`deep-research-panel-toggle${thinkingPanelCollapsed ? ' deep-research-panel-toggle--collapsed' : ''}`}
              onClick={() => setThinkingPanelCollapsed((prev) => !prev)}
              aria-label={thinkingPanelCollapsed ? t('agenticToggleExpand') : t('agenticToggleCollapse')}
              title={thinkingPanelCollapsed ? t('agenticToggleExpand') : t('agenticToggleCollapse')}
            >
              <span className="material-symbols-outlined">
                {thinkingPanelCollapsed ? 'chevron_right' : 'chevron_left'}
              </span>
            </button>

            <section className="deep-research-report">
              <div className="deep-research-report__inner">
                <div className="deep-research-report__head">
                  {report && currentSessionId && (
                    <div className="deep-research-report__toolbar">
                      {showCanvasTab && (
                        <span className={'deep-research-report__save-indicator' + (hasUnsavedCanvasChanges ? ' deep-research-report__save-indicator--dirty' : '')}>
                          {reportSaveStatus === 'saving'
                            ? t('saving')
                            : reportSaveStatus === 'error'
                            ? t('saveFailed')
                            : hasUnsavedCanvasChanges
                            ? t('deepResearchCanvasUnsaved')
                            : t('deepResearchCanvasSynced')}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                {error && (
                  <div className="deep-research-report__error" role="alert">
                    {error}
                  </div>
                )}
                {(!showCanvasTab || reportViewMode === 'preview') && (
                  <div ref={previewShellRef} className="deep-research-report__preview-shell">
                    <article
                      ref={previewArticleRef}
                      className={`deep-research-report__article chat__message--markdown${showCanvasTab && !activeSuggestion ? ' deep-research-report__article--selectable deep-research-report__article--editable' : ''}`}
                      contentEditable={showCanvasTab && !activeSuggestion}
                      suppressContentEditableWarning
                      onInput={showCanvasTab ? handlePreviewInput : undefined}
                      onBlur={showCanvasTab ? handlePreviewBlur : undefined}
                      onMouseUp={showCanvasTab ? syncPreviewSelection : undefined}
                      onTouchEnd={showCanvasTab ? syncPreviewSelection : undefined}
                      dangerouslySetInnerHTML={{
                        __html: previewReportHtml,
                      }}
                    />
                    {showSelectionPopover && (
                      <div
                        ref={selectionPopoverRef}
                        className="deep-research-canvas__popover deep-research-canvas__popover--preview"
                        role="dialog"
                        aria-label={t('deepResearchCanvasRewrite')}
                        style={selectionPopoverPosition || undefined}
                        onMouseDown={(e) => e.stopPropagation()}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="deep-research-canvas__popover-head">
                          <strong>{t('deepResearchCanvasRewrite')}</strong>
                          <button
                            type="button"
                            className="deep-research-canvas__popover-close"
                            onClick={() => {
                              setSelectionState(null);
                              setSelectionPopoverPosition(null);
                              setRewriteInstruction('');
                            }}
                            aria-label={t('cancel')}
                          >
                            <span className="material-symbols-outlined">close</span>
                          </button>
                        </div>
                        <textarea
                          className="deep-research-canvas__instruction"
                          rows="3"
                          value={rewriteInstruction}
                          onChange={(e) => setRewriteInstruction(e.target.value)}
                          placeholder={t('deepResearchCanvasRewritePlaceholder')}
                        />
                        <div className="deep-research-canvas__popover-actions">
                          <button
                            type="button"
                            className="logout-confirm-btn logout-confirm-btn--cancel"
                            onClick={() => {
                              setSelectionState(null);
                                setSelectionPopoverPosition(null);
                              setRewriteInstruction('');
                            }}
                          >
                            {t('cancel')}
                          </button>
                          <button
                            type="button"
                            className="logout-confirm-btn logout-confirm-btn--confirm"
                            onClick={handleRewriteSelection}
                            disabled={isRewritingSelection || !rewriteInstruction.trim()}
                          >
                            {isRewritingSelection ? `${t('deepResearchCanvasRewrite')}...` : t('deepResearchCanvasRewriteAction')}
                          </button>
                        </div>
                      </div>
                    )}
                    {activeSuggestion && (
                      <div
                        className="deep-research-canvas__inline-actions"
                        style={suggestionActionPosition || undefined}
                      >
                        <button
                          type="button"
                          className="deep-research-canvas__inline-action deep-research-canvas__inline-action--reject"
                          onClick={handleRejectSuggestion}
                          aria-label={t('deepResearchCanvasReject')}
                          title={t('deepResearchCanvasReject')}
                        >
                          <span className="material-symbols-outlined">close</span>
                        </button>
                        <button
                          type="button"
                          className="deep-research-canvas__inline-action deep-research-canvas__inline-action--accept"
                          onClick={handleAcceptSuggestion}
                          aria-label={t('deepResearchCanvasAccept')}
                          title={t('deepResearchCanvasAccept')}
                        >
                          <span className="material-symbols-outlined">check</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}
                {!report && !isStreaming && !error && (!showCanvasTab || reportViewMode === 'preview') && (
                  <p className="deep-research-report__placeholder">{t('deepResearchSearchPlaceholder')}</p>
                )}
              </div>
            </section>
          </div>
        )}
        {outlineEditorOpen && currentSessionId && (
          <div
            className="logout-confirm-overlay"
            role="dialog"
            aria-modal="true"
            aria-labelledby="deep-research-outline-editor-title"
          >
            <div className="logout-confirm-backdrop" />
            <div className="logout-confirm-card deep-research-outline-editor" onClick={(e) => e.stopPropagation()}>
              <div className="deep-research-outline-editor__head">
                <div className="deep-research-outline-editor__head-copy">
                  <h2 id="deep-research-outline-editor-title" className="logout-confirm-title">
                    {t('deepResearchOutlineEditorTitle')}
                  </h2>
                </div>
                <span className="deep-research-outline-editor__badge">{t('deepResearchOutlinePending')}</span>
              </div>

              <div className="deep-research-outline-editor__list">
                {outlineDraft.map((section, index) => (
                  <div key={section.id || index} className="deep-research-outline-editor__item">
                    <div className="deep-research-outline-editor__item-header">
                      <div className="deep-research-outline-editor__item-heading">
                        <span className="deep-research-outline-editor__item-index">{index + 1}</span>
                        <input
                          type="text"
                          className="deep-research-outline-editor__title-input"
                          value={section.title}
                          onChange={(e) => handleOutlineItemChange(index, 'title', e.target.value)}
                          placeholder={t('deepResearchOutlineEmptyTitle')}
                          aria-label={t('deepResearchOutlineTitle')}
                        />
                      </div>
                      <div className="deep-research-outline-editor__item-actions">
                        <button
                          type="button"
                          className="deep-research-outline-editor__action-icon deep-research-outline-editor__action-icon--danger"
                          onClick={() => handleDeleteOutlineItem(index)}
                          disabled={outlineDraft.length <= 1}
                          title={t('deepResearchOutlineDeleteSection')}
                          aria-label={t('deepResearchOutlineDeleteSection')}
                        >
                          <span className="material-symbols-outlined">delete</span>
                        </button>
                      </div>
                    </div>
                    <div className="deep-research-outline-editor__field-grid">
                      <textarea
                        className="deep-research-outline-editor__description-input"
                        rows="1"
                        value={section.description}
                        onChange={(e) => handleOutlineItemChange(index, 'description', e.target.value)}
                        onInput={(e) => autoResizeTextarea(e.currentTarget)}
                        placeholder={t('deepResearchOutlineDescriptionPlaceholder')}
                        aria-label={t('deepResearchOutlineDescription')}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className="deep-research-outline-editor__toolbar">
                <button type="button" className="deep-research-outline-editor__add" onClick={handleAddOutlineItem}>
                  <span className="material-symbols-outlined">add</span>
                  {t('deepResearchOutlineAddSection')}
                </button>
              </div>

              <div className="deep-research-outline-editor__rewrite">
                <div className="deep-research-outline-editor__rewrite-label">
                  {t('deepResearchOutlineRewriteLabel')}
                </div>
                <div className="deep-research-outline-editor__rewrite-box">
                  <textarea
                    rows="3"
                    value={outlineNaturalLanguageInstruction}
                    onChange={(e) => setOutlineNaturalLanguageInstruction(e.target.value)}
                    placeholder={t('deepResearchOutlineRewritePlaceholder')}
                  />
                </div>
              </div>

              <div className="deep-research-outline-editor__footer">
                <button
                  type="button"
                  className="logout-confirm-btn logout-confirm-btn--confirm"
                  onClick={hasRewriteInstruction ? handleRewriteOutline : handleContinueResearch}
                  disabled={
                    hasRewriteInstruction
                      ? isRewritingOutline
                      : (isSubmittingOutline || isStreaming || isContinuingResearch || outlineDraft.length === 0)
                  }
                >
                  {hasRewriteInstruction
                    ? (isRewritingOutline ? `${t('deepResearchOutlineRewriteBtn')}...` : t('deepResearchOutlineRewriteBtn'))
                    : (isContinuingResearch ? `${t('deepResearchOutlineContinue')}...` : t('deepResearchOutlineContinue'))}
                </button>
              </div>
            </div>
          </div>
        )}

        {pendingStartQuery && (
          <div
            className="logout-confirm-overlay"
            role="dialog"
            aria-modal="true"
            aria-labelledby="deep-research-confirm-title"
          >
            <div className="logout-confirm-backdrop" onClick={handleCancelStart} />
            <div className="logout-confirm-card deep-research-confirm-card" onClick={(e) => e.stopPropagation()}>
              <h2 id="deep-research-confirm-title" className="logout-confirm-title">
                {t('deepResearchConfirmStartTitle')}
              </h2>
              <p className="logout-confirm-desc">{t('deepResearchConfirmStartDesc')}</p>
              <div className="deep-research-confirm-query">
                <div className="deep-research-confirm-query__label">{t('deepResearchConfirmTopic')}</div>
                <div className="deep-research-confirm-query__value">{pendingStartQuery}</div>
              </div>
              <div className="logout-confirm-actions">
                <button
                  type="button"
                  className="logout-confirm-btn logout-confirm-btn--cancel"
                  onClick={handleCancelStart}
                >
                  {t('cancel')}
                </button>
                <button
                  type="button"
                  className="logout-confirm-btn logout-confirm-btn--confirm"
                  onClick={handleConfirmStart}
                >
                  {t('deepResearchConfirmStartBtn')}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>

      <aside className={`rag-right-sidebar${rightSidebarHidden ? ' rag-right-sidebar--collapsed' : ''}`}>
        <div className="rag-right-sidebar__head">
          <h3 className="rag-right-sidebar__title">
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
              source
            </span>
            {t('sources')}
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span
              className="rag-right-sidebar__badge"
              style={{
                fontSize: 10,
                background: 'var(--hover-bg-strong)',
                border: '1px solid var(--color-card-border)',
                padding: '0.125rem 0.5rem',
                borderRadius: 9999,
                fontWeight: 700,
                color: 'var(--color-charcoal-light)',
              }}
            >
              {sources.length}
            </span>
            <button
              type="button"
              className="sidebar__menu-btn"
              title={rightSidebarHidden ? t('expandDocPanel') : t('collapseDocPanel')}
              aria-label={rightSidebarHidden ? t('expandDocPanel') : t('collapseDocPanel')}
              onClick={() => setRightSidebarHidden((v) => !v)}
            >
              <span className="material-symbols-outlined">dock_to_left</span>
            </button>
          </div>
        </div>
        <div className="rag-right-sidebar__body">
          {sources.map((s) => (
            <div key={s.id} className="rag-doc-card">
              <div className="rag-doc-card__from">
                <span
                  className="material-symbols-outlined"
                  style={{ color: iconColorMap[s.iconColor] || 'var(--color-primary)', fontSize: 16 }}
                >
                  article
                </span>
                <span className="rag-doc-card__doc-name" title={s.title}>
                  {s.link ? (
                    <a href={s.link} target="_blank" rel="noopener noreferrer">
                      {s.title}
                    </a>
                  ) : (
                    s.title
                  )}
                </span>
              </div>
              <p className="rag-doc-card__snippet">{s.snippet}</p>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}
