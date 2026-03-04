import { useCallback, useEffect, useRef, useState } from 'react';
import { stripFinalAnswerMarkers } from '../utils/markdown';

const DEFAULT_MODEL_ID = 'default';

function getWsUrl(agenticEnabled) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host || 'localhost:8000';
  const path = agenticEnabled ? '/api/agentic/ws' : '/api/chat/ws';
  let url = `${protocol}//${host}${path}`;
  try {
    const token = window.localStorage.getItem('auth_token');
    if (token) url += `?token=${encodeURIComponent(token)}`;
  } catch (_) {}
  return url;
}

/**
 * @param {string | null} conversationId - 当前会话 ID，有则后端走 Redis/DB 读路径与写路径
 * @param {{ onRoundComplete?: (conversationId: string) => void, agenticEnabled?: boolean, enabledAgenticTools?: string[] }} options - 本轮对话结束回调 + 是否启用 Agentic 模式 + 启用的工具
 */
export function useChat(conversationId = null, options = {}) {
  const { onRoundComplete, agenticEnabled = false, enabledAgenticTools = [] } = options;
  const [messages, setMessages] = useState([]);
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  // Agentic 模式下的内部推理事件（Thought / Action / Observation）
  const [agenticEvents, setAgenticEvents] = useState([]);
  const [agenticStatus, setAgenticStatus] = useState(null); // 'thinking' | 'action' | 'observation' | 'done' | null
  const wsRef = useRef(null);
  const wsReadyRef = useRef(null);
  const streamingBufferRef = useRef('');
  const onRoundCompleteRef = useRef(onRoundComplete);
  const lastQuickParseUsedRef = useRef(false);
  const isStreamingRef = useRef(false);
  const typingTimerRef = useRef(null);
  const agenticEventsRef = useRef([]);
  onRoundCompleteRef.current = onRoundComplete;
  agenticEventsRef.current = agenticEvents;

  useEffect(() => {
    isStreamingRef.current = isStreaming;
    return () => {
      if (!isStreaming) {
        if (typingTimerRef.current) {
          clearTimeout(typingTimerRef.current);
          typingTimerRef.current = null;
        }
      }
    };
  }, [isStreaming]);

  const ensureWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }
    if (wsReadyRef.current) return wsReadyRef.current;

    const url = getWsUrl(agenticEnabled);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    wsReadyRef.current = new Promise((resolve, reject) => {
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error('WebSocket 连接失败'));
    });

    ws.onclose = () => {
      wsReadyRef.current = null;
      wsRef.current = null;
      setIsStreaming(false);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Agentic 模式：处理 stream_delta / Thought / Action / Observation / Final Answer 事件
        if (agenticEnabled && data.event) {
          if (data.event === 'error') {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: '错误：' + (data.message || '') },
            ]);
            streamingBufferRef.current = '';
            setStreamingContent('');
            setIsStreaming(false);
            setError(data.message || 'Agentic 会话错误');
            setAgenticStatus(null);
            return;
          }

          // ---- token 级流式：逐 token 累积到 streamingContent，实时渲染 ----
          if (data.event === 'stream_delta') {
            const token = data.content || '';
            if (token) {
              streamingBufferRef.current += token;
              const display = stripFinalAnswerMarkers(streamingBufferRef.current);
              setStreamingContent(display);
            }
            return;
          }

          if (data.event === 'thought') {
            // 思考流结束——清空流式缓冲区（内容已逐 token 展示过），写入推理面板
            streamingBufferRef.current = '';
            setStreamingContent('');
            setAgenticStatus('thinking');
            setAgenticEvents((prev) => {
              const next = [
                ...prev,
                {
                  type: 'thought',
                  step: data.step ?? 0,
                  content: data.content || '',
                },
              ];
              agenticEventsRef.current = next;
              return next;
            });
            return;
          }
          if (data.event === 'action') {
            setAgenticStatus('action');
            setAgenticEvents((prev) => {
              const next = [
                ...prev,
                {
                  type: 'action',
                  step: data.step ?? 0,
                  tool: data.tool || '',
                  content: data.content || '',
                },
              ];
              agenticEventsRef.current = next;
              return next;
            });
            return;
          }
          if (data.event === 'observation_delta') {
            const step = data.step ?? 0;
            const chunk = data.content || '';
            if (!chunk) return;
            setAgenticStatus('observation');
            setAgenticEvents((prev) => {
              const last = prev[prev.length - 1];
              const isAppending =
                last?.type === 'observation' && last?.step === step;
              const next = isAppending
                ? [...prev.slice(0, -1), { ...last, content: last.content + chunk }]
                : [...prev, { type: 'observation', step, content: chunk }];
              agenticEventsRef.current = next;
              return next;
            });
            return;
          }
          if (data.event === 'observation') {
            setAgenticStatus('observation');
            const step = data.step ?? 0;
            const content = data.content || '';
            setAgenticEvents((prev) => {
              const last = prev[prev.length - 1];
              const isUpdating =
                last?.type === 'observation' && last?.step === step;
              const next = isUpdating
                ? [...prev.slice(0, -1), { ...last, content }]
                : [...prev, { type: 'observation', step, content }];
              agenticEventsRef.current = next;
              return next;
            });
            return;
          }
          if (data.event === 'final_answer') {
            const raw = data.content || '';
            const content = stripFinalAnswerMarkers(raw);
            const convId = data.conversation_id;

            if (!content) {
              streamingBufferRef.current = '';
              setStreamingContent('');
              setIsStreaming(false);
              setAgenticStatus('done');
              if (convId && onRoundCompleteRef.current) {
                onRoundCompleteRef.current(convId);
              }
              return;
            }

            // 流式已将内容逐 token 推送完毕，直接落入 messages，跳过打字动画
            streamingBufferRef.current = '';
            setStreamingContent('');
            setMessages((prev) => [
              ...prev,
              {
                role: 'assistant',
                content,
                metadata: {
                  agentic_trace: {
                    version: 1,
                    status: 'done',
                    events: agenticEventsRef.current || [],
                  },
                },
              },
            ]);
            setIsStreaming(false);
            setAgenticStatus('done');
            if (convId && onRoundCompleteRef.current) {
              onRoundCompleteRef.current(convId);
            }
            return;
          }
          // 未识别的 event，忽略
          return;
        }

        // 普通聊天模式：保持原有流式协议
        if (data.error) {
          streamingBufferRef.current = '';
          setStreamingContent('');
          setMessages((prev) => [...prev, { role: 'assistant', content: '错误：' + data.error }]);
          setIsStreaming(false);
          setError(data.error);
          return;
        }
        if (typeof data.content === 'string') {
          streamingBufferRef.current += data.content;
          setStreamingContent(streamingBufferRef.current);
        }
        if (data.done) {
          const content = streamingBufferRef.current;
          streamingBufferRef.current = '';
          setStreamingContent('');
          if (content) {
            setMessages((prev) => {
              const next = [...prev, { role: 'assistant', content }];
              if (lastQuickParseUsedRef.current) {
                next.push({
                  role: 'assistant',
                  content:
                    '提示：本轮使用了临时上传的文件进行 Quick Parse，这些文件内容不会写入长期记忆或后续上下文历史。如需对文档进行多轮、深度使用，建议将其上传到知识库功能中。',
                  isQuickParseNotice: true,
                });
              }
              return next;
            });
          } else if (lastQuickParseUsedRef.current) {
            setMessages((prev) => [
              ...prev,
              {
                role: 'assistant',
                content:
                  '提示：本轮使用了临时上传的文件进行 Quick Parse，这些文件内容不会写入长期记忆或后续上下文历史。如需对文档进行多轮、深度使用，建议将其上传到知识库功能中。',
                isQuickParseNotice: true,
              },
            ]);
          }
          lastQuickParseUsedRef.current = false;
          setIsStreaming(false);
          if (data.conversation_id && onRoundCompleteRef.current) {
            onRoundCompleteRef.current(data.conversation_id);
          }
        }
      } catch (e) {
        console.error(e);
        setIsStreaming(false);
      }
    };

    return wsReadyRef.current;
  }, [agenticEnabled]);

  const sendMessage = useCallback(
    async (text, modelId = DEFAULT_MODEL_ID, conversationIdOverride = null, quickParseFiles = null, ragContext = null) => {
      const trimmed = text?.trim();
      if (!trimmed || isStreaming) return;

      const filesForThisRound = Array.isArray(quickParseFiles) ? quickParseFiles : null;
      lastQuickParseUsedRef.current = !!(filesForThisRound && filesForThisRound.length > 0);

      // 1) 先在前端对话区追加"文件预览消息"（仅用于展示，不发给后端）
      setMessages((prev) => {
        const next = [...prev];
        if (filesForThisRound && filesForThisRound.length > 0) {
          next.push({
            role: 'user',
            content: '',
            files: filesForThisRound,
            isFiles: true,
          });
        }
        next.push({ role: 'user', content: trimmed });
        return next;
      });
      setStreamingContent('');
      setError(null);
      setIsStreaming(true);
      if (agenticEnabled) {
        // 新一轮 Agentic 会话时，重置内部推理状态
        setAgenticEvents([]);
        agenticEventsRef.current = [];
        setAgenticStatus('thinking');
      }

      try {
        await ensureWebSocket();
        const ws = wsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          throw new Error('WebSocket 未连接');
        }

        const cid = conversationIdOverride ?? conversationId;

        if (agenticEnabled) {
          // Agentic 模式：使用 AgenticChatRequest 协议，仅发送本轮 user_query
          const payload = {
            user_query: trimmed,
            model_id: modelId || DEFAULT_MODEL_ID,
          };
          if (Array.isArray(enabledAgenticTools)) {
            payload.enabled_tools = enabledAgenticTools;
          }
          if (cid) payload.conversation_id = cid;
          ws.send(JSON.stringify(payload));
        } else {
          // 普通聊天模式：保持原有 WebSocket ChatRequest 协议
          // 仅将文字消息发给后端，不包含前端用于展示的文件消息
          const textHistory = messages.filter((m) => !m.isFiles);
          const nextMessages = [...textHistory, { role: 'user', content: trimmed }];
          const payload = {
            model_id: modelId || DEFAULT_MODEL_ID,
            messages: nextMessages,
            stream: true,
            temperature: 0.7,
            max_tokens: 1024,
          };
          if (cid) payload.conversation_id = cid;
          if (Array.isArray(quickParseFiles) && quickParseFiles.length > 0) {
            payload.quick_parse_files = quickParseFiles.map((f) => ({
              url: f.url,
              filename: f.filename,
              mime_type: f.mime_type,
              size: f.size,
            }));
          }
          if (ragContext && typeof ragContext === 'string' && ragContext.trim()) {
            payload.rag_context = ragContext.trim();
          }
          ws.send(JSON.stringify(payload));
        }
      } catch (err) {
        console.error(err);
        setMessages((prev) => [...prev, { role: 'assistant', content: '错误：' + err.message }]);
        setIsStreaming(false);
      }
    },
    [messages, isStreaming, ensureWebSocket, conversationId, agenticEnabled, enabledAgenticTools]
  );

  const cancelStream = useCallback(() => {
    if (!isStreaming) return;
    const content = streamingBufferRef.current;
    if (content) {
      setMessages((prev) => [...prev, { role: 'assistant', content }]);
      streamingBufferRef.current = '';
      setStreamingContent('');
    }
    setIsStreaming(false);
    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
    } catch (_) {}
  }, [isStreaming]);

  return {
    messages,
    setMessages,
    streamingContent,
    isStreaming,
    error,
    sendMessage,
    cancelStream,
    agenticEvents,
    agenticStatus,
  };
}
