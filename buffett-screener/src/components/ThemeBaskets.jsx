import { useState, useEffect } from 'react';
import outputs from '../../amplify_outputs.json';
import './TableStyles.css';

export default function ThemeBaskets({ onPrioritize }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [basketsData, setBasketsData] = useState(null);
  const [selectedThemeId, setSelectedThemeId] = useState('');

  useEffect(() => {
    async function fetchBaskets() {
      const bucketName = outputs?.custom?.dataBucketName;
      if (!bucketName) {
        setError("S3 Bucket Name not found in configurations.");
        setLoading(false);
        return;
      }
      const url = `https://${bucketName}.s3.amazonaws.com/dashboard/theme_baskets.json`;
      try {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`Failed to fetch thematic baskets. Status: ${response.status}`);
        }
        const data = await response.json();
        setBasketsData(data);
        
        // Auto-select the first theme with stocks, or just the first theme
        const basketKeys = Object.keys(data.baskets || {});
        if (basketKeys.length > 0) {
          const firstWithStocks = basketKeys.find(key => data.baskets[key].stocks?.length > 0);
          setSelectedThemeId(firstWithStocks || basketKeys[0]);
        }
      } catch (err) {
        console.error("Error loading thematic baskets:", err);
        setError(err.message || "Failed to load thematic baskets.");
      } finally {
        setLoading(false);
      }
    }

    fetchBaskets();
  }, []);

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#666', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
        Loading thematic baskets from S3...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '2rem', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', color: '#d93025' }}>
        <h3 style={{ marginTop: 0 }}>Thematic Baskets Data Unavailable</h3>
        <p>{error}</p>
        <p style={{ fontSize: '0.85rem', color: '#666' }}>
          Please make sure the <code>ThemeBasketWorker</code> Lambda has run at least once to build baskets and export the dashboard JSON.
        </p>
      </div>
    );
  }

  const baskets = basketsData?.baskets || {};
  const themeIds = Object.keys(baskets);

  if (themeIds.length === 0) {
    return (
      <div style={{ padding: '2rem', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', color: '#666' }}>
        No themes registered in the system.
      </div>
    );
  }

  const activeBasket = baskets[selectedThemeId];
  const stocks = activeBasket?.stocks || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header and Theme Selector */}
      <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
        <h2 style={{ color: '#1A6B3C', margin: '0 0 1rem 0', fontSize: '1.5rem' }}>Thematic Investment Baskets</h2>
        <p style={{ fontSize: '0.9rem', color: '#666', marginBottom: '1.5rem', lineHeight: '1.4' }}>
          Stocks dynamically classified into theme-specific baskets based on keyword matches across company description, sector, and latest thesis.
        </p>

        {/* Horizontal Theme Tabs */}
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', borderBottom: '1px solid #eee', paddingBottom: '12px' }}>
          {themeIds.map(id => {
            const basket = baskets[id];
            const isActive = selectedThemeId === id;
            return (
              <button
                key={id}
                onClick={() => setSelectedThemeId(id)}
                style={{
                  padding: '10px 18px',
                  border: isActive ? '2px solid #1A6B3C' : '1px solid #ddd',
                  borderRadius: '6px',
                  backgroundColor: isActive ? '#f0faf4' : 'white',
                  color: isActive ? '#1A6B3C' : '#555',
                  fontWeight: 'bold',
                  cursor: 'pointer',
                  fontSize: '0.9rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  transition: 'all 0.15s ease-in-out',
                }}
              >
                {basket.name}
                <span style={{
                  backgroundColor: isActive ? '#1A6B3C' : '#888',
                  color: 'white',
                  borderRadius: '10px',
                  padding: '2px 8px',
                  fontSize: '0.75rem',
                  fontWeight: 'normal',
                }}>
                  {basket.stocks?.length || 0}
                </span>
              </button>
            );
          })}
        </div>

        {/* Selected Theme Details */}
        {activeBasket && (
          <div style={{ marginTop: '1.2rem', padding: '1rem', backgroundColor: '#fafafa', borderRadius: '6px', borderLeft: '4px solid #1A6B3C' }}>
            <h4 style={{ margin: '0 0 6px 0', color: '#333' }}>Description</h4>
            <p style={{ margin: 0, fontSize: '0.85rem', color: '#555', lineHeight: '1.4' }}>
              {activeBasket.description}
            </p>
          </div>
        )}
      </div>

      {/* Stocks Table */}
      <div className="table-container" style={{ marginTop: 0 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Company</th>
              <th>Sector</th>
              <th>Rolling Avg Score</th>
              <th>Latest Verdict</th>
              <th>Investability Status</th>
              <th>Matched Keywords</th>
              {onPrioritize && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {stocks.length === 0 ? (
              <tr>
                <td colSpan={onPrioritize ? "8" : "7"} className="empty-state" style={{ padding: '3rem', textAlign: 'center', color: '#888' }}>
                  No stocks currently match the rules/keywords for this thematic basket.
                </td>
              </tr>
            ) : (
              stocks.map(stock => (
                <tr key={stock.ticker}>
                  <td className="fw-bold">{stock.ticker}</td>
                  <td>{stock.companyName}</td>
                  <td>{stock.sector}</td>
                  <td>{stock.avgCompositeScore ? stock.avgCompositeScore.toFixed(1) : 'N/A'}</td>
                  <td>
                    <span className={`badge ${stock.latestVerdict === 'INVESTIGATE' ? 'badge-success' : 'badge-warning'}`}>
                      {stock.latestVerdict || 'MONITOR'}
                    </span>
                  </td>
                  <td>
                    {stock.isInvestable ? (
                      <span className="badge badge-success" style={{ backgroundColor: '#1A6B3C' }}>INVESTABLE</span>
                    ) : (
                      <span className="badge" style={{ backgroundColor: '#888', color: 'white' }}>WATCHLIST</span>
                    )}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {stock.matchedKeywords?.map(kw => (
                        <span key={kw} style={{
                          backgroundColor: '#e8f5e9',
                          color: '#2e7d32',
                          borderRadius: '4px',
                          padding: '2px 6px',
                          fontSize: '0.75rem',
                          fontWeight: 'bold',
                        }}>
                          {kw}
                        </span>
                      ))}
                    </div>
                  </td>
                  {onPrioritize && (
                    <td>
                      <button 
                        onClick={() => onPrioritize(stock.ticker)}
                        className="run-now-btn"
                        style={{ padding: '4px 8px', fontSize: '0.75rem', backgroundColor: '#1A6B3C', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                        title="Prioritize rescreening this stock in the next run"
                      >
                        ⚡ Prioritize
                      </button>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
