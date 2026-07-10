import { useState, useRef, useEffect, useMemo } from 'react';
import ReactEChartsCore from 'echarts-for-react';
import { Brain, Send, Terminal, AlertCircle, RefreshCw, BarChart2 } from 'lucide-react';
import './InsightAgent.css';

const QUICK_QUESTIONS = [
  "Which drive had the most overcurrent trips this week?",
  "Show S2's winding temperature trend during the last thermal alarm",
  "How many hours of downtime did each unit have in the last 3 days?",
  "Is S2's bearing health degrading faster than S1's?",
  "Show me the peak torque values for all drives during the last 8 hours"
];

export default function InsightAgent() {
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'agent',
      text: "Welcome to DRIVEWISE InsightAgent. Ask any natural language question about VFD telemetry, alarm logs, asset health profiles, or FAT execution records to query the SQL historian database.",
      timestamp: new Date().toLocaleTimeString('en-GB', { hour12: false })
    }
  ]);
  const [queryInput, setQueryInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedResult, setSelectedResult] = useState(null);
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (questionText) => {
    const textToSend = questionText || queryInput;
    if (!textToSend.trim() || loading) return;

    if (!questionText) {
      setQueryInput('');
    }

    const userMsg = {
      id: Date.now().toString(),
      role: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString('en-GB', { hour12: false })
    };

    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const response = await fetch('http://localhost:8766/agent/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: textToSend })
      });

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const data = await response.json();
      
      const agentMsg = {
        id: (Date.now() + 1).toString(),
        role: 'agent',
        text: data.answer,
        timestamp: new Date().toLocaleTimeString('en-GB', { hour12: false }),
        sql: data.sql,
        chartType: data.chart_type,
        data: data.data
      };

      setMessages(prev => [...prev, agentMsg]);
      setSelectedResult(agentMsg);
    } catch (err) {
      console.error("Agent query failed:", err);
      const errorMsg = {
        id: (Date.now() + 1).toString(),
        role: 'error',
        text: `Unable to connect to the GenAI Agent on port 8766. Please verify that the agent service is running.\n\nError: ${err.message}`,
        timestamp: new Date().toLocaleTimeString('en-GB', { hour12: false })
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const chartOption = useMemo(() => {
    if (!selectedResult || !selectedResult.data || selectedResult.data.length === 0) return null;
    const records = selectedResult.data;
    const type = selectedResult.chartType;
    if (type === 'none') return null;

    // Detect columns
    const columns = Object.keys(records[0]);
    
    // Find x-axis candidate: timestamp, time, date, unit_id, alarm_code
    let xAxisCol = columns.find(c => c.toLowerCase().includes('timestamp') || c.toLowerCase().includes('time') || c.toLowerCase().includes('date'));
    if (!xAxisCol) {
      xAxisCol = columns.find(c => c.toLowerCase().includes('unit_id') || c.toLowerCase().includes('code') || c.toLowerCase().includes('name'));
    }
    if (!xAxisCol) {
      xAxisCol = columns[0];
    }

    // Y-Axis/numeric series candidates
    const seriesCols = columns.filter(c => c !== xAxisCol && typeof records[0][c] === 'number');
    if (seriesCols.length === 0) return null;

    // Format xAxis categories / timestamps
    const xData = records.map(r => {
      const val = r[xAxisCol];
      if (typeof val === 'string' && val.includes('T')) {
        // Pretty print ISO timestamp
        return new Date(val).toLocaleTimeString('en-GB', { hour12: false });
      }
      return String(val);
    });

    const series = seriesCols.map(col => ({
      name: col.replace(/_/g, ' ').toUpperCase(),
      type: type === 'line' ? 'line' : 'bar',
      smooth: true,
      data: records.map(r => r[col]),
      barMaxWidth: '30%',
      itemStyle: {
        borderRadius: type === 'bar' ? [4, 4, 0, 0] : [0, 0, 0, 0]
      }
    }));

    return {
      backgroundColor: 'transparent',
      grid: { top: 40, right: 30, bottom: 50, left: 55 },
      tooltip: { 
        trigger: 'axis', 
        backgroundColor: '#16213E', 
        borderColor: 'rgba(255,255,255,0.1)',
        textStyle: { color: '#E0E0E0', fontSize: 11, fontFamily: 'JetBrains Mono' }
      },
      legend: { 
        top: 0, 
        textStyle: { color: '#8B8BA3', fontSize: 10, fontFamily: 'JetBrains Mono' } 
      },
      xAxis: {
        type: 'category',
        data: xData,
        axisLabel: { color: '#8B8BA3', fontSize: 9, fontFamily: 'JetBrains Mono' },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#8B8BA3', fontSize: 9 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }
      },
      series
    };
  }, [selectedResult]);

  return (
    <div className="agent-screen">
      <div className="screen-header">
        <h1 className="screen-title">
          <Brain size={20} style={{ marginRight: 8, color: 'var(--color-accent)' }} />
          GenAI Insight Agent
        </h1>
      </div>

      <div className="agent-layout">
        {/* Left Column: Chat History */}
        <div className="agent-chat-card card">
          <div className="chat-history">
            {messages.map(m => (
              <div key={m.id} className={`chat-bubble ${m.role}`} onClick={() => m.data && setSelectedResult(m)}>
                <div className="chat-bubble-header">
                  <span>{m.role === 'user' ? 'Operator' : 'Agent'}</span>
                  <span>{m.timestamp}</span>
                </div>
                <div className="chat-bubble-body">{m.text}</div>
              </div>
            ))}
            {loading && (
              <div className="agent-loading">
                <div className="loading-spinner"></div>
                <span>Claude is compiling and running your query...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="quick-questions">
            {QUICK_QUESTIONS.map((q, idx) => (
              <button
                key={idx}
                className="question-chip"
                onClick={() => handleSend(q)}
                disabled={loading}
              >
                {q.length > 50 ? `${q.substring(0, 47)}...` : q}
              </button>
            ))}
          </div>

          <div className="chat-input-area">
            <input
              type="text"
              className="chat-input"
              placeholder="Ask an asset data question..."
              value={queryInput}
              onChange={e => setQueryInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              disabled={loading}
            />
            <button
              className="chat-send-btn"
              onClick={() => handleSend()}
              disabled={!queryInput.trim() || loading}
            >
              <Send size={14} />
            </button>
          </div>
        </div>

        {/* Right Column: Insights & Visualizations Canvas */}
        <div className="agent-canvas">
          {selectedResult && selectedResult.data ? (
            <div className="insight-results-card card">
              <div className="card-header">
                <span className="card-title">Query Results</span>
                <span className="card-subtitle">
                  {selectedResult.data.length} records returned
                </span>
              </div>

              {selectedResult.chartType !== 'none' && chartOption && (
                <div className="chart-container">
                  <ReactEChartsCore option={chartOption} style={{ height: '100%', width: '100%' }} notMerge={true} />
                </div>
              )}

              {selectedResult.data.length > 0 ? (
                <div className="table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        {Object.keys(selectedResult.data[0]).map(col => (
                          <th key={col}>{col.replace(/_/g, ' ')}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {selectedResult.data.slice(0, 100).map((row, idx) => (
                        <tr key={idx}>
                          {Object.values(row).map((val, cellIdx) => {
                            if (typeof val === 'string' && val.includes('T')) {
                              // Standardise timestamp fields
                              return <td key={cellIdx}>{val.replace('T', ' ').substring(0, 19)}</td>;
                            }
                            return <td key={cellIdx}>{String(val)}</td>;
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-canvas">
                  <span>No data records returned for this query.</span>
                </div>
              )}

              {selectedResult.sql && (
                <details className="sql-panel">
                  <summary className="sql-summary">
                    <Terminal size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
                    Show Compiled SQL Query
                  </summary>
                  <div className="sql-content">
                    <code className="sql-code">{selectedResult.sql}</code>
                  </div>
                </details>
              )}
            </div>
          ) : (
            <div className="insight-results-card card">
              <div className="empty-canvas">
                <BarChart2 size={48} className="empty-canvas-icon" />
                <h3>No Query Selection</h3>
                <p>Submit a question or select an agent response to visualize the telemetry data and SQL query details here.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
