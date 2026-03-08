"""
DeepResearch - Agent 基类

使用 Agentic 主程序 LLM（get_model_config_by_id + LLMService），支持 _message_queue 实时 SSE。
"""
import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from models import Message, Role
from routers.models import get_model_config_by_id
from services.llm_service import LLMService

from ..state import ResearchState

logger = logging.getLogger("agentic.deepresearch.agents")


class BaseAgent(ABC):
    """所有专家 Agent 的基类，使用主程序模型配置与 LLM 服务。"""

    def __init__(self, name: str, role: str, model_id: str = "deepseek-v3.2"):
        self.name = name
        self.role = role
        self.model_id = model_id
        self._logger = logging.getLogger(f"agentic.deepresearch.{name}")

    @abstractmethod
    async def process(self, state: ResearchState) -> ResearchState:
        """处理状态并返回更新后的状态。"""
        pass

    async def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = True,
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> str:
        """使用主程序 LLM 调用。"""
        try:
            model_config = get_model_config_by_id(self.model_id)
            service = LLMService(model_config)
            if json_mode:
                system_prompt = (system_prompt or "").strip() + "\n\n请严格按照要求的 JSON 格式输出，不要添加 markdown 代码块标记。"
            messages = [
                Message(role=Role.SYSTEM, content=system_prompt),
                Message(role=Role.USER, content=user_prompt),
            ]
            return await service.chat(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as e:
            self._logger.error("LLM call failed: %s", e)
            raise

    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """安全解析 JSON，处理 markdown 代码块等。"""
        if not response or not response.strip():
            return {}
        s = response.strip()
        if s.startswith("\ufeff"):
            s = s[1:]
        # 直接解析
        try:
            return self._fix_escaped_values(json.loads(s))
        except json.JSONDecodeError:
            pass
        # 提取 ```json ... ```
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
        if m:
            try:
                return self._fix_escaped_values(json.loads(m.group(1).strip()))
            except json.JSONDecodeError:
                pass
        # 找最外层 {}
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return self._fix_escaped_values(json.loads(s[start : end + 1]))
            except json.JSONDecodeError:
                pass
        self._logger.warning("JSON parse failed, raw prefix: %s", response[:500])
        return {}

    def _fix_escaped_values(self, obj: Any, key: Optional[str] = None) -> Any:
        """递归修复字符串中的过度转义（保留 code 等字段）。"""
        if isinstance(obj, dict):
            return {k: self._fix_escaped_values(v, key=k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._fix_escaped_values(x, key=key) for x in obj]
        if isinstance(obj, str) and key not in ("code", "fixed_code", "revised_content"):
            return (
                obj.replace("\\\\n", "\n")
                .replace("\\n", "\n")
                .replace("\\\\r", "\r")
                .replace("\\r", "\r")
            )
        return obj

    def add_message(self, state: ResearchState, event_type: str, content: Any) -> None:
        """追加消息并推送到 SSE 队列。"""
        message = {
            "type": event_type,
            "agent": self.name,
            "timestamp": datetime.now().isoformat(),
            "content": content,
        }
        state.setdefault("messages", []).append(message)
        queue = state.get("_message_queue")
        if queue is not None:
            try:
                queue.put_nowait(message)
            except Exception as e:
                self._logger.warning("Queue put failed: %s", e)

    def add_log(
        self,
        state: ResearchState,
        action: str,
        input_summary: str,
        output_summary: str,
        duration_ms: int,
        tokens_used: int = 0,
    ) -> None:
        """添加执行日志。"""
        state.setdefault("logs", []).append({
            "timestamp": datetime.now().isoformat(),
            "agent": self.name,
            "action": action,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "duration_ms": duration_ms,
            "tokens_used": tokens_used,
        })
