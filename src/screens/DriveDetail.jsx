import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useWebSocket, useSectionTags } from '../contexts/WebSocketContext';
import ReactEChartsCore from 'echarts-for-react';
import { Play, Square, AlertOctagon, ChevronLeft, ChevronRight, Settings } from 'lucide-react';
import './DriveDetail.css';

const SECTIONS = ['S1', 'S2', 'S3'];
const SECTION_NAMES = { S1: 'Section 1 — Infeed', S2: 'Section 2 — Transfer', S3: 'Section 3 — Discharge' };

const PROTECTION_ROWS = [
  { key: 'overcurrent', label: 'Overcurrent', unit: '%' },
  { key: 'overvoltage', label: 'DC Bus Overvoltage', unit: 'V' },
  { key: 'undervoltage', label: 'Supply Undervoltage', unit: 'V' },
  { key: 'earthfault', label: 'Earth Fault', unit: 'mA' },
  { key: 'thermal', label: 'Motor Thermal', unit: '°C' },
];

function AnimatedMimic({ sectionTags, status }) {
  const isRunning = status === 'RUNNING';
  const isFault = status === 'FAULT';
  const freq = sectionTags.frequency || 0;
  const current = sectionTags.current || 0;
  const dcBus = sectionTags.dc_bus_voltage || 0;

  return (
    <div className="drive-mimic">
      <svg viewBox="0 0 500 300" className="mimic-svg" preserveAspectRatio="xMidYMid meet">
        {/* Supply incoming */}
        <g>
          <text x="30" y="30" fill="var(--text-muted)" fontSize="10" fontFamily="var(--font-mono)">SUPPLY</text>
          <rect x="15" y="40" width="60" height="50" rx="4" fill="var(--bg-panel)" stroke="var(--border-default)" strokeWidth="1.5" />
          <text x="45" y="60" fill="var(--text-secondary)" fontSize="9" textAnchor="middle" fontFamily="var(--font-mono)">3~AC</text>
          <text x="45" y="75" fill="var(--text-value)" fontSize="10" textAnchor="middle" fontFamily="var(--font-mono)">415V</text>
        </g>

        {/* Cable: Supply → Drive */}
        <g className="cable-group">
          {[55, 65, 75].map((y, i) => (
            <line key={i} x1="75" y1={y - 5} x2="140" y2={y - 5}
              stroke={['#FF6B6B', '#FFB300', '#4A9EFF'][i]} strokeWidth="2" opacity="0.6" />
          ))}
          {isRunning && (
            <g>
              {[55, 65, 75].map((y, i) => (
                <circle key={i} cx="100" cy={y - 5} r="3" fill={['#FF6B6B', '#FFB300', '#4A9EFF'][i]}>
                  <animate attributeName="cx" from="80" to="135" dur="1s" repeatCount="indefinite" begin={`${i * 0.15}s`} />
                </circle>
              ))}
            </g>
          )}
        </g>

        {/* ACS880 Drive Cabinet */}
        <g>
          <text x="145" y="20" fill="var(--text-muted)" fontSize="10" fontFamily="var(--font-mono)">ACS880 DRIVE</text>
          <rect x="140" y="30" width="120" height="100" rx="6" fill="var(--bg-panel)"
            stroke={isFault ? 'var(--color-alarm)' : isRunning ? 'var(--color-accent)' : 'var(--border-default)'}
            strokeWidth="2" />

          {/* Drive front panel display */}
          <rect x="155" y="42" width="90" height="45" rx="3" fill="var(--bg-input)"
            stroke="var(--border-default)" strokeWidth="1" />
          <text x="165" y="56" fill="var(--text-muted)" fontSize="8" fontFamily="var(--font-mono)">FREQ</text>
          <text x="230" y="56" fill="var(--text-value)" fontSize="9" textAnchor="end" fontFamily="var(--font-mono)">{freq.toFixed(1)} Hz</text>
          <text x="165" y="68" fill="var(--text-muted)" fontSize="8" fontFamily="var(--font-mono)">CURR</text>
          <text x="230" y="68" fill="var(--text-value)" fontSize="9" textAnchor="end" fontFamily="var(--font-mono)">{current.toFixed(1)} A</text>
          <text x="165" y="80" fill="var(--text-muted)" fontSize="8" fontFamily="var(--font-mono)">DC</text>
          <text x="230" y="80" fill="var(--text-value)" fontSize="9" textAnchor="end" fontFamily="var(--font-mono)">{dcBus.toFixed(0)} V</text>

          {/* Status LEDs */}
          <circle cx="165" cy="102" r="4" fill={isRunning ? 'var(--color-healthy)' : 'var(--bg-input)'}
            stroke="var(--border-default)" strokeWidth="0.5" />
          <text x="173" y="105" fill="var(--text-muted)" fontSize="7" fontFamily="var(--font-mono)">RUN</text>
          <circle cx="200" cy="102" r="4" fill={isFault ? 'var(--color-alarm)' : 'var(--bg-input)'}
            stroke="var(--border-default)" strokeWidth="0.5">
            {isFault && <animate attributeName="opacity" values="1;0.3;1" dur="0.5s" repeatCount="indefinite" />}
          </circle>
          <text x="208" y="105" fill="var(--text-muted)" fontSize="7" fontFamily="var(--font-mono)">FLT</text>

          {/* ABB logo placeholder */}
          <text x="200" y="125" fill="var(--color-alarm)" fontSize="11" fontWeight="bold" textAnchor="middle" fontFamily="var(--font-mono)">ABB</text>
        </g>

        {/* Cable: Drive → Motor */}
        <g className="cable-group">
          {[55, 65, 75].map((y, i) => (
            <line key={i} x1="260" y1={y - 5} x2="330" y2={y - 5}
              stroke={['#FF6B6B', '#FFB300', '#4A9EFF'][i]} strokeWidth="2" opacity="0.6" />
          ))}
          {isRunning && (
            <g>
              {[55, 65, 75].map((y, i) => (
                <circle key={i} cx="290" cy={y - 5} r="3" fill={['#FF6B6B', '#FFB300', '#4A9EFF'][i]}>
                  <animate attributeName="cx" from="265" to="325" dur="0.8s" repeatCount="indefinite" begin={`${i * 0.1}s`} />
                </circle>
              ))}
            </g>
          )}
        </g>

        {/* Motor */}
        <g>
          <text x="345" y="20" fill="var(--text-muted)" fontSize="10" fontFamily="var(--font-mono)">MOTOR</text>
          <rect x="330" y="30" width="80" height="70" rx="6" fill="var(--bg-panel)"
            stroke={isFault ? 'var(--color-alarm)' : isRunning ? 'var(--color-accent)' : 'var(--border-default)'}
            strokeWidth="1.5" />
          {/* Cooling fins */}
          {[40, 48, 56, 64, 72, 80, 88].map(y => (
            <line key={y} x1="330" y1={y} x2="324" y2={y} stroke="var(--border-default)" strokeWidth="1" />
          ))}
          {/* Rotor */}
          <g style={{ transformOrigin: '370px 65px', animation: isRunning ? 'motor-rotate 1.5s linear infinite' : 'none' }}>
            <circle cx="370" cy="65" r="18" fill="none" stroke={isRunning ? 'var(--color-accent)' : 'var(--text-muted)'}
              strokeWidth="1.5" strokeDasharray="8,5" />
          </g>
          <circle cx="370" cy="65" r="5" fill="var(--bg-input)" stroke="var(--text-muted)" strokeWidth="1" />

          {/* Shaft */}
          <line x1="410" y1="65" x2="440" y2="65" stroke={isRunning ? 'var(--color-accent)' : 'var(--text-muted)'}
            strokeWidth="4" strokeLinecap="round" />
        </g>

        {/* Mechanical Load */}
        <g>
          <text x="445" y="40" fill="var(--text-muted)" fontSize="10" fontFamily="var(--font-mono)">LOAD</text>
          <rect x="440" y="48" width="45" height="35" rx="4" fill="var(--bg-surface)"
            stroke="var(--border-default)" strokeWidth="1.5" />
          <text x="462" y="70" fill="var(--text-secondary)" fontSize="8" textAnchor="middle" fontFamily="var(--font-mono)">CONV</text>
        </g>

        {/* Ground symbol */}
        <g transform="translate(45, 110)">
          <line x1="0" y1="0" x2="0" y2="15" stroke="var(--text-muted)" strokeWidth="1.5" />
          <line x1="-10" y1="15" x2="10" y2="15" stroke="var(--text-muted)" strokeWidth="1.5" />
          <line x1="-6" y1="19" x2="6" y2="19" stroke="var(--text-muted)" strokeWidth="1" />
          <line x1="-3" y1="23" x2="3" y2="23" stroke="var(--text-muted)" strokeWidth="0.5" />
        </g>
      </svg>
    </div>
  );
}

function SpeedTorqueTrend({ sectionTags, section }) {
  const historyRef = useRef({ speed: [], torque: [], time: [] });
  const maxPoints = 300; // 5 minutes at 1/sec

  useEffect(() => {
    const now = new Date();
    const h = historyRef.current;
    h.time.push(now.toLocaleTimeString('en-GB', { hour12: false }));
    h.speed.push(sectionTags.speed_actual || 0);
    h.torque.push(sectionTags.torque_pct || 0);
    if (h.time.length > maxPoints) {
      h.time.shift(); h.speed.shift(); h.torque.shift();
    }
  }, [sectionTags.speed_actual, sectionTags.torque_pct]);

  const h = historyRef.current;

  const option = {
    backgroundColor: 'transparent',
    animation: false,
    grid: { top: 30, right: 60, bottom: 30, left: 60 },
    legend: {
      data: ['Speed', 'Torque'],
      top: 0,
      textStyle: { color: '#A0A0A0', fontSize: 10, fontFamily: 'JetBrains Mono' },
    },
    xAxis: {
      type: 'category',
      data: h.time,
      axisLabel: { color: '#6B6B83', fontSize: 9, fontFamily: 'JetBrains Mono', interval: Math.floor(h.time.length / 5) },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      splitLine: { show: false },
    },
    yAxis: [
      {
        type: 'value',
        name: 'RPM',
        nameTextStyle: { color: '#8B8BA3', fontSize: 9 },
        axisLabel: { color: '#8B8BA3', fontSize: 9 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } },
        max: 1600,
      },
      {
        type: 'value',
        name: '%',
        nameTextStyle: { color: '#8B8BA3', fontSize: 9 },
        axisLabel: { color: '#8B8BA3', fontSize: 9 },
        splitLine: { show: false },
        max: 120,
      }
    ],
    series: [
      {
        name: 'Speed',
        type: 'line',
        data: h.speed,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#FFFFFF', width: 2 },
        areaStyle: { color: 'rgba(255,255,255,0.03)' },
      },
      {
        name: 'Torque',
        type: 'line',
        yAxisIndex: 1,
        data: h.torque,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#4A9EFF', width: 2 },
        areaStyle: { color: 'rgba(74,158,255,0.05)' },
      },
      // Setpoint line
      {
        name: 'Setpoint',
        type: 'line',
        data: h.time.map(() => sectionTags.speed_ref || 0),
        symbol: 'none',
        lineStyle: { color: '#4A9EFF', width: 1, type: 'dashed' },
        silent: true,
      }
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1A1A3E',
      borderColor: 'rgba(255,255,255,0.1)',
      textStyle: { color: '#E0E0E0', fontSize: 10, fontFamily: 'JetBrains Mono' },
    },
  };

  return (
    <div className="detail-panel">
      <div className="detail-panel-header">
        <span className="detail-panel-title">Speed & Torque Trend</span>
        <span className="detail-panel-subtitle">Last 5 minutes</span>
      </div>
      <ReactEChartsCore option={option} style={{ height: '180px' }} notMerge={true} />
    </div>
  );
}

function ParameterTable({ sectionTags, section, sendCommand }) {
  const [editing, setEditing] = useState(null);
  const [editValue, setEditValue] = useState('');

  const params = [
    { key: 'control_mode', label: 'Control Mode', value: sectionTags.control_mode || 'DTC', editable: true, type: 'select', options: ['DTC', 'SCALAR'] },
    { key: 'ramp_accel', label: 'Accel Time', value: sectionTags.ramp_accel || 10, unit: 's', editable: true, type: 'number' },
    { key: 'ramp_decel', label: 'Decel Time', value: sectionTags.ramp_decel || 10, unit: 's', editable: true, type: 'number' },
    { key: 'ramp_estop', label: 'E-Stop Time', value: sectionTags.ramp_estop || 2, unit: 's', editable: true, type: 'number' },
    { key: 'speed_ref', label: 'Speed Ref', value: sectionTags.speed_ref || 0, unit: 'RPM', editable: true, type: 'number' },
    { key: 'current_pct', label: 'Current Limit', value: '150', unit: '%', editable: true, type: 'number' },
  ];

  const handleEdit = (param) => {
    setEditing(param.key);
    setEditValue(String(param.value));
  };

  const handleSave = (paramKey) => {
    sendCommand('set_parameter', { section, parameter: paramKey, value: editValue });
    setEditing(null);
  };

  return (
    <div className="detail-panel">
      <div className="detail-panel-header">
        <span className="detail-panel-title">Drive Parameters</span>
        <Settings size={14} color="var(--text-muted)" />
      </div>
      <table className="data-table">
        <thead>
          <tr><th>Parameter</th><th>Value</th><th>Unit</th></tr>
        </thead>
        <tbody>
          {params.map(p => (
            <tr key={p.key} onClick={() => p.editable && handleEdit(p)} style={{ cursor: p.editable ? 'pointer' : 'default' }}>
              <td>{p.label}</td>
              <td>
                {editing === p.key ? (
                  <input className="param-input" type={p.type === 'number' ? 'number' : 'text'}
                    value={editValue} onChange={e => setEditValue(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') handleSave(p.key); if (e.key === 'Escape') setEditing(null); }}
                    autoFocus onClick={e => e.stopPropagation()} />
                ) : (
                  <span className="param-value">{typeof p.value === 'number' ? p.value.toFixed(1) : p.value}</span>
                )}
              </td>
              <td className="param-unit">{p.unit || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProtectionStatus({ sectionTags }) {
  return (
    <div className="detail-panel">
      <div className="detail-panel-header">
        <span className="detail-panel-title">Protection Status</span>
      </div>
      <div className="protection-rows">
        {PROTECTION_ROWS.map(prot => {
          const value = sectionTags[`prot_${prot.key}_value`] || 0;
          const threshold = sectionTags[`prot_${prot.key}_threshold`] || 100;
          const tripped = sectionTags[`prot_${prot.key}_trip`] || false;
          const ratio = Math.min((value / threshold) * 100, 100);
          const barClass = tripped ? 'danger' : ratio > 80 ? 'warning' : ratio > 50 ? 'normal' : 'good';

          return (
            <div key={prot.key} className={`protection-row ${tripped ? 'tripped' : ''}`}>
              <span className="protection-label">{prot.label}</span>
              <div className="protection-bar-container">
                <div className="progress-bar" style={{ flex: 1 }}>
                  <div className={`progress-bar-fill ${barClass}`} style={{ width: `${ratio}%` }}></div>
                </div>
              </div>
              <span className="protection-value">{typeof value === 'number' ? value.toFixed(1) : value}</span>
              <span className="protection-threshold">/ {threshold}</span>
              <span className="protection-unit">{prot.unit}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function DriveDetail() {
  const { sectionId } = useParams();
  const section = SECTIONS.includes(sectionId) ? sectionId : 'S1';
  const { tags, sendCommand } = useWebSocket();
  const sectionTags = useSectionTags(section);
  const navigate = useNavigate();
  const status = sectionTags.status || 'STOPPED';

  const sectionIdx = SECTIONS.indexOf(section);
  const prevSection = sectionIdx > 0 ? SECTIONS[sectionIdx - 1] : null;
  const nextSection = sectionIdx < SECTIONS.length - 1 ? SECTIONS[sectionIdx + 1] : null;

  return (
    <div className="drive-detail-screen">
      <div className="screen-header">
        <div className="flex items-center gap-md">
          {prevSection && (
            <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/drive/${prevSection}`)}>
              <ChevronLeft size={14} />
            </button>
          )}
          <h1 className="screen-title">{SECTION_NAMES[section]}</h1>
          {nextSection && (
            <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/drive/${nextSection}`)}>
              <ChevronRight size={14} />
            </button>
          )}
        </div>
        <div className="screen-actions">
          <span className={`status-pill ${status.toLowerCase()}`}>
            <span className="status-dot"></span>{status}
          </span>
          <button className="btn btn-success btn-sm"
            onClick={() => sendCommand('start_section', { section })}
            disabled={status === 'RUNNING'}>
            <Play size={12} /> Start
          </button>
          <button className="btn btn-danger btn-sm"
            onClick={() => sendCommand('stop_section', { section })}>
            <Square size={12} /> Stop
          </button>
          <button className="btn btn-danger btn-sm"
            onClick={() => sendCommand('estop_section', { section })}
            style={{ borderColor: 'var(--color-alarm)' }}>
            <AlertOctagon size={12} /> E-STOP
          </button>
        </div>
      </div>

      <div className="drive-detail-layout">
        <div className="drive-detail-left">
          <AnimatedMimic sectionTags={sectionTags} status={status} />
        </div>
        <div className="drive-detail-right">
          <SpeedTorqueTrend sectionTags={sectionTags} section={section} />
          <ParameterTable sectionTags={sectionTags} section={section} sendCommand={sendCommand} />
          <ProtectionStatus sectionTags={sectionTags} />
        </div>
      </div>
    </div>
  );
}
