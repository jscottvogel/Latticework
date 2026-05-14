import React from 'react';
import './Header.css';

export default function Header({ lastUpdated, runCost, onRunNow, isTriggering }) {
  return (
    <header className="app-header">
      <div className="header-content">
        <h1>Buffett Screener</h1>
        <div className="header-stats">
          <span className="stat">Last Updated: {lastUpdated || 'Loading...'}</span>
          <span className="stat">Run Cost: ${runCost ? runCost.toFixed(2) : '0.00'}</span>
          <button 
            className="run-now-btn" 
            onClick={onRunNow} 
            disabled={isTriggering}
          >
            {isTriggering ? 'Triggering...' : 'Run Now'}
          </button>
        </div>
      </div>
    </header>
  );
}
