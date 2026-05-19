import { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { useWebSocket } from './WebSocketContext';

const AlarmContext = createContext(null);

/*
  Alarm object shape:
  {
    id: string,
    priority: 'critical' | 'high' | 'warning' | 'low',
    section: 'S1' | 'S2' | 'S3' | 'SYSTEM',
    tag: string,
    description: string,
    value: number,
    threshold: number,
    timestamp: string (ISO),
    state: 'UNACKED_ACTIVE' | 'ACKED_ACTIVE' | 'ACKED_CLEARED' | 'CLEARED',
    firstOut: boolean,
    acknowledgedAt: string | null,
    clearedAt: string | null,
  }
*/

export function AlarmProvider({ children }) {
  const [alarms, setAlarms] = useState([]);
  const { tags } = useWebSocket();

  // Process alarm updates from the backend
  useEffect(() => {
    if (tags._alarm_updates) {
      setAlarms(prev => {
        let updated = [...prev];
        const updates = Array.isArray(tags._alarm_updates) ? tags._alarm_updates : [tags._alarm_updates];

        updates.forEach(alarm => {
          const existingIdx = updated.findIndex(a => a.id === alarm.id);
          if (existingIdx >= 0) {
            updated[existingIdx] = { ...updated[existingIdx], ...alarm };
          } else {
            updated.unshift(alarm);
          }
        });

        // Keep last 500 alarms max
        return updated.slice(0, 500);
      });
    }
  }, [tags._alarm_updates]);

  const activeAlarms = alarms.filter(a =>
    a.state === 'UNACKED_ACTIVE' || a.state === 'ACKED_ACTIVE'
  );

  const unacknowledgedAlarms = alarms.filter(a =>
    a.state === 'UNACKED_ACTIVE'
  );

  const latestUnacked = unacknowledgedAlarms[0] || null;

  const acknowledgeAlarm = useCallback((alarmId) => {
    setAlarms(prev => prev.map(a =>
      a.id === alarmId
        ? { ...a, state: a.state === 'UNACKED_ACTIVE' ? 'ACKED_ACTIVE' : a.state, acknowledgedAt: new Date().toISOString() }
        : a
    ));
  }, []);

  const acknowledgeAll = useCallback(() => {
    setAlarms(prev => prev.map(a =>
      a.state === 'UNACKED_ACTIVE'
        ? { ...a, state: 'ACKED_ACTIVE', acknowledgedAt: new Date().toISOString() }
        : a
    ));
  }, []);

  const alarmsBySection = activeAlarms.reduce((acc, a) => {
    acc[a.section] = (acc[a.section] || 0) + 1;
    return acc;
  }, {});

  const alarmsByCategory = activeAlarms.reduce((acc, a) => {
    const cat = a.tag?.split('_').pop() || 'other';
    acc[cat] = (acc[cat] || 0) + 1;
    return acc;
  }, {});

  // Standing alarms (active > 24 hours)
  const standingAlarms = activeAlarms.filter(a => {
    const age = Date.now() - new Date(a.timestamp).getTime();
    return age > 24 * 60 * 60 * 1000;
  });

  // Alarm flood detection (>10 in 10 minutes)
  const recentAlarms = alarms.filter(a => {
    const age = Date.now() - new Date(a.timestamp).getTime();
    return age < 10 * 60 * 1000;
  });
  const isAlarmFlood = recentAlarms.length > 10;

  return (
    <AlarmContext.Provider value={{
      alarms,
      activeAlarms,
      unacknowledgedAlarms,
      latestUnacked,
      acknowledgeAlarm,
      acknowledgeAll,
      alarmsBySection,
      alarmsByCategory,
      standingAlarms,
      isAlarmFlood,
      unackedCount: unacknowledgedAlarms.length,
    }}>
      {children}
    </AlarmContext.Provider>
  );
}

export function useAlarms() {
  const ctx = useContext(AlarmContext);
  if (!ctx) throw new Error('useAlarms must be used within AlarmProvider');
  return ctx;
}
