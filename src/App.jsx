import { useState, useEffect } from 'react';
import { Routes, Route, NavLink, useNavigate, Navigate } from 'react-router-dom';
import { WebSocketProvider, useWebSocket } from './contexts/WebSocketContext';
import { AlarmProvider, useAlarms } from './contexts/AlarmContext';
import {
  LayoutDashboard, Gauge, HeartPulse, Bell, TrendingUp,
  FlaskConical, Settings, ChevronRight
} from 'lucide-react';

import SystemOverview from './screens/SystemOverview';
import DriveDetail from './screens/DriveDetail';
import MotorHealth from './screens/MotorHealth';
import AlarmConsole from './screens/AlarmConsole';
import Historian from './screens/Historian';
import TestConsole from './screens/TestConsole';
import Configuration from './screens/Configuration';

const NAV_ITEMS = [
  { path: '/', icon: LayoutDashboard, label: 'System Overview' },
  { path: '/drive/S1', icon: Gauge, label: 'Drive Detail' },
  { path: '/health', icon: HeartPulse, label: 'Motor Health' },
  { path: '/alarms', icon: Bell, label: 'Alarm Console' },
  { path: '/historian', icon: TrendingUp, label: 'Historian' },
  { path: '/tests', icon: FlaskConical, label: 'Test Console' },
  { path: '/config', icon: Settings, label: 'Configuration' },
];

function AppShell() {
  const { connected, reconnecting } = useWebSocket();
  const { latestUnacked, unackedCount } = useAlarms();
  const [clock, setClock] = useState(new Date());
  const navigate = useNavigate();

  useEffect(() => {
    const timer = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const formatTime = (d) => d.toLocaleTimeString('en-GB', { hour12: false });
  const formatDate = (d) => d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

  return (
    <div className="app-layout">
      {/* === TOP BAR === */}
      <header className="topbar">
        <div className="topbar-left">
          <div className="topbar-brand">
            <span className="topbar-brand-dot"></span>
            <span className="topbar-brand-name">DRIVEWISE</span>
          </div>
          <div className="topbar-separator"></div>
          <span className="topbar-subtitle">Multi-Drive Simulation Platform</span>
        </div>
        <div className="topbar-right">
          <div className="topbar-info">
            <span className="topbar-info-label">Operator</span>
            <span className="topbar-info-value">ENGINEER</span>
          </div>
          <div className="topbar-info">
            <span className="topbar-info-label">Date</span>
            <span className="topbar-info-value">{formatDate(clock)}</span>
          </div>
          <div className="topbar-info">
            <span className="topbar-info-label">Time</span>
            <span className="topbar-info-value">{formatTime(clock)}</span>
          </div>
          <div className={`topbar-connection ${connected ? 'connected' : 'disconnected'}`}>
            <span className="topbar-connection-dot"></span>
            <span>{connected ? 'Online' : reconnecting ? 'Reconnecting' : 'Offline'}</span>
          </div>
        </div>
      </header>

      {/* === SIDEBAR === */}
      <nav className="sidebar">
        {NAV_ITEMS.map(item => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) => `sidebar-nav-item ${isActive ? 'active' : ''}`}
          >
            <item.icon size={20} strokeWidth={1.5} />
            <span className="sidebar-tooltip">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* === CONTENT === */}
      <main className="content-area">
        <Routes>
          <Route path="/" element={<SystemOverview />} />
          <Route path="/drive/:sectionId" element={<DriveDetail />} />
          <Route path="/health" element={<MotorHealth />} />
          <Route path="/alarms" element={<AlarmConsole />} />
          <Route path="/historian" element={<Historian />} />
          <Route path="/tests" element={<TestConsole />} />
          <Route path="/config" element={<Configuration />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      {/* === ALARM BANNER === */}
      <div
        className={`alarm-banner ${unackedCount > 0 ? 'has-alarms' : ''}`}
        onClick={() => navigate('/alarms')}
      >
        {latestUnacked ? (
          <>
            <div className="alarm-banner-left">
              <div className={`alarm-banner-priority ${latestUnacked.priority}`}></div>
              <div className="alarm-banner-text">
                <span className="alarm-banner-tag">
                  {latestUnacked.section} — {latestUnacked.tag}
                  {latestUnacked.firstOut && ' [FIRST OUT]'}
                </span>
                <span className="alarm-banner-desc">{latestUnacked.description}</span>
              </div>
              <span className="alarm-banner-time">
                {new Date(latestUnacked.timestamp).toLocaleTimeString('en-GB', { hour12: false })}
              </span>
            </div>
            <div className="alarm-banner-right">
              <span className="alarm-banner-count">{unackedCount}</span>
              <ChevronRight size={16} color="var(--text-muted)" />
            </div>
          </>
        ) : (
          <div className="alarm-banner-no-alarms">
            <Bell size={14} />
            <span>No active alarms — System normal</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <WebSocketProvider>
      <AlarmProvider>
        <AppShell />
      </AlarmProvider>
    </WebSocketProvider>
  );
}
