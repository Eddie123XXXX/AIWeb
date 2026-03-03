from __future__ import annotations

from typing import Any, Dict, Protocol


class ToolExecutionError(Exception):
    """工具执行时抛出的业务异常，用于生成 Error Observation。"""


class ToolContext(Protocol):
    """
    运行工具时可注入的上下文（数据库连接、缓存、配置等）。

    根据你的项目情况扩展，例如：
    - db: AsyncSession
    - redis: aioredis.Redis
    - user_id: 当前用户 ID（int）
    - roles: 当前用户角色列表（如 ["admin", "user"]）
    - permissions: 当前用户拥有的权限标识集合（如 {"memory:read", "rag:search"}）
    """

    # 最小约束：所有工具都可以依赖 user_id 进行权限控制与个性化检索
    user_id: int | None
    roles: list[str] | None
    permissions: set[str] | None


class Tool(Protocol):
    """
    所有工具的标准接口。

    你可以针对 skills / MCP / 内置业务工具实现不同的子类。
    """

    name: str
    description: str

    async def run(self, params: Dict[str, Any], ctx: ToolContext) -> str:
        """
        执行工具逻辑，返回字符串 Observation 文本。

        - 成功时返回人类可读的结果描述，供大模型继续思考使用；
        - 若需结构化结果，可在文本中嵌入 JSON，Prompt 中提前约定。
        - 失败时抛出 ToolExecutionError，由 Agent Loop 转为 Error Observation。
        """
        raise NotImplementedError

