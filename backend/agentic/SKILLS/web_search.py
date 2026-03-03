import asyncio


async def execute(query: str, **_: object) -> str:
  """
  示例 Skill 执行逻辑。
  这里仅做占位示例：实际项目中可以在此处调用已有的 WebSearchService
  或复用 agentic.tools.web_search.WebSearchTool 的实现。
  """
  # 为避免与现有 web_search 工具行为冲突，这里仅返回提示性文案。
  await asyncio.sleep(0)
  return f"Skill web_search 收到 query={query!r}。请在 SKILLS/web_search.py 中接入真实的网络搜索实现。"

