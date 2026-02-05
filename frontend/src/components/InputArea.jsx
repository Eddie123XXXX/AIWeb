import React, { useState, useRef, useCallback } from 'react';

export function InputArea({ onSend, isStreaming, onCancelStream }) {
  const [value, setValue] = useState('');
  const textareaRef = useRef(null);

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

  return (
    <div className="input-area">
      <div className="input-area__inner">
        <div className="input-box">
          <textarea
            ref={textareaRef}
            className="input-box__textarea"
            placeholder="在此输入你的问题..."
            rows={1}
            aria-label="输入消息"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
          />
          <div className="input-box__row">
            <div className="input-box__tools">
              <button
                type="button"
                className="input-box__tool-btn"
                title="附加文件"
                aria-label="附加文件"
              >
                <span className="material-symbols-outlined">attach_file</span>
              </button>
              <button
                type="button"
                className="input-box__tool-btn"
                title="语音输入"
                aria-label="语音输入"
              >
                <span className="material-symbols-outlined">mic</span>
              </button>
              <div className="input-box__more">
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
            </div>
            <button
              type="button"
              className="input-box__send"
              aria-label={isStreaming ? '暂停生成' : '发送'}
              title={isStreaming ? '暂停生成' : '发送'}
              onClick={handleSendClick}
            >
              <span className="material-symbols-outlined">
                {isStreaming ? 'pause' : 'send'}
              </span>
            </button>
          </div>
        </div>
        <p className="input-area__disclaimer">
          AI 可能产生不准确信息，请务必核实重要内容。
        </p>
      </div>
    </div>
  );
}
