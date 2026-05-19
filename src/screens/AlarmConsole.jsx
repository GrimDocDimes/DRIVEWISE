import { useState, useMemo } from 'react';
import { useAlarms } from '../contexts/AlarmContext';
import ReactEChartsCore from 'echarts-for-react';
import { Bell, CheckCheck, AlertTriangle, Filter } from 'lucide-react';
import './AlarmConsole.css';

const PRIORITY_COLORS = { critical: '#FF3B30', high: '#FF6B6B', warning: '#FFB300', low: '#4A9EFF' };
const STATE_LABELS = { UNACKED_ACTIVE: 'UNACKED', ACKED_ACTIVE: 'ACKED', ACKED_CLEARED: 'CLEARED' };

export default function AlarmConsole() {
  const { alarms, activeAlarms, unacknowledgedAlarms, acknowledgeAlarm, acknowledgeAll, alarmsBySection, alarmsByCategory, standingAlarms, isAlarmFlood, unackedCount } = useAlarms();
  const [selectedAlarms, setSelectedAlarms] = useState(new Set());
  const [filterPriority, setFilterPriority] = useState('all');

  const filteredAlarms = useMemo(() => {
    let list = activeAlarms;
    if (filterPriority !== 'all') list = list.filter(a => a.priority === filterPriority);
    return list.sort((a, b) => {
      const po = { critical: 0, high: 1, warning: 2, low: 3 };
      return (po[a.priority] - po[b.priority]) || (new Date(b.timestamp) - new Date(a.timestamp));
    });
  }, [activeAlarms, filterPriority]);

  const toggleSelect = (id) => { setSelectedAlarms(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; }); };
  const handleBulkAck = () => { selectedAlarms.forEach(id => acknowledgeAlarm(id)); setSelectedAlarms(new Set()); };

  const sectionChartOpt = { backgroundColor: 'transparent', grid: { top: 25, right: 10, bottom: 25, left: 40 }, title: { text: 'By Section', left: 'center', top: 0, textStyle: { color: '#8B8BA3', fontSize: 10, fontFamily: 'JetBrains Mono' } }, xAxis: { type: 'category', data: Object.keys(alarmsBySection).length ? Object.keys(alarmsBySection) : ['S1','S2','S3'], axisLabel: { color: '#6B6B83', fontSize: 9 }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } }, yAxis: { type: 'value', axisLabel: { color: '#6B6B83', fontSize: 9 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } } }, series: [{ type: 'bar', data: Object.keys(alarmsBySection).length ? Object.values(alarmsBySection) : [0,0,0], itemStyle: { color: '#4A9EFF', borderRadius: [3,3,0,0] }, barWidth: '50%' }] };
  const categoryChartOpt = { backgroundColor: 'transparent', grid: { top: 25, right: 10, bottom: 25, left: 80 }, title: { text: 'By Category', left: 'center', top: 0, textStyle: { color: '#8B8BA3', fontSize: 10, fontFamily: 'JetBrains Mono' } }, yAxis: { type: 'category', data: Object.keys(alarmsByCategory).length ? Object.keys(alarmsByCategory) : ['overcurrent','thermal'], axisLabel: { color: '#6B6B83', fontSize: 9 }, axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } } }, xAxis: { type: 'value', axisLabel: { color: '#6B6B83', fontSize: 9 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } } }, series: [{ type: 'bar', data: Object.keys(alarmsByCategory).length ? Object.values(alarmsByCategory) : [0,0], itemStyle: { color: '#FFB300', borderRadius: [0,3,3,0] }, barWidth: '50%' }] };

  return (
    <div className="alarm-screen">
      <div className="screen-header">
        <h1 className="screen-title"><Bell size={20} style={{ marginRight: 8 }} />Alarm Console
          {isAlarmFlood && <span className="alarm-flood-badge"><AlertTriangle size={12} /> FLOOD</span>}
        </h1>
        <div className="screen-actions">
          <span className="alarm-count-display">{unackedCount} Unacked</span>
          <button className="btn btn-ghost btn-sm" onClick={acknowledgeAll} disabled={unackedCount === 0}><CheckCheck size={14} /> Ack All</button>
          {selectedAlarms.size > 0 && <button className="btn btn-primary btn-sm" onClick={handleBulkAck}>Ack ({selectedAlarms.size})</button>}
        </div>
      </div>
      <div className="alarm-layout">
        <div className="alarm-list-panel card">
          <div className="alarm-list-header"><span className="card-title">Active Alarms</span>
            <div className="alarm-filter"><Filter size={12} />
              <select value={filterPriority} onChange={e => setFilterPriority(e.target.value)} className="alarm-filter-select">
                <option value="all">All</option><option value="critical">Critical</option><option value="high">High</option><option value="warning">Warning</option><option value="low">Low</option>
              </select>
            </div>
          </div>
          <div className="alarm-list-table-wrapper">
            <table className="data-table alarm-table"><thead><tr><th style={{width:30}}></th><th style={{width:6}}></th><th>Time</th><th>Section</th><th>Tag</th><th>Description</th><th>Value</th><th>State</th></tr></thead>
              <tbody>{filteredAlarms.length === 0 ? <tr><td colSpan="8" className="alarm-empty">No active alarms</td></tr> : filteredAlarms.map(a => (
                <tr key={a.id} className={`alarm-row ${a.state==='UNACKED_ACTIVE'?'unacked':''} ${a.firstOut?'first-out':''}`} onClick={() => acknowledgeAlarm(a.id)}>
                  <td><input type="checkbox" checked={selectedAlarms.has(a.id)} onChange={() => toggleSelect(a.id)} onClick={e => e.stopPropagation()} /></td>
                  <td><div className="alarm-priority-chip" style={{background:PRIORITY_COLORS[a.priority]}}></div></td>
                  <td className="alarm-time">{new Date(a.timestamp).toLocaleTimeString('en-GB',{hour12:false})}</td>
                  <td>{a.section}</td><td className="alarm-tag">{a.tag}{a.firstOut && <span className="first-out-badge">1st</span>}</td>
                  <td className="alarm-desc">{a.description}</td><td>{a.value?.toFixed(1)}/{a.threshold}</td>
                  <td><span className={`alarm-state-badge ${a.state.toLowerCase().replace('_','-')}`}>{STATE_LABELS[a.state]}</span></td>
                </tr>))}</tbody></table>
          </div>
        </div>
        <div className="alarm-analysis-panel">
          <div className="alarm-chart-card card"><ReactEChartsCore option={sectionChartOpt} style={{height:'150px'}} /></div>
          <div className="alarm-chart-card card"><ReactEChartsCore option={categoryChartOpt} style={{height:'150px'}} /></div>
          <div className="alarm-standing card"><div className="card-header"><span className="card-title">Standing (&gt;24h)</span><span className="card-subtitle">{standingAlarms.length}</span></div>
            {standingAlarms.length === 0 ? <p className="alarm-empty-small">None</p> : standingAlarms.map(a => <div key={a.id} className="standing-item"><div className="alarm-priority-chip" style={{background:PRIORITY_COLORS[a.priority]}}></div><span>{a.section}—{a.tag}</span></div>)}
          </div>
        </div>
      </div>
    </div>
  );
}
