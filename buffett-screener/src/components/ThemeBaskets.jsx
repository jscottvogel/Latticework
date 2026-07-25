import { useState, useEffect } from 'react';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import outputs from '../../amplify_outputs.json';
import './TableStyles.css';

export default function ThemeBaskets({ onPrioritize, onGenerateMemo, newestRunId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [basketsData, setBasketsData] = useState(null);
  const [selectedThemeId, setSelectedThemeId] = useState('');
  const [startingCapitalInput, setStartingCapitalInput] = useState('10000');
  const [weightingStrategy, setWeightingStrategy] = useState('score'); // 'score' or 'equal'
  const [exportSuccess, setExportSuccess] = useState(false);
  const [validationData, setValidationData] = useState(null);

  useEffect(() => {
    async function fetchBaskets() {
      const bucketName = outputs?.custom?.dataBucketName;
      if (!bucketName) {
        setError("S3 Bucket Name not found in configurations.");
        setLoading(false);
        return;
      }
      const domain = outputs?.custom?.distributionDomainName || `${bucketName}.s3.amazonaws.com`;
      const url = `https://${domain}/dashboard/theme_baskets.json`;
      const valUrl = `https://${domain}/dashboard/validation_summary.json?t=${Date.now()}`;
      try {
        const [basketsResponse, valResponse] = await Promise.all([
          fetch(url),
          fetch(valUrl).catch(e => {
            console.warn("Validation summary fetch failed (gracefully caught):", e);
            return { ok: false };
          })
        ]);
        if (!basketsResponse.ok) {
          throw new Error(`Failed to fetch thematic baskets. Status: ${basketsResponse.status}`);
        }
        const data = await basketsResponse.json();
        setBasketsData(data);

        if (valResponse.ok) {
          const valData = await valResponse.json();
          setValidationData(valData);
        }
        
        // Auto-select the first theme with stocks, or just the first theme
        const basketKeys = Object.keys(data.baskets || {});
        if (basketKeys.length > 0) {
          const firstWithStocks = basketKeys.find(key => data.baskets[key].stocks?.length > 0);
          setSelectedThemeId(firstWithStocks || basketKeys[0]);
        }
      } catch (err) {
        console.error("Error loading thematic baskets data:", err);
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

  // Parse starting capital safely
  const startingCapital = Math.min(100000000, Math.max(100, parseInt(startingCapitalInput) || 100));

  // Calculate Theme Backtest Performance from constituent raw validation outcomes
  const themeTickers = new Set(stocks.map(s => s.ticker));
  const rawPairs = validationData?.horizons?.['30']?.rawPairs || [];
  const themePairs = rawPairs.filter(p => themeTickers.has(p.ticker));
  const hasThemePerformance = themePairs.length > 0;
  let themeAvgReturn = 0;
  let themeSpAvgReturn = 0;
  let themeAlpha = 0;
  let themeWinRate = 0;

  if (hasThemePerformance) {
    themeAvgReturn = (themePairs.reduce((sum, p) => sum + (p.stockReturn || 0), 0) / themePairs.length) * 100;
    themeSpAvgReturn = (themePairs.reduce((sum, p) => sum + (p.spReturn || 0), 0) / themePairs.length) * 100;
    themeAlpha = themeAvgReturn - themeSpAvgReturn;
    
    const beatConstituentsCount = themePairs.filter(p => (p.stockReturn || 0) > (p.spReturn || 0)).length;
    themeWinRate = (beatConstituentsCount / themePairs.length) * 100;
  }

  // Calculate Direct Indexing allocations
  const totalScoreSum = stocks.reduce((sum, s) => sum + Math.max(0, s.avgCompositeScore || 0), 0);
  
  const stocksWithAllocation = stocks.map(stock => {
    let weight = 0;
    if (stocks.length > 0) {
      if (weightingStrategy === 'equal') {
        weight = 1 / stocks.length;
      } else {
        weight = totalScoreSum > 0 ? Math.max(0, stock.avgCompositeScore || 0) / totalScoreSum : 0;
      }
    }
    const allocatedCapital = startingCapital * weight;
    return {
      ...stock,
      weight,
      allocatedCapital
    };
  });

  // Prepare Pie Chart data
  const pieColors = ['#1A6B3C', '#2E8B57', '#3CB371', '#4D8C57', '#66BB6A', '#81C784', '#A5D6A7', '#C8E6C9', '#E8F5E9'];
  const pieChartData = stocksWithAllocation.map(stock => ({
    name: stock.ticker,
    value: parseFloat(stock.allocatedCapital.toFixed(2)),
    weightPct: parseFloat((stock.weight * 100).toFixed(1))
  }));

  const handleExportConfig = () => {
    const config = {
      themeId: selectedThemeId,
      themeName: activeBasket?.name,
      startingCapital,
      weightingStrategy,
      allocations: stocksWithAllocation.map(s => ({
        ticker: s.ticker,
        companyName: s.companyName,
        weight: parseFloat((s.weight * 100).toFixed(2)),
        capitalAllocated: parseFloat(s.allocatedCapital.toFixed(2))
      }))
    };
    navigator.clipboard.writeText(JSON.stringify(config, null, 2));
    setExportSuccess(true);
    setTimeout(() => setExportSuccess(false), 3000);
  };

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
                className={`theme-tab-btn ${isActive ? 'active' : 'inactive'}`}
              >
                {basket.name}
                <span className={`badge-count ${isActive ? 'active' : 'inactive'}`}>
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

        {/* Direct Indexing Simulator Section */}
        {activeBasket && stocks.length > 0 && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '1.5rem',
            marginTop: '1.5rem',
            paddingTop: '1.5rem',
            borderTop: '1px solid #eee'
          }}>
            {/* Left Control Board */}
            <div style={{
              backgroundColor: '#fafafa',
              padding: '1.5rem',
              borderRadius: '8px',
              border: '1px solid #e0e0e0',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              gap: '1.2rem'
            }}>
              <div>
                <h3 style={{ margin: '0 0 10px 0', color: '#1A6B3C', fontSize: '1.1rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  🎯 Direct Indexing Simulator
                </h3>
                <p style={{ margin: '0 0 1.2rem 0', fontSize: '0.8rem', color: '#666', lineHeight: '1.4' }}>
                  Simulate deploying custom capital into this thematic basket. Weight components equally or align allocations to the AI's composite score.
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                  <div>
                    <label style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#444', display: 'block', marginBottom: '6px' }}>
                      Starting Investment Capital
                    </label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontWeight: 'bold', color: '#666' }}>$</span>
                      <input
                        type="number"
                        value={startingCapitalInput}
                        onChange={(e) => setStartingCapitalInput(e.target.value)}
                        onBlur={() => setStartingCapitalInput(Math.min(100000000, Math.max(100, parseInt(startingCapitalInput) || 100)).toString())}
                        style={{
                          padding: '8px 12px',
                          border: '1px solid #ccc',
                          borderRadius: '4px',
                          width: '140px',
                          fontSize: '0.9rem'
                        }}
                      />
                    </div>
                  </div>

                  <div>
                    <label style={{ fontSize: '0.8rem', fontWeight: 'bold', color: '#444', display: 'block', marginBottom: '6px' }}>
                      Weighting Allocation Strategy
                    </label>
                    <div style={{ display: 'flex', gap: '10px' }}>
                      <button
                        onClick={() => setWeightingStrategy('score')}
                        className={`strategy-btn ${weightingStrategy === 'score' ? 'active' : 'inactive'}`}
                      >
                        Score-Weighted
                      </button>
                      <button
                        onClick={() => setWeightingStrategy('equal')}
                        className={`strategy-btn ${weightingStrategy === 'equal' ? 'active' : 'inactive'}`}
                      >
                        Equal-Weighted
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <button
                  onClick={handleExportConfig}
                  className={`export-btn ${exportSuccess ? 'success' : 'default'}`}
                >
                  {exportSuccess ? '✓ Config Copied!' : '📤 Export Pie Config'}
                </button>
                <span style={{ fontSize: '0.7rem', color: '#888', display: 'block', marginTop: '6px', textAlign: 'center', fontStyle: 'italic' }}>
                  Note: Copy custom targets for fractional shares or direct brokerage APIs.
                </span>
              </div>
            </div>

            {/* Right Chart & Performance Section */}
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '1rem'
            }}>
              {/* Pie Chart Card */}
              <div style={{
                backgroundColor: 'white',
                padding: '1.2rem',
                borderRadius: '8px',
                border: '1px solid #e0e0e0',
                display: 'flex',
                flexDirection: 'column',
                height: '240px'
              }}>
                <h4 style={{ margin: '0 0 10px 0', color: '#555', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Simulated Weight Allocation (%)
                </h4>
                <div style={{ flexGrow: 1, position: 'relative' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieChartData}
                        cx="50%"
                        cy="50%"
                        innerRadius={50}
                        outerRadius={70}
                        paddingAngle={3}
                        dataKey="value"
                      >
                        {pieChartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={pieColors[index % pieColors.length]} />
                        ))}
                      </Pie>
                      <Tooltip
                        formatter={(value, name, props) => [`$${value.toLocaleString()} (${props.payload.weightPct}%)`, 'Allocated']}
                        contentStyle={{ borderRadius: '6px', border: '1px solid #ccc', fontSize: '0.85rem' }}
                      />
                      <Legend
                        verticalAlign="bottom"
                        height={30}
                        iconSize={8}
                        iconType="circle"
                        wrapperStyle={{ fontSize: '0.75rem', paddingTop: '5px' }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Theme Performance Card */}
              <div style={{
                backgroundColor: 'white',
                padding: '1.2rem 1.5rem',
                borderRadius: '8px',
                border: '1px solid #e0e0e0',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                gap: '10px'
              }}>
                <h4 style={{ margin: '0', color: '#555', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  📈 30-Day Cohort Historical Returns
                </h4>
                
                {hasThemePerformance ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                      <span style={{ color: '#666' }}>Theme Avg Return (Constituents)</span>
                      <span style={{ fontWeight: 'bold', color: themeAvgReturn >= 0 ? '#1A6B3C' : '#d93025' }}>
                        {themeAvgReturn >= 0 ? '+' : ''}{themeAvgReturn.toFixed(2)}%
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                      <span style={{ color: '#666' }}>S&P 500 Index Avg Return</span>
                      <span style={{ fontWeight: 'bold', color: '#555' }}>
                        {themeSpAvgReturn >= 0 ? '+' : ''}{themeSpAvgReturn.toFixed(2)}%
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                      <span style={{ color: '#666' }}>Constituent Win Rate (Beats S&P)</span>
                      <span style={{ fontWeight: 'bold', color: themeWinRate >= 50 ? '#1A6B3C' : '#d93025' }}>
                        {themeWinRate.toFixed(1)}%
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', borderTop: '1px dashed #ddd', paddingTop: '6px' }}>
                      <span style={{ color: '#333', fontWeight: 'bold' }}>Thematic Alpha (Outperformance)</span>
                      <span style={{ fontWeight: 'bold', color: themeAlpha >= 0 ? '#1A6B3C' : '#d93025' }}>
                        {themeAlpha >= 0 ? '+' : ''}{themeAlpha.toFixed(2)}%
                      </span>
                    </div>
                    <span style={{ fontSize: '0.7rem', color: '#888', fontStyle: 'italic', marginTop: '4px' }}>
                      *Based on {themePairs.length} historical 30-day validation observations.
                    </span>
                  </div>
                ) : (
                  <div style={{ fontSize: '0.8rem', color: '#888', fontStyle: 'italic', padding: '10px 0' }}>
                    No historical validation outcomes computed yet for these theme constituents.
                  </div>
                )}
              </div>
            </div>
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
              <th>Allocation Weight</th>
              <th>Simulated Capital</th>
              <th>Latest Verdict</th>
              <th>Investability Status</th>
              <th>Matched Keywords</th>
              {(onPrioritize || onGenerateMemo) && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {stocks.length === 0 ? (
              <tr>
                <td colSpan={(onPrioritize || onGenerateMemo) ? "10" : "9"} className="empty-state" style={{ padding: '3rem', textAlign: 'center', color: '#888' }}>
                  No stocks currently match the rules/keywords for this thematic basket.
                </td>
              </tr>
            ) : (
              stocksWithAllocation.map(stock => (
                <tr key={stock.ticker}>
                  <td className="fw-bold">{stock.ticker}</td>
                  <td>{stock.companyName}</td>
                  <td>{stock.sector}</td>
                  <td>{stock.avgCompositeScore ? stock.avgCompositeScore.toFixed(1) : 'N/A'}</td>
                  <td style={{ fontWeight: '600', color: '#1A6B3C' }}>{(stock.weight * 100).toFixed(1)}%</td>
                  <td style={{ fontWeight: '600' }}>{stock.allocatedCapital.toLocaleString(undefined, { style: 'currency', currency: 'USD' })}</td>
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
                  {(onPrioritize || onGenerateMemo) && (
                    <td>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        {onGenerateMemo && newestRunId && (
                          <button
                            onClick={() => onGenerateMemo(stock.ticker, stock.companyName, newestRunId)}
                            className="run-now-btn"
                            style={{ padding: '4px 8px', fontSize: '0.75rem', backgroundColor: '#475569', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                            title="Generate/view buy-side research memo"
                          >
                            📝 Memo
                          </button>
                        )}
                        {onPrioritize && (
                          <button 
                            onClick={() => onPrioritize(stock.ticker)}
                            className="run-now-btn"
                            style={{ padding: '4px 8px', fontSize: '0.75rem', backgroundColor: '#1A6B3C', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                            title="Prioritize rescreening this stock in the next run"
                          >
                            ⚡ Prioritize
                          </button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Regulatory Direct Indexing Disclosure */}
      {activeBasket && stocks.length > 0 && (
        <div style={{
          backgroundColor: '#f8fafc',
          padding: '1.2rem 1.5rem',
          borderRadius: '8px',
          border: '1px solid #e2e8f0',
          fontSize: '0.75rem',
          color: '#64748b',
          lineHeight: '1.5',
          textAlign: 'justify'
        }}>
          <strong>Regulatory Disclosure:</strong> The thematic allocations and historical constituent statistics presented above are for simulated educational and illustration purposes only and do not constitute an offer, solicitation, or recommendation to buy or sell any security. Direct indexing involves purchasing individual securities and carries risk, including potential loss of principal. Performance of custom baskets may deviate from standard benchmark ETFs due to transaction costs, weighting differences, cash drag, and execution timings. The simulator does not account for the tax consequences of trading or rebalancing. Exact replication of model weight distributions requires fractional share capabilities; fractional shares are not transferable, do not carry voting rights, and may have liquidity profiles distinct from whole shares. Historical constituent returns represent Total Shareholder Return (adjusted close price inclusive of reinvested distributions), but actual execution outcomes may vary. Past performance of any scoring methodology is no guarantee of future results.
        </div>
      )}
    </div>
  );
}
