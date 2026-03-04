import React, { useRef, useEffect, useState, useCallback } from 'react';
import * as echarts from 'echarts/core';
import { LineChart, BarChart, PieChart, ScatterChart } from 'echarts/charts';
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart,
  BarChart,
  PieChart,
  ScatterChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  CanvasRenderer,
]);

function isDarkMode() {
  return document.documentElement.getAttribute('data-theme') === 'dark';
}

function deepMerge(target, source) {
  const out = { ...target };
  for (const key of Object.keys(source)) {
    const sv = source[key];
    const tv = target[key];
    if (sv && typeof sv === 'object' && !Array.isArray(sv) && tv && typeof tv === 'object' && !Array.isArray(tv)) {
      out[key] = deepMerge(tv, sv);
    } else {
      out[key] = sv;
    }
  }
  return out;
}

function mergeAxis(axis, override) {
  if (!axis) return axis;
  if (Array.isArray(axis)) return axis.map((a) => deepMerge(a, override));
  return deepMerge(axis, override);
}

const DARK_AXIS = {
  axisLine: { lineStyle: { color: '#3f3f46' } },
  axisLabel: { color: '#9CA3AF' },
  splitLine: { lineStyle: { color: '#27272a' } },
};

function applyThemeOverride(option, dark) {
  if (!dark) return { ...option, backgroundColor: 'transparent' };

  let themed = deepMerge(option, {
    backgroundColor: 'transparent',
    textStyle: { color: '#E5E7EB' },
    title: { textStyle: { color: '#E5E7EB' }, subtextStyle: { color: '#9CA3AF' } },
    legend: { textStyle: { color: '#9CA3AF' } },
    tooltip: { backgroundColor: '#27272a', borderColor: '#3f3f46', textStyle: { color: '#E5E7EB' } },
  });

  if (themed.xAxis) themed.xAxis = mergeAxis(themed.xAxis, DARK_AXIS);
  if (themed.yAxis) themed.yAxis = mergeAxis(themed.yAxis, DARK_AXIS);

  return themed;
}

export default function EChartsRenderer({ config, width = '100%', height = '400px' }) {
  const chartRef = useRef(null);
  const instanceRef = useRef(null);
  const [error, setError] = useState(null);

  const configJsonRef = useRef('');
  const renderChart = useCallback(() => {
    if (!chartRef.current || !config) return;
    const option = config.echarts_option;
    if (!option) { setError('缺少 echarts_option'); return; }

    const configJson = JSON.stringify(config);
    if (instanceRef.current && configJsonRef.current === configJson) {
      // config 未变，仅刷新主题（如跟随主题切换），避免 dispose/re-init 导致屏闪
      instanceRef.current.setOption(applyThemeOverride(option, isDarkMode()), true);
      return;
    }
    configJsonRef.current = configJson;

    try {
      if (instanceRef.current) {
        instanceRef.current.dispose();
        instanceRef.current = null;
      }
      instanceRef.current = echarts.init(chartRef.current);
      instanceRef.current.setOption(applyThemeOverride(option, isDarkMode()), true);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, [config]);

  useEffect(() => {
    renderChart();
    return () => {
      if (instanceRef.current) {
        instanceRef.current.dispose();
        instanceRef.current = null;
      }
    };
  }, [renderChart]);

  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.attributeName === 'data-theme') {
          renderChart();
          break;
        }
      }
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, [renderChart]);

  useEffect(() => {
    if (!chartRef.current) return;
    const ro = new ResizeObserver(() => instanceRef.current?.resize());
    ro.observe(chartRef.current);
    return () => ro.disconnect();
  }, []);

  if (error) {
    return <div className="echart-error">图表渲染失败: {error}</div>;
  }

  return (
    <div className="echart-wrapper">
      {config.title && <div className="echart-title">{config.title}</div>}
      <div ref={chartRef} style={{ width, height }} />
    </div>
  );
}

/**
 * 表格渲染（chart_type === "table" 时使用）
 */
export function TableRenderer({ config }) {
  const columns = config.columns || [];
  const rows = config.data || [];
  const pageSize = config.pageSize || 10;
  const [page, setPage] = useState(0);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const visibleRows = config.pagination
    ? rows.slice(page * pageSize, (page + 1) * pageSize)
    : rows;

  if (!columns.length && !rows.length) {
    return <div className="echart-error">无表格数据</div>;
  }

  return (
    <div className="echart-table-wrapper">
      {config.title && <div className="echart-title">{config.title}</div>}
      <div className="echart-table-scroll">
        <table className="echart-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, i) => (
              <tr key={i}>
                {columns.map((col) => (
                  <td key={col.key}>{row[col.key] ?? ''}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {config.pagination && totalPages > 1 && (
        <div className="echart-table-pagination">
          <button disabled={page === 0} onClick={() => setPage(page - 1)}>上一页</button>
          <span>{page + 1} / {totalPages}</span>
          <button disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}>下一页</button>
        </div>
      )}
    </div>
  );
}
