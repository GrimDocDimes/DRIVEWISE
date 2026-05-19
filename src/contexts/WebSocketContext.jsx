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
      const ws = new WebSocket('ws://localhost:8765');
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        setReconnecting(false);
        reconnectAttemptRef.current = 0;
        console.log('[WS] Connected to simulation backend');
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
      console.error('[WS] Connection error:', e);
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

  const sendCommand = useCallback((type, payload = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...payload }));
    } else {
      console.warn('[WS] Cannot send command — not connected');
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
