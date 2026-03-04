from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ..tools_base import ToolContext, ToolExecutionError
from .common import ensure_permissions, validate_params

logger = logging.getLogger("agentic.tools.chart_generator")


# ---------------------------------------------------------------------------
# 参数 Schema（暴露给 LLM）
# ---------------------------------------------------------------------------

class ChartGeneratorParams(BaseModel):
    data: Union[Dict[str, Any], List[Any]] = Field(
        description=(
            "图表数据，支持多种格式："
            "折线/柱状图: {xAxis:[...], series:[{name,data}]} 或 [{name,value},...] ；"
            "饼图: [{name,value},...] 或 {category:value,...} ；"
            "散点图: [[x,y],...] 或 [{x,y},...] ；"
            "表格: [{col1:val1,...},...]"
        ),
    )
    chart_type: str = Field(
        default="bar",
        description="图表类型: line / bar / pie / scatter / table",
    )
    title: str = Field(
        default="数据图表",
        description="图表标题",
    )
    subtitle: str = Field(default="", description="副标题")
    smooth: bool = Field(default=True, description="折线图是否平滑曲线")
    area: bool = Field(default=False, description="折线图是否显示面积")
    horizontal: bool = Field(default=False, description="柱状图是否水平")
    stacked: bool = Field(default=False, description="柱状图是否堆叠")
    rose: bool = Field(default=False, description="饼图是否为南丁格尔玫瑰图")
    x_name: str = Field(default="X", description="散点图 X 轴名称")
    y_name: str = Field(default="Y", description="散点图 Y 轴名称")


# ---------------------------------------------------------------------------
# ECharts 配置生成引擎
# ---------------------------------------------------------------------------

DEFAULT_COLORS = [
    "#5470c6", "#91cc75", "#fac858", "#ee6666",
    "#73c0de", "#3ba272", "#fc8452", "#9a60b4",
    "#ea7ccc", "#48b8d0",
]


def _parse_series_data(data: Union[Dict, List]) -> tuple[list, list]:
    x_data: list = []
    series_data: list = []

    if isinstance(data, dict):
        x_data = data.get("xAxis", [])
        series_data = data.get("series", [])
        if not series_data:
            x_data = list(data.keys())
            series_data = [{"name": "数值", "data": list(data.values())}]
    elif isinstance(data, list):
        if data and isinstance(data[0], dict):
            x_data = [item.get("name", f"项目{i}") for i, item in enumerate(data)]
            series_data = [{"name": "数值", "data": [item.get("value", 0) for item in data]}]
        else:
            x_data = [f"项目{i + 1}" for i in range(len(data))]
            series_data = [{"name": "数值", "data": data}]

    return x_data, series_data


def _parse_pie_data(data: Union[Dict, List]) -> list[dict]:
    if isinstance(data, dict):
        if "series" in data and data["series"]:
            return data["series"][0].get("data", [])
        return [
            {"name": k, "value": v}
            for k, v in data.items()
            if k not in {"xAxis", "series", "type", "title"}
        ]
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            return data
        return [{"name": f"项目{i + 1}", "value": v} for i, v in enumerate(data)]
    return []


def _parse_scatter_data(data: Union[Dict, List]) -> list[list]:
    result: list[list] = []
    if not isinstance(data, list):
        return result
    for item in data:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            result.append([item[0], item[1]])
        elif isinstance(item, dict):
            x = item.get("x", item.get("value", 0))
            y = item.get("y", item.get("count", 0))
            result.append([x, y])
    return result


def _base_title(title: str, subtitle: str = "") -> dict:
    cfg: dict = {"text": title, "left": "center"}
    if subtitle:
        cfg["subtext"] = subtitle
    return cfg


def generate_line(data: Any, title: str, subtitle: str = "",
                  smooth: bool = True, area: bool = False) -> dict:
    x_data, series_data = _parse_series_data(data)
    series = []
    for i, s in enumerate(series_data):
        cfg: dict = {
            "name": s.get("name", f"系列{i + 1}"),
            "type": "line",
            "data": s.get("data", []),
            "smooth": smooth,
            "emphasis": {"focus": "series"},
        }
        if area:
            cfg["areaStyle"] = {"opacity": 0.3}
        series.append(cfg)

    return {
        "type": "line",
        "title": title,
        "echarts_option": {
            "title": _base_title(title, subtitle),
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
            "legend": {"data": [s["name"] for s in series], "bottom": 0},
            "grid": {"left": "3%", "right": "4%", "bottom": "10%", "containLabel": True},
            "xAxis": {"type": "category", "boundaryGap": False, "data": x_data},
            "yAxis": {"type": "value"},
            "series": series,
            "color": DEFAULT_COLORS,
        },
    }


def generate_bar(data: Any, title: str, subtitle: str = "",
                 horizontal: bool = False, stacked: bool = False) -> dict:
    x_data, series_data = _parse_series_data(data)
    series = []
    for i, s in enumerate(series_data):
        cfg: dict = {
            "name": s.get("name", f"系列{i + 1}"),
            "type": "bar",
            "data": s.get("data", []),
            "emphasis": {"focus": "series"},
            "itemStyle": {
                "borderRadius": [0, 4, 4, 0] if horizontal else [4, 4, 0, 0],
            },
        }
        if stacked:
            cfg["stack"] = "total"
        series.append(cfg)

    cat_axis = {"type": "category", "data": x_data}
    val_axis = {"type": "value"}

    return {
        "type": "bar",
        "title": title,
        "echarts_option": {
            "title": _base_title(title, subtitle),
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {"data": [s["name"] for s in series], "bottom": 0},
            "grid": {"left": "3%", "right": "4%", "bottom": "10%", "containLabel": True},
            "xAxis": val_axis if horizontal else cat_axis,
            "yAxis": cat_axis if horizontal else val_axis,
            "series": series,
            "color": DEFAULT_COLORS,
        },
    }


def generate_pie(data: Any, title: str, subtitle: str = "",
                 rose: bool = False) -> dict:
    pie_data = _parse_pie_data(data)
    series_cfg: dict = {
        "name": title,
        "type": "pie",
        "radius": "60%",
        "data": pie_data,
        "emphasis": {
            "itemStyle": {
                "shadowBlur": 10,
                "shadowOffsetX": 0,
                "shadowColor": "rgba(0, 0, 0, 0.5)",
            }
        },
        "label": {"formatter": "{b}: {d}%"},
    }
    if rose:
        series_cfg["roseType"] = "area"
        series_cfg["radius"] = ["20%", "70%"]

    return {
        "type": "pie",
        "title": title,
        "echarts_option": {
            "title": _base_title(title, subtitle),
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "legend": {"orient": "vertical", "left": "left", "top": "middle"},
            "series": [series_cfg],
            "color": DEFAULT_COLORS,
        },
    }


def generate_scatter(data: Any, title: str, subtitle: str = "",
                     x_name: str = "X", y_name: str = "Y") -> dict:
    scatter_data = _parse_scatter_data(data)
    return {
        "type": "scatter",
        "title": title,
        "echarts_option": {
            "title": _base_title(title, subtitle),
            "tooltip": {
                "trigger": "item",
                "formatter": f"{x_name}: {{c[0]}}<br/>{y_name}: {{c[1]}}",
            },
            "xAxis": {"type": "value", "name": x_name},
            "yAxis": {"type": "value", "name": y_name},
            "series": [{"type": "scatter", "data": scatter_data, "symbolSize": 10}],
            "color": DEFAULT_COLORS,
        },
    }


def generate_table(data: Any, title: str) -> dict:
    if isinstance(data, dict):
        rows = data.get("data", [data])
    elif isinstance(data, list):
        rows = data
    else:
        rows = []

    columns: list[str] = []
    if rows and isinstance(rows[0], dict):
        columns = list(rows[0].keys())

    return {
        "type": "table",
        "title": title,
        "columns": [{"key": col, "label": col} for col in columns],
        "data": rows,
        "pagination": len(rows) > 10,
        "pageSize": 10,
    }


_GENERATORS: Dict[str, Any] = {
    "line": generate_line,
    "bar": generate_bar,
    "pie": generate_pie,
    "scatter": generate_scatter,
    "table": generate_table,
}


def build_chart(
    data: Any,
    chart_type: str,
    title: str,
    **kwargs: Any,
) -> dict:
    """根据 chart_type 分派到对应的生成函数。"""
    ct = chart_type.lower()
    fn = _GENERATORS.get(ct)
    if fn is None:
        logger.warning("未知图表类型 %s，回退为 bar", ct)
        fn = generate_bar

    if ct == "table":
        return fn(data, title)
    return fn(data, title, **kwargs)


# ---------------------------------------------------------------------------
# Agentic Tool 适配层
# ---------------------------------------------------------------------------

class ChartGeneratorTool:
    """
    ECharts 图表配置生成工具。

    根据数据和指定的图表类型生成完整的 ECharts 配置 JSON，
    前端可直接用返回的 echarts_option 渲染图表。
    """

    name = "chart_generator"
    description = (
        "ECharts 图表生成工具：传入数据和图表类型（line/bar/pie/scatter/table），"
        "生成完整的 ECharts 配置 JSON。支持折线图、柱状图、饼图、散点图和数据表格。"
        "重要：你必须将本工具返回的 JSON 原样放入 ```chart\\n...\\n``` 代码块中输出给用户，"
        "前端会自动将其渲染为交互式图表。不要修改返回的 JSON。"
    )
    required_permissions: set[str] = set()
    param_model = ChartGeneratorParams

    async def run(self, params: Dict[str, Any], ctx: ToolContext) -> str:
        parsed = validate_params(ChartGeneratorParams, params)
        ensure_permissions(ctx, self.required_permissions)

        data = parsed.data
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:
                raise ToolExecutionError(f"data 字段不是合法 JSON: {exc}") from exc

        if not data:
            raise ToolExecutionError("data 不能为空")

        kwargs: dict[str, Any] = {}
        ct = parsed.chart_type.lower()
        if parsed.subtitle:
            kwargs["subtitle"] = parsed.subtitle

        if ct == "line":
            kwargs.update(smooth=parsed.smooth, area=parsed.area)
        elif ct == "bar":
            kwargs.update(horizontal=parsed.horizontal, stacked=parsed.stacked)
        elif ct == "pie":
            kwargs["rose"] = parsed.rose
        elif ct == "scatter":
            kwargs.update(x_name=parsed.x_name, y_name=parsed.y_name)

        try:
            config = build_chart(data, ct, parsed.title, **kwargs)
        except Exception as exc:
            raise ToolExecutionError(f"图表生成失败: {exc}") from exc

        chart_json = json.dumps(config, ensure_ascii=False)
        return (
            "图表配置已生成。请在你的回答中使用 ```chart 代码块原样输出以下 JSON，"
            "前端会自动渲染为交互式图表：\n\n"
            f"```chart\n{chart_json}\n```"
        )
