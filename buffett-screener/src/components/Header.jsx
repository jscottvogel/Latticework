import './Header.css';

export default function Header({ lastUpdated, runCost, onRunNow, isTriggering }) {
  return (
    <header className="app-header">
      <div className="header-content">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <img src="/logo.png" alt="Value Screener Logo" style={{ width: '40px', height: '40px', borderRadius: '8px' }} />
          <h1>Value Screener</h1>
        </div>
        <div className="header-stats">
          <span className="stat">Last Updated: {lastUpdated || 'Loading...'}</span>
          <span className="stat">Run Cost: ${runCost ? runCost.toFixed(2) : '0.00'}</span>

        </div>
      </div>
    </header>
  );
}
