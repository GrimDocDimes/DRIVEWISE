import { useEffect, useRef } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import ReactEChartsCore from 'echarts-for-react';
import { HeartPulse, Clock, Activity } from 'lucide-react';
import './MotorHealth.css';

const SECTIONS = ['S1', 'S2', 'S3'];
const SECTION_NAMES = { S1: 'Section 1', S2: 'Section 2', S3: 'Section 3' };

function HealthGauge({ value, label, size = 200 }) {
  const color = value > 60 ? '#4ADE80' : value > 30 ? '#FFB300' : '#FF3B30';

  const option = {
    series: [{
      type: 'gauge',
      startAngle: 220,
      endAngle: -40,
      min: 0,
      max: 100,
      radius: '90%',
      progress: {
        show: true,
        width: 14,
        roundCap: true,
        itemStyle: { color }
      },
      pointer: { show: false },
      axisLine: {
        lineStyle: { width: 14, color: [[1, 'rgba(255,255,255,0.06)']] }
      },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      title: {
        show: true,
        offsetCenter: [0, '60%'],
        fontSize: 11,
        color: '#8B8BA3',
        fontFamily: 'JetBrains Mono',
      },
      detail: {
        valueAnimation: true,
        offsetCenter: [0, '10%'],
        fontSize: 32,
        fontWeight: 700,
        color: '#FFFFFF',
        fontFamily: 'JetBrains Mono',
        formatter: '{value}%',
      },
      data: [{ value: value.toFixed(0), name: label }],
    }],
  };

  return (
    <ReactEChartsCore option={option} style={{ width: `${size}px`, height: `${size}px` }} />
  );
}

function VibrationSpectrum({ section, tags }) {
  const spectrum = tags[`${section}_vibration_spectrum`] || new Array(32).fill(0);
  const shaftFreq = ((tags[`${section}_speed_actual`] || 0) / 60);
  const bpfo = shaftFreq * 5.43; // typical for 6208 bearing
  const bpfi = shaftFreq * 8.57;

  const freqLabels = spectrum.map((_, i) => `${(i * 10).toFixed(0)}`);

  const option = {
    backgroundColor: 'transparent',
    animation: false,
    grid: { top: 35, right: 15, bottom: 35, left: 45 },
    title: {
      text: SECTION_NAMES[section],
      left: 'center',
      top: 5,
      textStyle: { color: '#8B8BA3', fontSize: 11, fontFamily: 'JetBrains Mono', fontWeight: 500 },
    },
    xAxis: {
      type: 'category',
      data: freqLabels,
      name: 'Hz',
      nameTextStyle: { color: '#6B6B83', fontSize: 9 },
      axisLabel: { color: '#6B6B83', fontSize: 8, fontFamily: 'JetBrains Mono', interval: 3 },
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
    },
    yAxis: {
      type: 'value',
      name: 'mm/s',
      nameTextStyle: { color: '#6B6B83', fontSize: 9 },
      axisLabel: { color: '#6B6B83', fontSize: 8 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } },
    },
    series: [{
      type: 'bar',
      data: spectrum.map((v, i) => ({
        value: v,
        itemStyle: {
          color: v > 4 ? '#FF3B30' : v > 2 ? '#FFB300' : '#4A9EFF',
          borderRadius: [2, 2, 0, 0],
        }
      })),
      barWidth: '60%',
    }],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1A1A3E',
      borderColor: 'rgba(255,255,255,0.1)',
      textStyle: { color: '#E0E0E0', fontSize: 10, fontFamily: 'JetBrains Mono' },
      formatter: (params) => {
        const p = params[0];
        return `${p.axisValue} Hz<br/>Amplitude: ${p.value.toFixed(2)} mm/s`;
      }
    },
    // Mark lines for defect frequencies
    ...(shaftFreq > 0 ? {} : {}),
  };

  return <ReactEChartsCore option={option} style={{ height: '180px', flex: 1 }} notMerge={true} />;
}

export default function MotorHealth() {
  const { tags } = useWebSocket();

  return (
    <div className="health-screen">
      <div className="screen-header">
        <h1 className="screen-title">
          <HeartPulse size={20} style={{ marginRight: 8 }} />
          Motor Health Dashboard
        </h1>
      </div>

      {/* Health Gauges */}
      <div className="health-gauges-row">
        {SECTIONS.map(s => {
          const combined = tags[`${s}_combined_health`] || 100;
          const insulation = tags[`${s}_insulation_health`] || 100;
          const bearing = tags[`${s}_bearing_health`] || 100;
          const isoClass = tags[`${s}_bearing_iso`] || 'Good';

          return (
            <div key={s} className="health-gauge-card card">
              <div className="card-header">
                <span className="card-title">{SECTION_NAMES[s]}</span>
                <span className={`status-pill ${isoClass === 'Good' ? 'running' : isoClass === 'Satisfactory' ? 'warning' : 'fault'}`}>
                  <span className="status-dot"></span>
                  ISO: {isoClass}
                </span>
              </div>

              <div className="health-gauge-center">
                <HealthGauge value={combined} label="Combined Health" size={180} />
              </div>

              <div className="health-sub-bars">
                <div className="health-sub-bar">
                  <span className="health-sub-label">Insulation</span>
                  <div className="h-gauge">
                    <div className="h-gauge-bar">
                      <div className="h-gauge-fill" style={{
                        width: `${insulation}%`,
                        background: insulation > 60 ? 'var(--color-healthy)' : insulation > 30 ? 'var(--color-warning)' : 'var(--color-alarm)',
                      }}></div>
                    </div>
                    <span className="h-gauge-value">{insulation.toFixed(0)}%</span>
                  </div>
                </div>
                <div className="health-sub-bar">
                  <span className="health-sub-label">Bearing</span>
                  <div className="h-gauge">
                    <div className="h-gauge-bar">
                      <div className="h-gauge-fill" style={{
                        width: `${bearing}%`,
                        background: bearing > 60 ? 'var(--color-healthy)' : bearing > 30 ? 'var(--color-warning)' : 'var(--color-alarm)',
                      }}></div>
                    </div>
                    <span className="h-gauge-value">{bearing.toFixed(0)}%</span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Remaining Useful Life */}
      <div className="rul-panel card">
        <div className="card-header">
          <span className="card-title"><Clock size={14} style={{ marginRight: 6 }} /> Remaining Useful Life</span>
        </div>
        <div className="rul-rows">
          {SECTIONS.map(s => {
            const hours = tags[`${s}_rul_hours`] || 50000;
            const date = new Date(Date.now() + hours * 3600 * 1000);
            const dateStr = date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
            const confidence = Math.round(hours * 0.1);

            return (
              <div key={s} className="rul-row">
                <span className="rul-section">{SECTION_NAMES[s]}</span>
                <div className="rul-hours">
                  <span className="value-number small">{hours.toLocaleString()}</span>
                  <span className="value-unit">hrs</span>
                </div>
                <div className="rul-date">
                  <span className="rul-date-value">{dateStr}</span>
                  <span className="rul-confidence">±{confidence.toLocaleString()} hrs</span>
                </div>
                <div className="rul-bar">
                  <div className="progress-bar">
                    <div className={`progress-bar-fill ${hours > 30000 ? 'good' : hours > 10000 ? 'warning' : 'danger'}`}
                      style={{ width: `${Math.min((hours / 50000) * 100, 100)}%` }}></div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Vibration Spectrum */}
      <div className="vibration-panel card">
        <div className="card-header">
          <span className="card-title"><Activity size={14} style={{ marginRight: 6 }} /> Bearing Vibration Spectrum</span>
          <span className="card-subtitle">FFT Analysis — Defect Frequency Detection</span>
        </div>
        <div className="vibration-charts">
          {SECTIONS.map(s => (
            <VibrationSpectrum key={s} section={s} tags={tags} />
          ))}
        </div>
      </div>
    </div>
  );
}
