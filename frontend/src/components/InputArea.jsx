import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useTranslation } from '../context/LocaleContext';
import { apiUrl } from '../utils/api';
import { getAuthHeaders } from '../utils/auth';
import pdfIcon from '../../img/file type icon/PDF (1).png';
import wordIcon from '../../img/file type icon/DOCX.png';
import sheetIcon from '../../img/file type icon/XLS.png';
import textIcon from '../../img/file type icon/DOCX.png';
import genericFileIcon from '../../img/file type icon/DOCX.png';

const SpeechRecognitionAPI =
  typeof window !== 'undefined' &&
  (window.SpeechRecognition || window.webkitSpeechRecognition);

export function InputArea({
  onSend,
  isStreaming,
  onCancelStream,
  hasChat,
  onAttachFiles,
  attachedFiles = [],
  attachError = null,
  onRemoveAttachedFile,
  showAttach = true,
  showMore = true,
}) {
  const t = useTranslation();
  const [value, setValue] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [voiceTranscribing, setVoiceTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState(null);
  const textareaRef = useRef(null);
  const moreRef = useRef(null);
  const fileInputRef = useRef(null);
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const [enteringFixed, setEnteringFixed] = useState(false);

  const handleSubmit = useCallback(() => {
    const text = (value + (interimTranscript || '')).trim();
    if (!text) return;
    onSend(text);
    setValue('');
    setInterimTranscript('');
  }, [value, interimTranscript, onSend]);

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

  const handleAttachClick = () => {
    if (isStreaming) return;
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileChange = (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    if (onAttachFiles) {
      onAttachFiles(Array.from(files));
    }
    // 允许选择同一个文件多次
    e.target.value = '';
  };

  // 语音识别：浏览器支持则用 Web Speech API 实时转写；否则用录音上传 Qwen ASR
  const toggleVoiceInput = useCallback(() => {
    if (isStreaming) return;
    setVoiceError(null);

    // 麦克风必须在「安全上下文」下使用：仅 https 或 http://localhost / 127.0.0.1
    if (typeof window !== 'undefined' && !window.isSecureContext) {
      setVoiceError(t('voiceInsecureContext'));
      return;
    }

    if (SpeechRecognitionAPI) {
      // 浏览器原生语音识别
      if (isListening) {
        if (recognitionRef.current) recognitionRef.current.stop();
        setIsListening(false);
        setInterimTranscript('');
        return;
      }
      try {
        const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = document.documentElement.lang === 'en' ? 'en-US' : 'zh-CN';
        recognition.onresult = (event) => {
          let finalText = '';
          let interimText = '';
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) finalText += transcript;
            else interimText += transcript;
          }
          if (finalText) setValue((prev) => (prev ? `${prev} ${finalText}` : finalText));
          setInterimTranscript(interimText || '');
        };
        recognition.onend = () => {
          setIsListening(false);
          setInterimTranscript('');
        };
        recognition.onerror = (event) => {
          if (event.error === 'not-allowed') setVoiceError(t('voicePermissionDenied'));
          setIsListening(false);
          setInterimTranscript('');
        };
        recognitionRef.current = recognition;
        recognition.start();
        setIsListening(true);
      } catch (err) {
        setVoiceError(t('voiceUnsupported'));
        setIsListening(false);
      }
      return;
    }

    // 浏览器不支持：录音上传，后端 Qwen3-ASR-Flash 转写
    if (isListening || voiceTranscribing) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      return;
    }

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        streamRef.current = stream;
        chunksRef.current = [];
        const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
        const recorder = new MediaRecorder(stream, { mimeType: mime });
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunksRef.current.push(e.data);
        };
        recorder.onstop = async () => {
          stream.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
          mediaRecorderRef.current = null;
          setIsListening(false);
          if (chunksRef.current.length === 0) {
            setVoiceError(t('voiceUnsupported'));
            return;
          }
          const blob = new Blob(chunksRef.current, { type: mime });
          setVoiceTranscribing(true);
          try {
            const formData = new FormData();
            formData.append('audio', blob, 'recording.webm');
            const resp = await fetch(apiUrl('/api/asr/transcribe'), {
              method: 'POST',
              headers: { ...getAuthHeaders() },
              body: formData,
            });
            if (!resp.ok) {
              const err = await resp.json().catch(() => ({}));
              setVoiceError(err.detail || t('voiceUnsupported'));
              return;
            }
            const data = await resp.json();
            const text = (data.text || '').trim();
            if (text) setValue((prev) => (prev ? `${prev} ${text}` : text));
          } catch (err) {
            setVoiceError(err?.message || t('voiceUnsupported'));
          } finally {
            setVoiceTranscribing(false);
          }
        };
        recorder.onerror = () => {
          setVoiceError(t('voiceUnsupported'));
          setIsListening(false);
          stream.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
        };
        mediaRecorderRef.current = recorder;
        recorder.start();
        setIsListening(true);
      })
      .catch(() => {
        setVoiceError(
          typeof window !== 'undefined' && !window.isSecureContext
            ? t('voiceInsecureContext')
            : t('voicePermissionDenied')
        );
      });
  }, [isListening, isStreaming, voiceTranscribing, t]);

  // 组件卸载时释放语音识别 / 录音资源
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch (_) {}
        recognitionRef.current = null;
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          mediaRecorderRef.current.stop();
        } catch (_) {}
        mediaRecorderRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    };
  }, []);

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

  const inputBoxClass =
    'input-box' + (isListening || voiceTranscribing ? ' input-box--recording' : '');

  const displayValue = value + (interimTranscript ? interimTranscript : '');

  return (
    <div className={wrapperClass}>
      <div className="input-area__inner">
        <div className={inputBoxClass}>
          <textarea
            ref={textareaRef}
            className="input-box__textarea"
            placeholder={isListening ? '' : t('placeholder')}
            rows={1}
            aria-label={t('inputMessage')}
            value={displayValue}
            onChange={(e) => {
              const v = e.target.value;
              if (isListening) {
                setValue(v);
                setInterimTranscript('');
              } else {
                setValue(v);
              }
            }}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
          />

          {attachedFiles && attachedFiles.length > 0 && (
            <div className="input-box__file-list" aria-label="已附加文件">
              {attachedFiles.map((file, index) => {
                const name = file.filename || file.name || '未命名文件';
                const ext = name.includes('.') ? name.split('.').pop().toLowerCase() : '';
                let typeLabel = '文件';
                let typeClass = 'other';
                let iconSrc = genericFileIcon;
                if (ext === 'pdf') {
                  typeLabel = 'PDF';
                  typeClass = 'pdf';
                  iconSrc = pdfIcon;
                } else if (ext === 'doc' || ext === 'docx') {
                  typeLabel = 'Word';
                  typeClass = 'word';
                  iconSrc = wordIcon;
                } else if (ext === 'xls' || ext === 'xlsx' || ext === 'csv') {
                  typeLabel = '表格';
                  typeClass = 'sheet';
                  iconSrc = sheetIcon;
                } else if (ext === 'txt') {
                  typeLabel = '文本';
                  typeClass = 'text';
                  iconSrc = textIcon;
                }
                const shortName =
                  name.length > 24 ? `${name.slice(0, 10)}...${name.slice(-8)}` : name;

                return (
                  <div
                    key={`${name}-${index}`}
                    className="input-box__file-preview"
                    data-test-id="file-preview"
                  >
                    <img
                      className={`input-box__file-icon-img input-box__file-icon-img--${typeClass}`}
                      src={iconSrc}
                      alt={`${typeLabel} icon`}
                    />
                    <div className="input-box__file-meta">
                      <div
                        className="input-box__file-name"
                        title={name}
                        data-test-id="file-name"
                      >
                        {shortName}
                      </div>
                      <div className="input-box__file-type">{typeLabel}</div>
                    </div>
                    {onRemoveAttachedFile && (
                      <button
                        type="button"
                        className="input-box__file-remove"
                        aria-label={`移除文件“${name}”`}
                        onClick={() => onRemoveAttachedFile(index)}
                      >
                        <span className="material-symbols-outlined">close</span>
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div className="input-box__row">
            <div className="input-box__tools">
              {(isListening || voiceTranscribing) && (
                <span className="input-box__recording-hint" role="status" aria-live="polite">
                  <span className="input-box__recording-dot" aria-hidden />
                  {voiceTranscribing ? t('voiceTranscribing') : t('voiceListening')}
                </span>
              )}
              {showAttach && (
                <>
                  <button
                    type="button"
                    className="input-box__tool-btn"
                    title="附加文件"
                    aria-label="附加文件"
                    onClick={handleAttachClick}
                  >
                    <span className="material-symbols-outlined">attach_file</span>
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    style={{ display: 'none' }}
                    onChange={handleFileChange}
                  />
                </>
              )}
              <button
                type="button"
                className={`input-box__tool-btn${isListening || voiceTranscribing ? ' input-box__tool-btn--recording' : ''}`}
                title={voiceTranscribing ? t('voiceTranscribing') : isListening ? t('voiceStop') : t('voiceInput')}
                aria-label={voiceTranscribing ? t('voiceTranscribing') : isListening ? t('voiceStop') : t('voiceInput')}
                aria-pressed={isListening || voiceTranscribing}
                onClick={toggleVoiceInput}
                disabled={isStreaming || voiceTranscribing}
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
        {(attachError || voiceError) && (
          <p className="input-area__error" role="status">
            {attachError && (
              <>
                {attachError.type === 'unsupported' &&
                  `${t('quickParseUnsupportedFilePrefix')}${attachError.filename}${t('quickParseSupportedTypesSuffix')}`}
                {attachError.type === 'tooLarge' &&
                  `${t('quickParseFileTooLargePrefix')}${attachError.filename}${t('quickParseFileTooLargeSuffix')}`}
                {attachError.type === 'duplicated' &&
                  `${t('quickParseFileDuplicatedPrefix')}${attachError.filename}${t('quickParseFileDuplicatedSuffix')}`}
              </>
            )}
            {voiceError && !attachError && voiceError}
          </p>
        )}
        <p className="input-area__disclaimer">{t('disclaimer')}</p>
      </div>
    </div>
  );
}
