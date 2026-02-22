import { useCallback, useRef, useState } from 'react';

const DEFAULT_MODEL_ID = 'default';

function getWsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host || 'localhost:8000';
  let url = `${protocol}//${host}/api/chat/ws`;
  try {
    const token = window.localStorage.getItem('auth_token');
    if (token) url += `?token=${encodeURIComponent(token)}`;
  } catch (_) {}
  return url;
}

/**
 * @param {string | null} conversationId - 当前会话 ID，有则后端走 Redis/DB 读路径与写路径
 * @param {{ onRoundComplete?: (conversationId: string) => void }} options - 本轮对话结束（done）时回调，用于刷新侧栏标题等
 */
export function useChat(conversationId = null, options = {}) {
  const { onRoundComplete } = options;
  const [messages, setMessages] = useState([]);
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);
  const wsReadyRef = useRef(null);
  const streamingBufferRef = useRef('');
  const onRoundCompleteRef = useRef(onRoundComplete);
  onRoundCompleteRef.current = onRoundComplete;

  const ensureWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }
    if (wsReadyRef.current) return wsReadyRef.current;

    const url = getWsUrl();
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
            setMessages((prev) => [...prev, { role: 'assistant', content }]);
          }
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
  }, []);

  const sendMessage = useCallback(
    async (text, modelId = DEFAULT_MODEL_ID) => {
      const trimmed = text?.trim();
      if (!trimmed || isStreaming) return;

      const userMessage = { role: 'user', content: trimmed };
      setMessages((prev) => [...prev, userMessage]);
      setStreamingContent('');
      setError(null);
      setIsStreaming(true);

      try {
        await ensureWebSocket();
        const ws = wsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          throw new Error('WebSocket 未连接');
        }
        const nextMessages = [...messages, userMessage];
        const payload = {
          model_id: modelId || DEFAULT_MODEL_ID,
          messages: nextMessages,
          stream: true,
          temperature: 0.7,
          max_tokens: 1024,
        };
        if (conversationId) payload.conversation_id = conversationId;
        ws.send(JSON.stringify(payload));
      } catch (err) {
        console.error(err);
        setMessages((prev) => [...prev, { role: 'assistant', content: '错误：' + err.message }]);
        setIsStreaming(false);
      }
    },
    [messages, isStreaming, ensureWebSocket, conversationId]
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
  };
}
