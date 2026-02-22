import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslation } from '../context/LocaleContext';

export function InputArea({
  onSend,
  isStreaming,
  onCancelStream,
  hasChat,
  showAttach = true,
  showMore = true,
}) {
  const t = useTranslation();
  const [value, setValue] = useState('');
  const textareaRef = useRef(null);
  const moreRef = useRef(null);
  const [enteringFixed, setEnteringFixed] = useState(false);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setValue('');
  }, [value, onSend]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSendClick = () => {
    if (isStreaming) {
      onCancelStream();
    } else {
      handleSubmit();
    }
  };

  // 让“更多选项”的浮窗在点击外部时自动收起
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!moreRef.current) return;
      if (moreRef.current.contains(event.target)) return;

      const details = moreRef.current.querySelector('details');
      if (details && details.open) {
        details.open = false;
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, []);

  // 当 from “未开始对话” 切换到 “有对话（固定在底部）” 时，加一小段滑动/渐隐动画
  useEffect(() => {
    if (!hasChat) return;
    setEnteringFixed(true);
    const timer = setTimeout(() => {
      setEnteringFixed(false);
    }, 260);
    return () => clearTimeout(timer);
  }, [hasChat]);

  const wrapperClass =
    'input-area' +
    (hasChat ? ' input-area--fixed' : ' input-area--inline') +
    (hasChat && enteringFixed ? ' input-area--fixed-enter' : '');

  return (
    <div className={wrapperClass}>
      <div className="input-area__inner">
        <div className="input-box">
          <textarea
            ref={textareaRef}
            className="input-box__textarea"
            placeholder={t('placeholder')}
            rows={1}
            aria-label={t('inputMessage')}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
          />
          <div className="input-box__row">
            <div className="input-box__tools">
              {showAttach && (
                <button
                  type="button"
                  className="input-box__tool-btn"
                  title="附加文件"
                  aria-label="附加文件"
                >
                  <span className="material-symbols-outlined">attach_file</span>
                </button>
              )}
              <button
                type="button"
                className="input-box__tool-btn"
                title="语音输入"
                aria-label="语音输入"
              >
                <span className="material-symbols-outlined">mic</span>
              </button>
              {showMore && (
                <div className="input-box__more" ref={moreRef}>
                  <details>
                    <summary title="更多选项">
                      <span className="material-symbols-outlined">more_horiz</span>
                    </summary>
                    <div className="input-box__dropdown">
                      <button type="button" className="input-box__dropdown-btn">
                        <span className="material-symbols-outlined">description</span>
                        <span>浏览本地文件</span>
                      </button>
                      <button type="button" className="input-box__dropdown-btn">
                        <span className="material-symbols-outlined">mic_external_on</span>
                        <span>语音输入设置</span>
                      </button>
                      <hr />
                      <button type="button" className="input-box__dropdown-btn">
                        <span className="material-symbols-outlined">tune</span>
                        <span>回复偏好</span>
                      </button>
                    </div>
                  </details>
                </div>
              )}
            </div>
            <button
              type="button"
              className="input-box__send"
              aria-label={isStreaming ? t('stopGenerate') : t('send')}
              title={isStreaming ? t('stopGenerate') : t('send')}
              onClick={handleSendClick}
            >
              <span className="material-symbols-outlined">
                {isStreaming ? 'pause' : 'send'}
              </span>
            </button>
          </div>
        </div>
        <p className="input-area__disclaimer">
          {t('disclaimer')}
        </p>
      </div>
    </div>
  );
}
