import { useState, useRef, useMemo } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import ReactEChartsCore from 'echarts-for-react';
import { TrendingUp, Search, Clock } from 'lucide-react';
import './Historian.css';

const AVAILABLE_TAGS = [
  { group: 'Section 1', tags: ['S1_speed_actual','S1_torque_pct','S1_current','S1_winding_temp','S1_bearing_health','S1_power'] },
  { group: 'Section 2', tags: ['S2_speed_actual','S2_torque_pct','S2_current','S2_winding_temp','S2_bearing_health','S2_power'] },
  { group: 'Section 3', tags: ['S3_speed_actual','S3_torque_pct','S3_current','S3_winding_temp','S3_bearing_health','S3_power'] },
  { group: 'System', tags: ['total_power_kw','total_energy_kwh','system_power_factor'] },
];

const TAG_COLORS = ['#FFFFFF','#4A9EFF','#FFB300','#4ADE80','#FF6B6B','#C084FC'];
const TIME_RANGES = [{ label: '1h', hours: 1 },{ label: '8h', hours: 8 },{ label: '24h', hours: 24 }];

export default function Historian() {
  const { tags } = useWebSocket();
  const [selectedTags, setSelectedTags] = useState(['S1_speed_actual','S1_torque_pct']);
  const [timeRange, setTimeRange] = useState('1h');
  const [searchQuery, setSearchQuery] = useState('');
  const historyRef = useRef({});

  // Record current values
  selectedTags.forEach(tag => {
    if (!historyRef.current[tag]) historyRef.current[tag] = { times: [], values: [] };
    const h = historyRef.current[tag];
    const now = new Date();
    h.times.push(now.toLocaleTimeString('en-GB', { hour12: false }));
    h.values.push(tags[tag] || 0);
    if (h.times.length > 3600) { h.times.shift(); h.values.shift(); }
  });

  const toggleTag = (tag) => {
    setSelectedTags(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag)
        : prev.length < 6 ? [...prev, tag] : prev
    );
  };

  const allTags = AVAILABLE_TAGS.flatMap(g => g.tags);
  const filtered = searchQuery ? allTags.filter(t => t.toLowerCase().includes(searchQuery.toLowerCase())) : null;

  const chartOption = useMemo(() => {
    const series = selectedTags.map((tag, i) => {
      const h = historyRef.current[tag] || { times: [], values: [] };
      return {
        name: tag,
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color: TAG_COLORS[i], width: 2 },
        data: h.values,
        yAxisIndex: i < 3 ? 0 : 1,
      };
    });
    const firstTag = historyRef.current[selectedTags[0]];
    return {
      backgroundColor: 'transparent',
      animation: false,
      grid: { top: 40, right: 60, bottom: 60, left: 60 },
      legend: { top: 5, textStyle: { color: '#8B8BA3', fontSize: 10, fontFamily: 'JetBrains Mono' } },
      dataZoom: [{ type: 'inside', start: 80, end: 100 }, { type: 'slider', bottom: 10, height: 20, borderColor: 'rgba(255,255,255,0.1)', fillerColor: 'rgba(74,158,255,0.1)', textStyle: { color: '#6B6B83', fontSize: 9 } }],
      tooltip: { trigger: 'axis', backgroundColor: '#1A1A3E', borderColor: 'rgba(255,255,255,0.1)', textStyle: { color: '#E0E0E0', fontSize: 10, fontFamily: 'JetBrains Mono' }, axisPointer: { type: 'cross', crossStyle: { color: 'rgba(255,255,255,0.2)' } } },
      xAxis: { type: 'category', data: firstTag?.times || [], axisLabel: { color: '#6B6B83', fontSize: 9, fontFamily: 'JetBrains Mono', interval: 'auto' }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } },
      yAxis: [
        { type: 'value', axisLabel: { color: '#8B8BA3', fontSize: 9 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } } },
        { type: 'value', axisLabel: { color: '#8B8BA3', fontSize: 9 }, splitLine: { show: false } },
      ],
      series,
    };
  }, [selectedTags, tags]);

  return (
    <div className="historian-screen">
      <div className="screen-header">
        <h1 className="screen-title"><TrendingUp size={20} style={{ marginRight: 8 }} />Historian & Trends</h1>
        <div className="screen-actions">
          {TIME_RANGES.map(tr => (
            <button key={tr.label} className={`btn btn-sm ${timeRange === tr.label ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTimeRange(tr.label)}>
              {tr.label}
            </button>
          ))}
        </div>
      </div>
      <div className="historian-layout">
        <div className="historian-sidebar card">
          <div className="historian-search">
            <Search size={12} /><input type="text" placeholder="Search tags..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} className="historian-search-input" />
          </div>
          <div className="historian-tag-list">
            {filtered ? (
              filtered.map(tag => (
                <label key={tag} className={`historian-tag-item ${selectedTags.includes(tag)?'selected':''}`}>
                  <input type="checkbox" checked={selectedTags.includes(tag)} onChange={() => toggleTag(tag)} />
                  <span className="historian-tag-name">{tag}</span>
                  {selectedTags.includes(tag) && <span className="historian-tag-color" style={{background:TAG_COLORS[selectedTags.indexOf(tag)]}}></span>}
                </label>
              ))
            ) : (
              AVAILABLE_TAGS.map(group => (
                <div key={group.group}>
                  <div className="historian-group-label">{group.group}</div>
                  {group.tags.map(tag => (
                    <label key={tag} className={`historian-tag-item ${selectedTags.includes(tag)?'selected':''}`}>
                      <input type="checkbox" checked={selectedTags.includes(tag)} onChange={() => toggleTag(tag)} />
                      <span className="historian-tag-name">{tag.split('_').slice(1).join('_')}</span>
                      {selectedTags.includes(tag) && <span className="historian-tag-color" style={{background:TAG_COLORS[selectedTags.indexOf(tag)]}}></span>}
                    </label>
                  ))}
                </div>
              ))
            )}
          </div>
          <div className="historian-tag-count">{selectedTags.length}/6 tags selected</div>
        </div>
        <div className="historian-chart-area card">
          <ReactEChartsCore option={chartOption} style={{ height: '100%', minHeight: '400px' }} notMerge={true} />
        </div>
      </div>
    </div>
  );
}
