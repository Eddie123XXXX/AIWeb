"""
DeepResearch - 报告转正式 Markdown Agent (MarkdownReport)

将 Writer 输出的报告草稿整理为结构规范的 Markdown 文档，便于前端编辑与导出为文件。
"""
from typing import Any, Dict

from .base import BaseAgent
from ..state import ResearchState, ResearchPhase


class MarkdownReport(BaseAgent):
    """MarkdownReport - 将报告格式化为正式 Markdown 文档。"""

    PROMPT = """你是一位技术文档编辑。请将下面的研究报告草稿整理为**规范的 Markdown 文档**，便于保存为 .md 文件或在前端直接编辑。

要求：
1. 保持原意与数据不变，只做格式与结构整理。
2. 标题层级：文档标题用 #，一级节用 ##，二级节用 ###，依此类推，层级连续不跳级。
3. 列表统一用 - 或 1. 格式；需要强调的数据可用 **粗体**。
4. 若有代码、配置或公式，用 ``` 代码块或行内 `code`。
5. 来源与引用保持为 [来源名](URL) 或文末参考文献列表。
6. 不要添加多余说明，只输出整理后的完整 Markdown 正文。

研究报告草稿：
---
{draft}
---
请直接输出整理后的完整 Markdown 正文（不要用 ```markdown 包裹，不要输出 JSON）。"""

    def __init__(self, model_id: str = "default"):
        super().__init__(name="MarkdownReport", role="markdown_report", model_id=model_id)

    async def process(self, state: ResearchState) -> ResearchState:
        if state.get("phase") != ResearchPhase.REVIEWING.value:
            return state
        # 仅在 Writer 刚结束、尚未进入 Reviewer 前执行一次；通过 final_report 已有内容且未设置 _markdown_done 来判定
        if state.get("_markdown_report_done"):
            return state
        draft = (state.get("final_report") or "").strip()
        if not draft:
            return state

        self.add_message(state, "thought", {"agent": self.name, "content": "正在将报告整理为规范 Markdown 文档..."})

        prompt = self.PROMPT.format(draft=draft[:12000])
        try:
            resp = await self.call_llm(
                system_prompt="你是技术文档编辑，只输出整理后的 Markdown 正文，不要用代码块包裹。",
                user_prompt=prompt,
                json_mode=False,
                temperature=0.2,
                max_tokens=8192,
            )
        except Exception as e:
            self._logger.warning("MarkdownReport LLM failed, keeping draft: %s", e)
            state["_markdown_report_done"] = True
            return state

        if resp and resp.strip():
            out = resp.strip()
            if out.startswith("```"):
                lines = out.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                out = "\n".join(lines)
            state["final_report"] = out
        state["_markdown_report_done"] = True
        self.add_message(state, "report_draft", {"content": state["final_report"], "format": "markdown"})
        return state
