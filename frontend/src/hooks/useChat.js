import { useCallback, useEffect, useRef, useState } from 'react';

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

        // Agentic 模式：处理 Thought / Action / Observation / Final Answer 事件
        if (agenticEnabled && data.event) {
          if (data.event === 'error') {
            setMessages((prev) => [
              ...prev,
              { role: 'assistant', content: '错误：' + (data.message || '') },
            ]);
            setIsStreaming(false);
            setError(data.message || 'Agentic 会话错误');
            setAgenticStatus(null);
            return;
          }
          if (data.event === 'thought') {
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
          if (data.event === 'observation') {
            setAgenticStatus('observation');
            setAgenticEvents((prev) => {
              const next = [
                ...prev,
                {
                  type: 'observation',
                  step: data.step ?? 0,
                  content: data.content || '',
                },
              ];
              agenticEventsRef.current = next;
              return next;
            });
            return;
          }
          if (data.event === 'final_answer') {
            // 去掉前缀 "Final Answer:"，只保留真正的回答内容
            const raw = data.content || '';
            const content = raw.replace(/^Final Answer\s*:?\s*/i, '');
            const convId = data.conversation_id;

            // 前端模拟流式打字效果：逐字更新 streamingContent，结束后写入 messages
            if (!content) {
              setIsStreaming(false);
              // 思路面板保留在本轮 user / assistant 之间，只把状态更新为 done
              setAgenticStatus('done');
              if (convId && onRoundCompleteRef.current) {
                onRoundCompleteRef.current(convId);
              }
              return;
            }

            setAgenticStatus('done');
            streamingBufferRef.current = '';
            setStreamingContent('');

            const total = content.length;
            const stepSize = 3; // 每次追加的字符数
            const interval = 20; // 毫秒
            let index = 0;

            const tick = () => {
              if (!isStreamingRef.current) {
                // 已被用户中断
                return;
              }
              index += stepSize;
              if (index >= total) {
                // 结束：把完整答案写入 messages，并清空 streamingContent
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
                // 先保留实时事件，避免“最终答案落地瞬间”面板闪消；
                // Chat 侧会在检测到历史 trace 可用时自动切换为历史面板。
                setAgenticStatus('done');
                if (convId && onRoundCompleteRef.current) {
                  onRoundCompleteRef.current(convId);
                }
                return;
              }
              const slice = content.slice(0, index);
              streamingBufferRef.current = slice;
              setStreamingContent(slice);
              typingTimerRef.current = setTimeout(tick, interval);
            };

            // 确保处于“流式中”状态，然后启动动画
            setIsStreaming(true);
            isStreamingRef.current = true;
            typingTimerRef.current = setTimeout(tick, interval);
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

      // 1) 先在前端对话区追加“文件预览消息”（仅用于展示，不发给后端）
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
