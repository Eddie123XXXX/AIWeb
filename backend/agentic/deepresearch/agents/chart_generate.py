"""
DeepResearch - 图表 Agent (ChartGenerate)

委托 agentic.tools.chart_generator 的 build_chart 生成 ECharts 配置，写入 state["charts"]。
"""
import uuid
from typing import Any, Dict, List

from .base import BaseAgent
from ..state import ResearchState, ResearchPhase

from ...tools.chart_generator import build_chart


def _data_points_to_chart_data(data_points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将 state 的 data_points 转为 chart_generator 可用的 [{name, value}]。"""
    out = []
    for d in data_points:
        name = (d.get("name") or str(d.get("value", "")))[:80]
        value = d.get("value")
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        out.append({"name": name, "value": value})
    return out


class ChartGenerate(BaseAgent):
    """ChartGenerate - 使用 chart_generator 工具生成图表配置。"""

    def __init__(self, model_id: str = "default"):
        super().__init__(name="ChartGenerate", role="chart_generate", model_id=model_id)

    async def process(self, state: ResearchState) -> ResearchState:
        if state.get("phase") != ResearchPhase.ANALYZING.value:
            return state

        self.add_message(state, "thought", {"agent": self.name, "content": "使用图表工具生成 ECharts 配置..."})
        charts = list(state.get("charts", []))
        outline = state.get("outline", [])
        data_points = state.get("data_points", [])

        need_chart_sections = [s for s in outline if s.get("requires_chart")][:2]
        if not need_chart_sections and outline:
            need_chart_sections = outline[:2]

        chart_data = _data_points_to_chart_data(data_points)
        if not chart_data and data_points:
            chart_data = _data_points_to_chart_data(data_points[:15])

        for section in need_chart_sections:
            section_id = section.get("id", "")
            title = section.get("title", "数据概览")
            if not chart_data:
                charts.append({
                    "id": f"chart_{uuid.uuid4().hex[:8]}",
                    "section_id": section_id,
                    "title": title,
                    "chart_type": "bar",
                    "description": "暂无数据点，未生成图表配置",
                })
                self.add_message(state, "chart", {"agent": self.name, "title": title, "chart_type": "bar"})
                continue

            try:
                config = build_chart(chart_data, "bar", title)
            except Exception as e:
                self._logger.warning("build_chart failed: %s", e)
                charts.append({
                    "id": f"chart_{uuid.uuid4().hex[:8]}",
                    "section_id": section_id,
                    "title": title,
                    "chart_type": "bar",
                    "description": str(e),
                })
                self.add_message(state, "chart", {"agent": self.name, "title": title, "chart_type": "bar"})
                continue

            chart_entry = {
                "id": f"chart_{uuid.uuid4().hex[:8]}",
                "section_id": section_id,
                "title": config.get("title", title),
                "chart_type": config.get("type", "bar"),
                "echarts_option": config.get("echarts_option"),
                "data_points": chart_data[:10],
            }
            charts.append(chart_entry)
            self.add_message(state, "chart", {
                "agent": self.name,
                "title": chart_entry["title"],
                "chart_type": chart_entry["chart_type"],
                "echarts_option": config.get("echarts_option"),
            })

        state["charts"] = charts
        self.add_message(state, "phase_detail", {"content": f"已生成 {len(charts)} 个图表配置"})
        return state
