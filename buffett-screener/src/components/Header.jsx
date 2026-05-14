import './Header.css';

export default function Header({ lastUpdated, runCost }) {
  return (
    <header className="app-header">
      <div className="header-content">
        <h1>Buffett Screener</h1>
        <div className="header-stats">
          <span className="stat">Last Updated: {lastUpdated || 'Loading...'}</span>
          <span className="stat">Run Cost: ${runCost ? runCost.toFixed(2) : '0.00'}</span>
          {/* Button hidden, can be triggered via console using runBuffettPipeline() */}
        </div>
      </div>
    </header>
  );
}
