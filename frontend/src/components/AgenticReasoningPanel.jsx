import React from 'react';
import { useTranslation } from '../context/LocaleContext';
import logoImg from '../../img/Ling_Flowing_Logo.png';
import logoImgDark from '../../img/Image.png';

// Agentic 推理过程头部：左侧圆形 logo，中间粗体状态文案，右侧展开图标按钮。
// 当处于推理中（有事件且未完成）时，让 logo 旋转以代替加载圆圈。
export function AgenticReasoningPanel({ events = [], status, isStreaming, expanded, onToggle }) {
  const t = useTranslation();
  const hasEvents = Array.isArray(events) && events.length > 0;
  const spinning = isStreaming && status && status !== 'done';

  let statusKey = null;
  if (status === 'thinking') {
    statusKey = 'agenticStatusThinking';
  } else if (status === 'action') {
    statusKey = 'agenticStatusAction';
  } else if (status === 'observation') {
    statusKey = 'agenticStatusObservation';
  } else if (status === 'done') {
    statusKey = 'agenticStatusDone';
  }
  const statusText = statusKey ? t(statusKey) : '';
  const waitingText = t('agenticStatusWaiting');
  const doneText = t('agenticStatusDone');
  const toggleExpandText = t('agenticToggleExpand');
  const toggleCollapseText = t('agenticToggleCollapse');
  const stripStepPrefix = (text) =>
    (text || '')
      .replace(/^\s*Step\s*\d+\s*[·.\-:：]?\s*/i, '')
      .replace(/^\s*第\s*\d+\s*步\s*[·.\-:：]?\s*/, '')
      .replace(/^\s*(Thought|Action|Observation)\s*[:：]\s*/i, '')
      .replace(/^\s*(思考|动作|观察)\s*[:：]\s*/, '')
      .trim();

  return (
    <div className="agentic-panel">
      <div className="agentic-panel__header">
        <div className="agentic-panel__status">
          <span
            className={
              spinning
                ? 'agentic-panel__logo agentic-panel__logo--spinning'
                : 'agentic-panel__logo'
            }
          >
            <img
              src={logoImg}
              alt=""
              className="agentic-panel__logo-img logo-img--light"
            />
            <img
              src={logoImgDark}
              alt=""
              className="agentic-panel__logo-img logo-img--dark"
            />
          </span>
          <span className="agentic-panel__status-text">
            <strong>{spinning ? `${statusText}…` : hasEvents ? statusText || doneText : waitingText}</strong>
          </span>
          {hasEvents && (
            <button
              type="button"
              className="agentic-panel__toggle"
              onClick={onToggle}
            >
              <span className="material-symbols-outlined agentic-panel__toggle-icon">
                {expanded ? 'expand_less' : 'expand_more'}
              </span>
              <span className="visually-hidden">
                {expanded ? toggleCollapseText : toggleExpandText}
              </span>
            </button>
          )}
        </div>
      </div>

      {expanded && hasEvents && (
        <div className="agentic-panel__body">
          {events.map((e, idx) => {
            const key = `${e.type}-${e.step}-${idx}`;
            const label =
              e.type === 'thought'
                ? t('agenticLabelThought')
                : e.type === 'action'
                ? `${t('agenticLabelAction')}${e.tool ? `: ${t('agenticActionCallingTool')} "${e.tool}"` : ''}`
                : t('agenticLabelObservation');
            return (
              <details key={key} className="agentic-panel__event" open={e.type === 'thought'}>
                <summary className="agentic-panel__event-summary">{label}</summary>
                <div className="agentic-panel__event-content">
                  {stripStepPrefix(e.content) || (e.type === 'action' ? t('agenticCallingTool') : '')}
                </div>
              </details>
            );
          })}
        </div>
      )}
    </div>
  );
}

