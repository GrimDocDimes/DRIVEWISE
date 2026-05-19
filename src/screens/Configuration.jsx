import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import { Settings, Save, RotateCcw, Sliders, Zap } from 'lucide-react';
import './Configuration.css';

const DEFAULT_MOTOR = { ratedPower: 75, ratedVoltage: 415, ratedCurrent: 135, ratedSpeed: 1475, poles: 4, powerFactor: 0.86 };
const FAULT_TYPES = ['Overcurrent', 'Overvoltage', 'Undervoltage', 'Earth Fault', 'Thermal Overload', 'Belt Slip'];

export default function Configuration() {
  const { sendCommand, tags } = useWebSocket();
  const [motor, setMotor] = useState(DEFAULT_MOTOR);
  const [simSpeed, setSimSpeed] = useState(tags.sim_speed_multiplier || 1);
  const [loadProfile, setLoadProfile] = useState([20, 40, 70, 90, 100, 80, 60, 40, 30, 50, 80, 100]);
  const [faultSchedule, setFaultSchedule] = useState([]);
  const [saved, setSaved] = useState(false);

  // Live-apply sim speed on slider change
  const handleSimSpeedChange = useCallback((value) => {
    const v = parseInt(value);
    setSimSpeed(v);
    sendCommand('configure', { simSpeed: v });
  }, [sendCommand]);

  // Live-apply load profile on bar change
  const handleLoadChange = useCallback((index, value) => {
    setLoadProfile(prev => {
      const np = [...prev];
      np[index] = parseInt(value);
      sendCommand('configure', { loadProfile: np });
      return np;
    });
  }, [sendCommand]);

  const handleMotorChange = (field, value) => {
    setMotor(prev => ({ ...prev, [field]: parseFloat(value) || 0 }));
    setSaved(false);
  };

  const handleSave = () => {
    sendCommand('configure', { motor, simSpeed, loadProfile, faultSchedule });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleReset = () => {
    setMotor(DEFAULT_MOTOR);
    setSimSpeed(1);
    setLoadProfile([20, 40, 70, 90, 100, 80, 60, 40, 30, 50, 80, 100]);
    setFaultSchedule([]);
    sendCommand('configure', {
      simSpeed: 1,
      loadProfile: [20, 40, 70, 90, 100, 80, 60, 40, 30, 50, 80, 100],
      faultSchedule: [],
    });
  };

  const addFault = () => {
    setFaultSchedule(prev => [...prev, { type: 'Overcurrent', time: 30, section: 'S1' }]);
  };

  const removeFault = (idx) => {
    setFaultSchedule(prev => prev.filter((_, i) => i !== idx));
  };

  const updateFault = (idx, field, value) => {
    setFaultSchedule(prev => prev.map((f, i) => i === idx ? { ...f, [field]: value } : f));
  };

  return (
    <div className="config-screen">
      <div className="screen-header">
        <h1 className="screen-title"><Settings size={20} style={{ marginRight: 8 }} />Configuration</h1>
        <div className="screen-actions">
          <button className="btn btn-ghost btn-sm" onClick={handleReset}><RotateCcw size={14} /> Reset</button>
          <button className={`btn ${saved ? 'btn-success' : 'btn-primary'} btn-sm`} onClick={handleSave}>
            <Save size={14} /> {saved ? 'Saved!' : 'Apply All'}
          </button>
        </div>
      </div>

      <div className="config-layout">
        {/* Motor Nameplate */}
        <div className="config-section card">
          <div className="card-header"><span className="card-title">Motor Nameplate Data</span></div>
          <div className="config-form">
            {[
              { key: 'ratedPower', label: 'Rated Power', unit: 'kW' },
              { key: 'ratedVoltage', label: 'Rated Voltage', unit: 'V' },
              { key: 'ratedCurrent', label: 'Rated Current', unit: 'A' },
              { key: 'ratedSpeed', label: 'Rated Speed', unit: 'RPM' },
              { key: 'poles', label: 'Poles', unit: '' },
              { key: 'powerFactor', label: 'Power Factor', unit: '' },
            ].map(field => (
              <div key={field.key} className="config-field">
                <label className="config-label">{field.label}</label>
                <div className="config-input-group">
                  <input type="number" className="config-input" value={motor[field.key]}
                    onChange={e => handleMotorChange(field.key, e.target.value)} step={field.key === 'powerFactor' ? 0.01 : 1} />
                  {field.unit && <span className="config-unit">{field.unit}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Load Profile — Live apply */}
        <div className="config-section card">
          <div className="card-header">
            <span className="card-title">Load Profile</span>
            <span className="card-subtitle">Material load over time — changes apply live</span>
          </div>
          <div className="load-profile-chart">
            <div className="load-profile-bars">
              {loadProfile.map((val, i) => (
                <div key={i} className="load-bar-col">
                  <div className="load-bar-track">
                    <div className="load-bar-fill" style={{ height: `${val}%`, background: val > 80 ? 'var(--color-warning)' : 'var(--color-accent)' }}></div>
                  </div>
                  <input type="range" min="0" max="100" value={val} className="load-bar-slider"
                    onChange={e => handleLoadChange(i, e.target.value)} />
                  <span className="load-bar-label">{val}%</span>
                </div>
              ))}
            </div>
            <div className="load-profile-time">
              {loadProfile.map((_, i) => <span key={i} className="load-time-label">{i * 5}m</span>)}
            </div>
          </div>
        </div>

        {/* Simulation Speed — Live apply */}
        <div className="config-section card">
          <div className="card-header">
            <span className="card-title"><Sliders size={14} style={{ marginRight: 6 }} />Simulation Speed</span>
            <span className="card-subtitle">Changes apply instantly</span>
          </div>
          <div className="sim-speed-control">
            <input type="range" min="1" max="60" value={simSpeed} className="sim-speed-slider"
              onChange={e => handleSimSpeedChange(e.target.value)} />
            <div className="sim-speed-display">
              <span className="value-number">{simSpeed}</span>
              <span className="value-unit">×</span>
            </div>
            <span className="sim-speed-desc">
              {simSpeed === 1 ? 'Real time' : `1 real second = ${simSpeed} simulated seconds`}
            </span>
          </div>
        </div>

        {/* Fault Injection */}
        <div className="config-section card">
          <div className="card-header">
            <span className="card-title"><Zap size={14} style={{ marginRight: 6 }} />Fault Injection Schedule</span>
            <button className="btn btn-ghost btn-sm" onClick={addFault}>+ Add Fault</button>
          </div>
          <div className="fault-schedule">
            {faultSchedule.length === 0 ? (
              <p className="fault-empty">No scheduled faults. Click "+ Add Fault" to configure fault injection.</p>
            ) : (
              faultSchedule.map((fault, i) => (
                <div key={i} className="fault-item">
                  <select className="config-input" value={fault.type} onChange={e => updateFault(i, 'type', e.target.value)}>
                    {FAULT_TYPES.map(ft => <option key={ft} value={ft}>{ft}</option>)}
                  </select>
                  <select className="config-input" value={fault.section} onChange={e => updateFault(i, 'section', e.target.value)}>
                    <option value="S1">S1</option><option value="S2">S2</option><option value="S3">S3</option>
                  </select>
                  <div className="config-input-group">
                    <input type="number" className="config-input" value={fault.time} min="0"
                      onChange={e => updateFault(i, 'time', parseInt(e.target.value))} />
                    <span className="config-unit">sec</span>
                  </div>
                  <button className="btn btn-danger btn-sm" onClick={() => removeFault(i)}>×</button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
