"""
DeepResearch - 数据分析 Agent (DataAnalyst)

委托 agentic.tools.data_analyzer 做抽取与分析，结果写回 state（data_points、insights）。
"""
import uuid
from typing import Any, Dict, List

from .base import BaseAgent
from ..state import ResearchState, ResearchPhase

from ...tools.data_analyzer import run_analysis, _normalize_data


class DataAnalyst(BaseAgent):
    """数据分析 - 使用 data_analyzer 工具从事实中抽取数据点并生成洞察。"""

    def __init__(self, model_id: str = "default"):
        super().__init__(name="DataAnalyst", role="数据分析", model_id=model_id)

    async def process(self, state: ResearchState) -> ResearchState:
        if state.get("phase") != ResearchPhase.ANALYZING.value:
            return state

        facts = state.get("facts", [])[:30]
        if not facts:
            self.add_message(state, "phase_detail", {"content": "暂无事实数据，跳过数据分析"})
            return state

        self.add_message(state, "thought", {"agent": self.name, "content": "使用数据分析工具从事实中抽取数据点并生成洞察..."})

        # 用工具做文本归一化与抽取（替代原来自写的正则）
        texts = [(f.get("content") or "")[:2000] for f in facts]
        normalized = _normalize_data(texts)
        data_points = list(state.get("data_points", []))
        seen = set()

        for i, row in enumerate(normalized):
            source = facts[i].get("source_name", "N/A") if i < len(facts) else "N/A"
            name = (row.get("text") or str(row))[:80]
            value = row.get("value") or row.get("percentage")
            if value is None:
                continue
            key = (name, value)
            if key in seen:
                continue
            seen.add(key)
            unit = "百分比" if "percentage" in row else ("年份" if "year" in row else "")
            year = row.get("year")
            data_points.append({
                "id": f"dp_{uuid.uuid4().hex[:8]}",
                "name": name,
                "value": value,
                "unit": unit,
                "year": year,
                "source": source,
            })

        state["data_points"] = data_points

        # 用工具做完整分析，得到洞察与统计
        analysis = run_analysis(texts, analysis_type="auto")
        if analysis.get("success") and analysis.get("insights"):
            state["insights"] = list(state.get("insights", [])) + analysis["insights"]
            self.add_message(state, "phase_detail", {"content": f"已抽取 {len(data_points)} 个数据点，生成 {len(analysis['insights'])} 条洞察"})
        else:
            self.add_message(state, "phase_detail", {"content": f"已抽取 {len(data_points)} 个数据点"})

        return state
