import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useWebSocket } from '../contexts/WebSocketContext';
import { Play, Square, AlertTriangle, Zap } from 'lucide-react';
import './SystemOverview.css';

const SECTIONS = ['S1', 'S2', 'S3'];
const SECTION_LABELS = { S1: 'Section 1 — Infeed', S2: 'Section 2 — Transfer', S3: 'Section 3 — Discharge' };

function ConveyorBelt({ tags }) {
  const beltRef = useRef(null);
  const anyRunning = SECTIONS.some(s => tags[`${s}_status`] === 'RUNNING');
  const avgSpeed = SECTIONS.reduce((sum, s) => sum + (tags[`${s}_belt_speed`] || 0), 0) / 3;
  const materialLoad = tags['S1_material_load'] || 0;

  return (
    <div className="conveyor-belt-container">
      <svg viewBox="0 0 1100 100" className="conveyor-belt-svg" preserveAspectRatio="xMidYMid meet">
        {/* Belt structure */}
        <defs>
          <linearGradient id="beltGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#2A2A4E" />
            <stop offset="50%" stopColor="#3A3A5E" />
            <stop offset="100%" stopColor="#2A2A4E" />
          </linearGradient>
          <pattern id="beltPattern" x="0" y="0" width="40" height="10" patternUnits="userSpaceOnUse">
            <rect width="40" height="10" fill="url(#beltGrad)" />
            <line x1="20" y1="0" x2="20" y2="10" stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
          </pattern>
        </defs>

        {/* Belt body */}
        <rect x="30" y="35" width="1040" height="30" rx="4" fill="url(#beltPattern)"
          stroke="var(--border-default)" strokeWidth="1">
          {anyRunning && (
            <animate attributeName="x" from="30" to="-10" dur={`${Math.max(0.5, 3 / Math.max(avgSpeed, 0.1))}s`} repeatCount="indefinite" />
          )}
        </rect>

        {/* Section dividers */}
        <line x1="370" y1="25" x2="370" y2="75" stroke="var(--color-accent)" strokeWidth="1" strokeDasharray="4,4" opacity="0.4" />
        <line x1="730" y1="25" x2="730" y2="75" stroke="var(--color-accent)" strokeWidth="1" strokeDasharray="4,4" opacity="0.4" />

        {/* Section labels on belt */}
        <text x="200" y="28" fill="var(--text-muted)" fontSize="10" textAnchor="middle" fontFamily="var(--font-mono)">S1</text>
        <text x="550" y="28" fill="var(--text-muted)" fontSize="10" textAnchor="middle" fontFamily="var(--font-mono)">S2</text>
        <text x="900" y="28" fill="var(--text-muted)" fontSize="10" textAnchor="middle" fontFamily="var(--font-mono)">S3</text>

        {/* Drive pulleys */}
        {[50, 370, 730].map((x, i) => (
          <g key={i}>
            <circle cx={x} cy="50" r="18" fill="var(--bg-card)" stroke="var(--border-default)" strokeWidth="1.5" />
            <circle cx={x} cy="50" r="6" fill="var(--bg-input)" stroke="var(--text-muted)" strokeWidth="1">
              {tags[`${SECTIONS[i]}_status`] === 'RUNNING' && (
                <animateTransform attributeName="transform" type="rotate"
                  from={`0 ${x} 50`} to={`360 ${x} 50`}
                  dur="2s" repeatCount="indefinite" />
              )}
            </circle>
          </g>
        ))}

        {/* Tail pulleys */}
        {[340, 700, 1060].map((x, i) => (
          <circle key={i} cx={x} cy="50" r="12" fill="var(--bg-card)" stroke="var(--border-default)" strokeWidth="1" />
        ))}

        {/* Material on belt */}
        {materialLoad > 5 && (
          <rect x="80" y="25" width={`${materialLoad * 9.5}`} height="10" rx="2"
            fill="var(--color-warning)" opacity="0.35">
            {anyRunning && (
              <animate attributeName="x" from="80" to="1000" dur="8s" repeatCount="indefinite" />
            )}
          </rect>
        )}

        {/* Flow arrows */}
        {anyRunning && [200, 550, 900].map((x, i) => (
          <g key={i} opacity="0.6">
            <polygon points={`${x-6},45 ${x+6},50 ${x-6},55`} fill="var(--color-accent)">
              <animate attributeName="opacity" values="0.3;0.8;0.3" dur="1.5s" repeatCount="indefinite" begin={`${i*0.3}s`} />
            </polygon>
          </g>
        ))}
      </svg>
    </div>
  );
}

function MotorGraphic({ status, speed }) {
  const isRunning = status === 'RUNNING';
  const isFault = status === 'FAULT';

  return (
    <div className={`motor-graphic ${isRunning ? 'running' : ''} ${isFault ? 'fault' : ''}`}>
      <svg viewBox="0 0 80 80" className="motor-svg">
        {/* Motor body */}
        <rect x="15" y="20" width="50" height="40" rx="4" fill="var(--bg-panel)"
          stroke={isFault ? 'var(--color-alarm)' : isRunning ? 'var(--color-accent)' : 'var(--border-default)'}
          strokeWidth="1.5" />

        {/* Cooling fins */}
        {[26, 32, 38, 44, 50, 56].map(y => (
          <line key={y} x1="15" y1={y} x2="10" y2={y}
            stroke="var(--border-default)" strokeWidth="1" />
        ))}

        {/* Shaft */}
        <line x1="65" y1="40" x2="78" y2="40"
          stroke={isRunning ? 'var(--color-accent)' : 'var(--text-muted)'}
          strokeWidth="3" strokeLinecap="round" />

        {/* Rotor indicator (rotating) */}
        <g style={{ transformOrigin: '40px 40px', animation: isRunning ? `motor-rotate ${Math.max(0.3, 60 / Math.max(speed, 1))}s linear infinite` : 'none' }}>
          <circle cx="40" cy="40" r="12" fill="none"
            stroke={isRunning ? 'var(--color-accent)' : 'var(--text-muted)'}
            strokeWidth="1" strokeDasharray="6,4" />
        </g>

        {/* Terminal box */}
        <rect x="25" y="14" width="20" height="8" rx="2" fill="var(--bg-surface)"
          stroke="var(--border-default)" strokeWidth="1" />

        {/* Status dot */}
        <circle cx="40" cy="65" r="3"
          fill={isFault ? 'var(--color-alarm)' : isRunning ? 'var(--color-healthy)' : 'var(--text-muted)'}
          opacity={isFault ? undefined : 1}>
          {isFault && <animate attributeName="opacity" values="1;0.3;1" dur="0.5s" repeatCount="indefinite" />}
        </circle>
      </svg>
    </div>
  );
}

function DriveCard({ section, tags, onClick }) {
  const prefix = section;
  const status = tags[`${prefix}_status`] || 'STOPPED';
  const speed = tags[`${prefix}_speed_actual`] || 0;
  const speedRef = tags[`${prefix}_speed_ref`] || 0;
  const torquePct = tags[`${prefix}_torque_pct`] || 0;
  const current = tags[`${prefix}_current`] || 0;
  const currentPct = tags[`${prefix}_current_pct`] || 0;
  const insulationHealth = tags[`${prefix}_insulation_health`] || 100;
  const bearingHealth = tags[`${prefix}_bearing_health`] || 100;
  const power = tags[`${prefix}_power`] || 0;

  const statusClass = status.toLowerCase();
  const torqueBarClass = torquePct > 90 ? 'danger' : torquePct > 70 ? 'warning' : 'normal';

  return (
    <div className={`drive-card ${statusClass}`} onClick={onClick}>
      <div className="drive-card-header">
        <span className="drive-card-section">{SECTION_LABELS[section]}</span>
        <span className={`status-pill ${statusClass}`}>
          <span className="status-dot"></span>
          {status}
        </span>
      </div>

      <MotorGraphic status={status} speed={speed} />

      <div className="drive-card-speed">
        <span className="value-label">Speed</span>
        <div className="drive-card-speed-row">
          <span className="value-number">{speed.toFixed(0)}</span>
          <span className="value-unit">RPM</span>
        </div>
        {speedRef > 0 && (
          <span className="drive-card-setpoint">SP: {speedRef.toFixed(0)} RPM</span>
        )}
      </div>

      <div className="drive-card-metrics">
        <div className="drive-card-metric">
          <span className="value-label">Torque</span>
          <div className="h-gauge">
            <div className="h-gauge-bar">
              <div className={`h-gauge-fill ${torqueBarClass}`}
                style={{ width: `${Math.min(torquePct, 100)}%`, background: torquePct > 90 ? 'var(--color-alarm)' : torquePct > 70 ? 'var(--color-warning)' : 'var(--color-accent)' }}>
              </div>
            </div>
            <span className="h-gauge-value">{torquePct.toFixed(0)}%</span>
          </div>
        </div>

        <div className="drive-card-metric">
          <span className="value-label">Current</span>
          <div className="drive-card-metric-row">
            <span className="drive-card-metric-value">{current.toFixed(1)}</span>
            <span className="drive-card-metric-unit">A</span>
            <span className="drive-card-metric-pct">({currentPct.toFixed(0)}%)</span>
          </div>
        </div>

        <div className="drive-card-metric">
          <span className="value-label">Power</span>
          <div className="drive-card-metric-row">
            <span className="drive-card-metric-value">{power.toFixed(1)}</span>
            <span className="drive-card-metric-unit">kW</span>
          </div>
        </div>
      </div>

      <div className="drive-card-health">
        <div className="drive-card-health-item">
          <svg viewBox="0 0 36 36" className="health-ring">
            <circle cx="18" cy="18" r="15" fill="none" stroke="var(--bg-input)" strokeWidth="3" />
            <circle cx="18" cy="18" r="15" fill="none"
              stroke={insulationHealth > 60 ? 'var(--color-healthy)' : insulationHealth > 30 ? 'var(--color-warning)' : 'var(--color-alarm)'}
              strokeWidth="3" strokeDasharray={`${insulationHealth * 0.942} 94.2`}
              strokeLinecap="round" transform="rotate(-90 18 18)" />
          </svg>
          <div className="health-ring-label">
            <span className="health-ring-value">{insulationHealth.toFixed(0)}%</span>
            <span className="health-ring-name">Insul</span>
          </div>
        </div>
        <div className="drive-card-health-item">
          <svg viewBox="0 0 36 36" className="health-ring">
            <circle cx="18" cy="18" r="15" fill="none" stroke="var(--bg-input)" strokeWidth="3" />
            <circle cx="18" cy="18" r="15" fill="none"
              stroke={bearingHealth > 60 ? 'var(--color-healthy)' : bearingHealth > 30 ? 'var(--color-warning)' : 'var(--color-alarm)'}
              strokeWidth="3" strokeDasharray={`${bearingHealth * 0.942} 94.2`}
              strokeLinecap="round" transform="rotate(-90 18 18)" />
          </svg>
          <div className="health-ring-label">
            <span className="health-ring-value">{bearingHealth.toFixed(0)}%</span>
            <span className="health-ring-name">Brg</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ConfirmDialog({ open, title, message, onConfirm, onCancel, variant = 'primary' }) {
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <h3 className="modal-title">{title}</h3>
        <p className="modal-body">{message}</p>
        <div className="modal-actions">
          <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button className={`btn btn-${variant}`} onClick={onConfirm}>Confirm</button>
        </div>
      </div>
    </div>
  );
}

export default function SystemOverview() {
  const { tags, sendCommand } = useWebSocket();
  const navigate = useNavigate();
  const [confirmAction, setConfirmAction] = useState(null);

  const anyRunning = SECTIONS.some(s => tags[`${s}_status`] === 'RUNNING');
  const anyFault = SECTIONS.some(s => tags[`${s}_status`] === 'FAULT');

  const totalPower = tags.total_power_kw || SECTIONS.reduce((s, sec) => s + (tags[`${sec}_power`] || 0), 0);
  const totalEnergy = tags.total_energy_kwh || 0;
  const pf = tags.system_power_factor || 0.85;

  const handleStartAll = () => {
    setConfirmAction({
      title: 'Start All Sections',
      message: 'This will start all three conveyor sections in sequence. Section 1 starts first, followed by Section 2 and Section 3 after speed confirmation. Ensure all permissives are satisfied.',
      variant: 'success',
      onConfirm: () => { sendCommand('start_all'); setConfirmAction(null); }
    });
  };

  const handleStopAll = () => {
    setConfirmAction({
      title: 'Stop All Sections',
      message: 'This will ramp all three sections to zero speed using the programmed deceleration curve and apply mechanical brakes at standstill.',
      variant: 'danger',
      onConfirm: () => { sendCommand('stop_all'); setConfirmAction(null); }
    });
  };

  return (
    <div className="overview-screen">
      <div className="screen-header">
        <h1 className="screen-title">System Overview</h1>
        <div className="screen-actions">
          <button className="btn btn-success" onClick={handleStartAll} disabled={anyRunning}>
            <Play size={14} /> Start All
          </button>
          <button className="btn btn-danger" onClick={handleStopAll}>
            <Square size={14} /> Stop All
          </button>
        </div>
      </div>

      {/* Energy panel */}
      <div className="overview-energy-panel">
        <div className="energy-item">
          <Zap size={14} className="energy-icon" />
          <span className="value-label">Total Power</span>
          <span className="value-number small">{totalPower.toFixed(1)}<span className="value-unit">kW</span></span>
        </div>
        <div className="energy-divider"></div>
        <div className="energy-item">
          <span className="value-label">Shift Energy</span>
          <span className="value-number small">{totalEnergy.toFixed(1)}<span className="value-unit">kWh</span></span>
        </div>
        <div className="energy-divider"></div>
        <div className="energy-item">
          <span className="value-label">Power Factor</span>
          <span className="value-number small">{pf.toFixed(2)}</span>
        </div>
      </div>

      {/* Conveyor belt animation */}
      <ConveyorBelt tags={tags} />

      {/* Drive cards */}
      <div className="overview-cards">
        {SECTIONS.map(s => (
          <DriveCard key={s} section={s} tags={tags}
            onClick={() => navigate(`/drive/${s}`)} />
        ))}
      </div>

      <ConfirmDialog
        open={!!confirmAction}
        title={confirmAction?.title}
        message={confirmAction?.message}
        variant={confirmAction?.variant}
        onConfirm={confirmAction?.onConfirm}
        onCancel={() => setConfirmAction(null)}
      />
    </div>
  );
}
