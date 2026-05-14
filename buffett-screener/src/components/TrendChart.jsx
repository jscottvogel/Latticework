import React, { useState, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const COLORS = ['#1A6B3C', '#ff9800', '#2196f3', '#9c27b0', '#e91e63', '#00bcd4', '#4caf50', '#ffeb3b', '#795548', '#607d8b'];

export default function TrendChart({ historyData }) {
  const [hiddenLines, setHiddenLines] = useState({});

  // historyData expected format:
  // [
  //   { week: '2023-W40', AAPL: 8.5, MSFT: 7.2, ... },
  //   { week: '2023-W41', AAPL: 8.6, MSFT: 7.1, ... }
  // ]

  const tickers = useMemo(() => {
    if (!historyData || historyData.length === 0) return [];
    const keys = new Set();
    historyData.forEach(d => {
      Object.keys(d).forEach(k => {
        if (k !== 'week') keys.add(k);
      });
    });
    return Array.from(keys);
  }, [historyData]);

  const toggleLine = (ticker) => {
    setHiddenLines(prev => ({
      ...prev,
      [ticker]: !prev[ticker]
    }));
  };

  if (!historyData || historyData.length === 0) {
    return <div className="empty-state">No historical data available for chart.</div>;
  }

  return (
    <div className="chart-wrapper" style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', marginBottom: '2rem' }}>
      <h2 style={{ color: '#1A6B3C', marginTop: 0 }}>Top 10 Score Trends (Last 4 Weeks)</h2>
      
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '1rem' }}>
        {tickers.map((ticker, idx) => (
          <label key={ticker} style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', fontSize: '0.85rem' }}>
            <input 
              type="checkbox" 
              checked={!hiddenLines[ticker]} 
              onChange={() => toggleLine(ticker)}
            />
            <span style={{ color: COLORS[idx % COLORS.length], fontWeight: 'bold' }}>{ticker}</span>
          </label>
        ))}
      </div>

      <div style={{ height: '400px', width: '100%' }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={historyData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="week" />
            <YAxis domain={[0, 10]} />
            <Tooltip contentStyle={{ borderRadius: '8px', border: '1px solid #ccc' }} />
            {tickers.map((ticker, idx) => (
              !hiddenLines[ticker] && (
                <Line 
                  key={ticker}
                  type="monotone" 
                  dataKey={ticker} 
                  stroke={COLORS[idx % COLORS.length]} 
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  activeDot={{ r: 6 }}
                />
              )
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
