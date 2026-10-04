import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';

const WebSocketContext = createContext(null);

// Default tag values for all 3 drive sections
const createDefaultTags = () => {
  const sections = ['S1', 'S2', 'S3'];
  const tags = {
    sim_running: false,
    sim_speed_multiplier: 1,
    sim_time: 0,
    total_power_kw: 0,
    total_energy_kwh: 0,
    system_power_factor: 0.85,
  };

  sections.forEach(s => {
    // Drive
    tags[`${s}_status`] = 'STOPPED';      // STOPPED, STARTING, RUNNING, FAULT
    tags[`${s}_control_mode`] = 'DTC';     // DTC, SCALAR
    tags[`${s}_speed_ref`] = 0;            // RPM setpoint
    tags[`${s}_speed_actual`] = 0;         // RPM actual
    tags[`${s}_speed_error`] = 0;          // RPM error
    tags[`${s}_torque`] = 0;               // Nm
    tags[`${s}_torque_pct`] = 0;           // % of rated
    tags[`${s}_current`] = 0;              // Amps
    tags[`${s}_current_pct`] = 0;          // % of rated
    tags[`${s}_voltage`] = 0;              // Volts
    tags[`${s}_frequency`] = 0;            // Hz
    tags[`${s}_dc_bus_voltage`] = 0;       // V DC bus
    tags[`${s}_power`] = 0;                // kW
    tags[`${s}_power_factor`] = 0;

    // Ramp
    tags[`${s}_ramp_accel`] = 10;          // seconds
    tags[`${s}_ramp_decel`] = 10;          // seconds
    tags[`${s}_ramp_estop`] = 2;           // seconds

    // Motor thermal
    tags[`${s}_winding_temp`] = 25;        // °C
    tags[`${s}_rotor_temp`] = 25;          // °C
    tags[`${s}_thermal_load_pct`] = 0;     // % of thermal limit

    // Conveyor
    tags[`${s}_belt_speed`] = 0;           // m/s
    tags[`${s}_material_load`] = 0;        // % of max
    tags[`${s}_belt_slip`] = false;

    // Health & predictive
    tags[`${s}_insulation_health`] = 100;  // %
    tags[`${s}_bearing_health`] = 100;     // %
    tags[`${s}_combined_health`] = 100;    // %
    tags[`${s}_rul_hours`] = 50000;        // remaining useful life hours
    tags[`${s}_bearing_iso`] = 'Good';     // ISO 10816 class
    tags[`${s}_bearing_defect_freq`] = 'None';

    // Protection status
    tags[`${s}_prot_overcurrent_value`] = 0;
    tags[`${s}_prot_overcurrent_threshold`] = 150;
    tags[`${s}_prot_overcurrent_trip`] = false;
    tags[`${s}_prot_overvoltage_value`] = 0;
    tags[`${s}_prot_overvoltage_threshold`] = 750;
    tags[`${s}_prot_overvoltage_trip`] = false;
    tags[`${s}_prot_undervoltage_value`] = 415;
    tags[`${s}_prot_undervoltage_threshold`] = 290;
    tags[`${s}_prot_undervoltage_trip`] = false;
    tags[`${s}_prot_earthfault_value`] = 0;
    tags[`${s}_prot_earthfault_threshold`] = 30;
    tags[`${s}_prot_earthfault_trip`] = false;
    tags[`${s}_prot_thermal_value`] = 0;
    tags[`${s}_prot_thermal_threshold`] = 155;
    tags[`${s}_prot_thermal_trip`] = false;

    // Vibration spectrum (simplified — 32 frequency bins)
    tags[`${s}_vibration_spectrum`] = new Array(32).fill(0);

    // Brake
    tags[`${s}_brake_released`] = false;
  });

  return tags;
};

const getWsUrl = () => {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL;
  const isHttps = window.location.protocol === 'https:';
  const host = window.location.hostname || 'localhost';
  return isHttps ? `wss://${host}:8765` : `ws://${host}:8765`;
};

// Fallback in-browser simulator step for offline/static deployment demo mode
const stepFallbackSimulation = (prevTags) => {
  const next = { ...prevTags };
  next.sim_time = (next.sim_time || 0) + 0.1;
  const sections = ['S1', 'S2', 'S3'];
  let totalPower = 0;

  sections.forEach((s) => {
    const statusKey = `${s}_status`;
    const speedRefKey = `${s}_speed_ref`;
    const speedActualKey = `${s}_speed_actual`;
    const torqueKey = `${s}_torque`;
    const torquePctKey = `${s}_torque_pct`;
    const currentKey = `${s}_current`;
    const currentPctKey = `${s}_current_pct`;
    const voltageKey = `${s}_voltage`;
    const freqKey = `${s}_frequency`;
    const dcBusKey = `${s}_dc_bus_voltage`;
    const powerKey = `${s}_power`;
    const windingTempKey = `${s}_winding_temp`;
    const rotorTempKey = `${s}_rotor_temp`;
    const beltSpeedKey = `${s}_belt_speed`;

    let status = next[statusKey] || 'STOPPED';
    let targetSpeed = status === 'RUNNING' || status === 'STARTING' ? (next[speedRefKey] || 1475) : 0;
    let actualSpeed = next[speedActualKey] || 0;

    // Ramp speed
    if (actualSpeed < targetSpeed) {
      actualSpeed = Math.min(targetSpeed, actualSpeed + 25);
      if (status === 'STARTING' && actualSpeed >= targetSpeed) next[statusKey] = 'RUNNING';
    } else if (actualSpeed > targetSpeed) {
      actualSpeed = Math.max(targetSpeed, actualSpeed - 35);
      if (actualSpeed === 0 && status !== 'FAULT') next[statusKey] = 'STOPPED';
    }

    next[speedActualKey] = actualSpeed;
    next[`${s}_speed_error`] = (next[speedRefKey] || 0) - actualSpeed;

    const noise = (Math.random() - 0.5) * 1.5;
    const speedFraction = actualSpeed / 1475.0;

    if (actualSpeed > 0) {
      const baseTorque = (450 + noise * 10);
      next[torqueKey] = Math.round(baseTorque * speedFraction * 10) / 10;
      next[torquePctKey] = Math.round((next[torqueKey] / 485.0) * 1000) / 10;
      next[currentKey] = Math.round((speedFraction * 120 + 10 + noise) * 10) / 10;
      next[currentPctKey] = Math.round((next[currentKey] / 135.0) * 1000) / 10;
      next[voltageKey] = Math.round(speedFraction * 415);
      next[freqKey] = Math.round(speedFraction * 50 * 10) / 10;
      next[dcBusKey] = Math.round(586 + noise * 2);
      const kw = Math.max(0, (next[torqueKey] * actualSpeed / 9549) * 1.1);
      next[powerKey] = Math.round(kw * 10) / 10;
      next[beltSpeedKey] = Math.round(speedFraction * 3.5 * 100) / 100;
      next[windingTempKey] = Math.min(115, Math.round(((next[windingTempKey] || 25) + 0.05) * 10) / 10);
      next[rotorTempKey] = Math.min(105, Math.round(((next[rotorTempKey] || 25) + 0.04) * 10) / 10);
      totalPower += next[powerKey];
    } else {
      next[torqueKey] = 0;
      next[torquePctKey] = 0;
      next[currentKey] = 0;
      next[currentPctKey] = 0;
      next[voltageKey] = 0;
      next[freqKey] = 0;
      next[dcBusKey] = 586;
      next[powerKey] = 0;
      next[beltSpeedKey] = 0;
      next[windingTempKey] = Math.max(25, Math.round(((next[windingTempKey] || 25) - 0.02) * 10) / 10);
      next[rotorTempKey] = Math.max(25, Math.round(((next[rotorTempKey] || 25) - 0.02) * 10) / 10);
    }

    // Health metrics
    next[`${s}_insulation_health`] = 98.5;
    next[`${s}_bearing_health`] = 99.1;
    next[`${s}_combined_health`] = 98.8;
    next[`${s}_rul_hours`] = 48200;
  });

  next.total_power_kw = Math.round(totalPower * 10) / 10;
  next.total_energy_kwh = Math.round(((next.total_energy_kwh || 0) + (totalPower * 0.1 / 3600)) * 1000) / 1000;
  return next;
};

export function WebSocketProvider({ children }) {
  const [tags, setTags] = useState(createDefaultTags);
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const reconnectAttemptRef = useRef(0);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const url = getWsUrl();
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setReconnecting(false);
        reconnectAttemptRef.current = 0;
        console.log('[WS] Connected to simulation backend at', url);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'tag_update') {
            setTags(prev => ({ ...prev, ...data.tags }));
          }
        } catch (e) {
          console.error('[WS] Parse error:', e);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        scheduleReconnect();
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch (e) {
        setConnected(false);
        scheduleReconnect();
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    setReconnecting(true);
    const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 10000);
    reconnectAttemptRef.current += 1;
    reconnectTimerRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]);

  // Fallback simulator loop when WS is offline
  useEffect(() => {
    if (connected) return;
    const interval = setInterval(() => {
      setTags(prev => stepFallbackSimulation(prev));
    }, 100);
    return () => clearInterval(interval);
  }, [connected]);

  const sendCommand = useCallback((type, payload = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...payload }));
    } else {
      // Execute command on local fallback simulator when offline
      setTags(prev => {
        const next = { ...prev };
        const sections = ['S1', 'S2', 'S3'];
        if (type === 'start_all') {
          sections.forEach(s => {
            next[`${s}_status`] = 'RUNNING';
            next[`${s}_speed_ref`] = 1475;
          });
        } else if (type === 'stop_all') {
          sections.forEach(s => {
            next[`${s}_status`] = 'STOPPED';
            next[`${s}_speed_ref`] = 0;
          });
        } else if (type === 'estop_all') {
          sections.forEach(s => {
            next[`${s}_status`] = 'STOPPED';
            next[`${s}_speed_ref`] = 0;
            next[`${s}_speed_actual`] = 0;
          });
        } else if (type === 'start_section') {
          const sec = payload.section || 'S1';
          next[`${sec}_status`] = 'RUNNING';
          next[`${sec}_speed_ref`] = 1475;
        } else if (type === 'stop_section') {
          const sec = payload.section || 'S1';
          next[`${sec}_status`] = 'STOPPED';
          next[`${sec}_speed_ref`] = 0;
        } else if (type === 'estop_section') {
          const sec = payload.section || 'S1';
          next[`${sec}_status`] = 'STOPPED';
          next[`${sec}_speed_ref`] = 0;
          next[`${sec}_speed_actual`] = 0;
        } else if (type === 'set_parameter') {
          const { section, parameter, value } = payload;
          if (section && parameter) {
            next[`${section}_${parameter}`] = value;
          }
        } else if (type === 'inject_fault') {
          const sec = payload.section || 'S1';
          next[`${sec}_status`] = 'FAULT';
          next[`${sec}_speed_ref`] = 0;
          next[`${sec}_speed_actual`] = 0;
        } else if (type === 'reset_fault') {
          const sec = payload.section || 'S1';
          if (next[`${sec}_status`] === 'FAULT') {
            next[`${sec}_status`] = 'STOPPED';
          }
        }
        return next;
      });
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return (
    <WebSocketContext.Provider value={{ tags, connected, reconnecting, sendCommand }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket() {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error('useWebSocket must be used within WebSocketProvider');
  return ctx;
}

export function useTag(tagName) {
  const { tags } = useWebSocket();
  return tags[tagName];
}

export function useSectionTags(section) {
  const { tags } = useWebSocket();
  const prefix = section + '_';
  const sectionTags = {};
  for (const key in tags) {
    if (key.startsWith(prefix)) {
      sectionTags[key.slice(prefix.length)] = tags[key];
    }
  }
  return sectionTags;
}
