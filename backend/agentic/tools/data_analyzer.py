"""
数据分析工具 (data_analyzer)。

自动识别数据类型和特征，执行趋势/分布/对比分析，推荐可视化类型。
"""
from __future__ import annotations

import json
import logging
import re
import statistics as stat_module
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ..tools_base import ToolContext, ToolExecutionError
from .common import ensure_permissions, validate_params

logger = logging.getLogger("agentic.tools.data_analyzer")


# ---------------------------------------------------------------------------
# 参数 Schema（暴露给 LLM）
# ---------------------------------------------------------------------------

class DataAnalyzerParams(BaseModel):
    data: Union[List[Dict[str, Any]], List[str], Dict[str, Any]] = Field(
        description="待分析数据：字典列表、文本列表或单个字典均可",
    )
    analysis_type: str = Field(
        default="auto",
        description="分析类型: auto(自动识别) / trend(趋势) / distribution(分布) / comparison(对比)",
    )


# ---------------------------------------------------------------------------
# 内部数据模型
# ---------------------------------------------------------------------------

class DataType(Enum):
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    DATETIME = "datetime"
    TEXT = "text"
    BOOLEAN = "boolean"


@dataclass
class ColumnProfile:
    name: str
    data_type: DataType
    non_null_count: int
    unique_count: int
    sample_values: List[Any] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 分析引擎
# ---------------------------------------------------------------------------

_TIME_PATTERNS = [
    "year", "month", "date", "time", "quarter", "week",
    "created", "updated", "timestamp", "period", "day",
    "年份", "月份", "日期", "时间", "季度",
]

_CATEGORY_PATTERNS = [
    "name", "type", "category", "class", "group", "status",
    "industry", "region", "company", "product", "brand",
    "名称", "类型", "分类", "行业", "地区", "公司", "产品",
]

_NUMBER_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:元|万|亿|%|人民币|美元)?"
)
_YEAR_RE = re.compile(r"(20\d{2}|19\d{2})年?")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _is_numeric(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value.replace(",", ""))
            return True
        except ValueError:
            return False
    return False


def _to_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).replace(",", ""))


def _normalize_data(data: Any) -> List[Dict]:
    if isinstance(data, list):
        if not data:
            return []
        if all(isinstance(item, dict) for item in data):
            return data
        if all(isinstance(item, str) for item in data):
            return _extract_from_texts(data)
        return [{"value": item, "index": i} for i, item in enumerate(data)]
    if isinstance(data, dict):
        return [data]
    return []


def _extract_from_texts(texts: List[str]) -> List[Dict]:
    extracted = []
    for i, text in enumerate(texts):
        item: Dict[str, Any] = {"index": i, "text": text[:200]}
        years = _YEAR_RE.findall(text)
        if years:
            item["year"] = int(years[0])
        numbers = _NUMBER_RE.findall(text)
        if numbers:
            try:
                item["value"] = float(numbers[0].replace(",", ""))
            except ValueError:
                pass
        pct = _PERCENT_RE.search(text)
        if pct:
            item["percentage"] = float(pct.group(1))
        extracted.append(item)
    return extracted


def _detect_column_type(col_name: str, values: List) -> DataType:
    col_lower = col_name.lower()
    for p in _TIME_PATTERNS:
        if p in col_lower:
            return DataType.DATETIME
    for p in _CATEGORY_PATTERNS:
        if p in col_lower:
            return DataType.CATEGORICAL
    if not values:
        return DataType.TEXT
    numeric_count = sum(1 for v in values if _is_numeric(v))
    if numeric_count / len(values) > 0.8:
        return DataType.NUMERIC
    unique_ratio = len(set(str(v) for v in values)) / len(values)
    if unique_ratio < 0.3:
        return DataType.CATEGORICAL
    return DataType.TEXT


def _profile_data(data: List[Dict]) -> List[ColumnProfile]:
    if not data:
        return []
    all_columns: set[str] = set()
    for row in data:
        all_columns.update(row.keys())

    profiles: List[ColumnProfile] = []
    for col_name in sorted(all_columns):
        values = [row.get(col_name) for row in data if col_name in row]
        non_null = [v for v in values if v is not None and v != ""]
        dtype = _detect_column_type(col_name, non_null)

        stats: Dict[str, Any] = {}
        if dtype == DataType.NUMERIC and non_null:
            nums = [_to_float(v) for v in non_null if _is_numeric(v)]
            if nums:
                stats = {
                    "min": min(nums),
                    "max": max(nums),
                    "mean": stat_module.mean(nums),
                    "sum": sum(nums),
                }
                if len(nums) > 1:
                    stats["std"] = stat_module.stdev(nums)

        profiles.append(
            ColumnProfile(
                name=col_name,
                data_type=dtype,
                non_null_count=len(non_null),
                unique_count=len(set(str(v) for v in non_null)),
                sample_values=non_null[:5],
                stats=stats,
            )
        )
    return profiles


def _detect_analysis_type(profile: List[ColumnProfile]) -> str:
    has_time = any(p.data_type == DataType.DATETIME for p in profile)
    has_numeric = any(p.data_type == DataType.NUMERIC for p in profile)
    has_category = any(p.data_type == DataType.CATEGORICAL for p in profile)
    if has_time and has_numeric:
        return "trend"
    if has_category and has_numeric:
        return "comparison"
    if has_numeric:
        return "distribution"
    return "general"


# ---------------------------------------------------------------------------
# 各类分析
# ---------------------------------------------------------------------------

def _analyze_trend(data: List[Dict], profile: List[ColumnProfile]) -> Dict[str, Any]:
    time_col = next((p.name for p in profile if p.data_type == DataType.DATETIME), None)
    value_col = next((p.name for p in profile if p.data_type == DataType.NUMERIC), None)

    if not (time_col and value_col):
        return _analyze_general(data, profile)

    sorted_data = sorted(data, key=lambda x: x.get(time_col, 0))
    values = [_to_float(r[value_col]) for r in sorted_data if _is_numeric(r.get(value_col))]
    times = [r.get(time_col) for r in sorted_data]

    insights: List[str] = []
    stats: Dict[str, Any] = {}
    chart_config: Optional[Dict] = None

    if len(values) >= 2:
        first, last = values[0], values[-1]
        change = last - first
        change_pct = (change / first * 100) if first != 0 else 0
        trend = "上升" if change > 0 else "下降" if change < 0 else "持平"
        insights.append(f"整体呈{trend}趋势，变化幅度 {abs(change_pct):.1f}%")

        if len(values) > 2:
            rates = [
                (values[i] - values[i - 1]) / values[i - 1] * 100
                for i in range(1, len(values))
                if values[i - 1] != 0
            ]
            if rates:
                insights.append(f"平均增长率 {stat_module.mean(rates):.1f}%")

        stats = {
            "start_value": first,
            "end_value": last,
            "total_change": change,
            "change_percent": round(change_pct, 2),
            "trend": trend,
            "data_points": len(values),
        }

    chart_config = {
        "type": "line",
        "title": f"{value_col}趋势分析",
        "data": {
            "xAxis": [str(t) for t in times],
            "series": [{"name": value_col, "data": values}],
        },
    }
    return {
        "success": True,
        "insights": insights,
        "statistics": stats,
        "visualization_hint": "line",
        "chart_config": chart_config,
    }


def _analyze_distribution(data: List[Dict], profile: List[ColumnProfile]) -> Dict[str, Any]:
    numeric_profiles = [p for p in profile if p.data_type == DataType.NUMERIC]
    insights: List[str] = []
    stats: Dict[str, Any] = {}

    if numeric_profiles:
        main_col = numeric_profiles[0]
        values = [_to_float(r[main_col.name]) for r in data if _is_numeric(r.get(main_col.name))]
        if values:
            stats = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": round(stat_module.mean(values), 4),
                "sum": sum(values),
            }
            if len(values) > 1:
                stats["median"] = stat_module.median(values)
                stats["std"] = round(stat_module.stdev(values), 4)

            insights.append(f"共 {len(values)} 个数据点")
            insights.append(f"范围: {stats['min']:.2f} - {stats['max']:.2f}")
            insights.append(f"平均值: {stats['mean']:.2f}")

            if "std" in stats:
                threshold = stats["mean"] + 2 * stats["std"]
                outliers = [v for v in values if v > threshold]
                if outliers:
                    insights.append(f"发现 {len(outliers)} 个潜在异常值（> 均值+2σ）")

    return {
        "success": True,
        "insights": insights,
        "statistics": stats,
        "visualization_hint": "bar",
    }


def _analyze_comparison(data: List[Dict], profile: List[ColumnProfile]) -> Dict[str, Any]:
    cat_col = next((p.name for p in profile if p.data_type == DataType.CATEGORICAL), None)
    value_col = next((p.name for p in profile if p.data_type == DataType.NUMERIC), None)

    if not (cat_col and value_col):
        return _analyze_general(data, profile)

    buckets: Dict[str, List[float]] = {}
    for row in data:
        cat = row.get(cat_col)
        val = row.get(value_col)
        if cat and _is_numeric(val):
            buckets.setdefault(str(cat), []).append(_to_float(val))

    if not buckets:
        return _analyze_general(data, profile)

    cat_stats = {
        cat: {"sum": sum(vals), "avg": round(sum(vals) / len(vals), 4), "count": len(vals)}
        for cat, vals in buckets.items()
    }
    sorted_cats = sorted(cat_stats.items(), key=lambda x: x[1]["sum"], reverse=True)
    total = sum(s["sum"] for s in cat_stats.values())

    insights: List[str] = []
    top = sorted_cats[0]
    insights.append(f"最高: {top[0]} ({top[1]['sum']:.2f})")
    if len(sorted_cats) > 1:
        bottom = sorted_cats[-1]
        insights.append(f"最低: {bottom[0]} ({bottom[1]['sum']:.2f})")
    if total > 0:
        insights.append(f"{top[0]} 占比 {top[1]['sum'] / total * 100:.1f}%")

    viz = "pie" if len(cat_stats) <= 6 else "bar"
    chart_config = {
        "type": viz,
        "title": f"{cat_col}对比分析",
        "data": {
            "series": [
                {
                    "name": value_col,
                    "data": [{"name": k, "value": round(v["sum"], 2)} for k, v in sorted_cats],
                }
            ]
        },
    }
    return {
        "success": True,
        "insights": insights,
        "statistics": {"categories": len(cat_stats), "category_stats": cat_stats, "total": total},
        "visualization_hint": viz,
        "chart_config": chart_config,
    }


def _analyze_general(data: List[Dict], profile: List[ColumnProfile]) -> Dict[str, Any]:
    insights = [f"共 {len(data)} 条数据，{len(profile)} 个字段"]
    for p in profile:
        if p.stats:
            insights.append(f"{p.name}: 范围 {p.stats.get('min', 'N/A')} - {p.stats.get('max', 'N/A')}")
    for p in profile:
        if p.data_type == DataType.CATEGORICAL:
            insights.append(f"{p.name}: {p.unique_count} 个不同值")
    return {
        "success": True,
        "insights": insights,
        "statistics": {"total_rows": len(data), "total_columns": len(profile)},
        "visualization_hint": "table",
    }


def run_analysis(data: Any, analysis_type: str = "auto") -> Dict[str, Any]:
    """执行完整的数据分析流程。"""
    normalized = _normalize_data(data)
    if not normalized:
        return {
            "success": False,
            "error": "无有效数据可分析",
            "insights": [],
            "statistics": {},
            "visualization_hint": "none",
        }

    profile = _profile_data(normalized)

    if analysis_type == "auto":
        analysis_type = _detect_analysis_type(profile)

    dispatch = {
        "trend": _analyze_trend,
        "distribution": _analyze_distribution,
        "comparison": _analyze_comparison,
    }
    result = dispatch.get(analysis_type, _analyze_general)(normalized, profile)

    result["data_profile"] = {
        "total_rows": len(normalized),
        "columns": {
            col.name: {
                "type": col.data_type.value,
                "unique": col.unique_count,
                "non_null": col.non_null_count,
            }
            for col in profile
        },
    }
    return result


# ---------------------------------------------------------------------------
# Agentic Tool 适配层
# ---------------------------------------------------------------------------

class DataAnalyzerTool:
    """
    数据分析工具 (data_analyzer)。

    自动识别数据类型和特征，执行趋势分析 / 分布分析 / 对比分析 / 异常检测，
    推荐可视化类型并生成图表配置。
    """

    name = "data_analyzer"
    description = (
        "智能数据分析工具：传入结构化数据（字典列表、文本列表或单个字典），"
        "自动识别数据特征并执行趋势分析、分布分析、对比分析或异常检测，"
        "返回统计摘要、数据洞察和推荐的可视化配置。"
    )
    required_permissions: set[str] = set()
    param_model = DataAnalyzerParams

    async def run(self, params: Dict[str, Any], ctx: ToolContext) -> str:
        parsed = validate_params(DataAnalyzerParams, params)
        ensure_permissions(ctx, self.required_permissions)

        data = parsed.data
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:
                raise ToolExecutionError(f"data 字段不是合法 JSON: {exc}") from exc

        result = run_analysis(data, parsed.analysis_type)

        if not result.get("success"):
            return f"分析失败: {result.get('error', '未知错误')}"

        lines: List[str] = []

        profile = result.get("data_profile") or {}
        if profile:
            lines.append(f"📊 数据概况: {profile.get('total_rows', 0)} 行")

        viz = result.get("visualization_hint", "none")
        if viz != "none":
            lines.append(f"推荐图表类型: {viz}")

        insights = result.get("insights") or []
        if insights:
            lines.append("\n数据洞察:")
            for idx, insight in enumerate(insights, 1):
                lines.append(f"  {idx}. {insight}")

        stats = result.get("statistics") or {}
        if stats:
            lines.append("\n关键统计:")
            for k, v in stats.items():
                if isinstance(v, dict):
                    continue
                lines.append(f"  - {k}: {v}")

        chart = result.get("chart_config")
        if chart:
            lines.append(f"\n图表配置(JSON):\n{json.dumps(chart, ensure_ascii=False, indent=2)}")

        return "\n".join(lines)
