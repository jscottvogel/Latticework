import { useState, useEffect } from 'react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import outputs from '../../amplify_outputs.json';

export default function AdvisorTournament() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [selectedHorizon, setSelectedHorizon] = useState('1Y'); // '6M', '1Y', '2Y', '3Y', '5Y'
  const [activeAdvisor, setActiveAdvisor] = useState('Munger'); // Default view details for Charlie Munger

  useEffect(() => {
    async function fetchCompetitionData() {
      const bucketName = outputs?.custom?.dataBucketName;
      if (!bucketName) {
        setError("S3 Bucket Name not found in configurations.");
        setLoading(false);
        return;
      }
      const domain = outputs?.custom?.distributionDomainName || `${bucketName}.s3.amazonaws.com`;
      const url = `https://${domain}/dashboard/advisor_competition.json?t=${Date.now()}`;
      try {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error("Advisor competition data is not seeded yet. Run the validation pipeline to generate results.");
        }
        const competitionJson = await response.json();
        setData(competitionJson);
      } catch (err) {
        console.error("Error loading competition data:", err);
        setError(err.message || "Failed to load competition data.");
      } finally {
        setLoading(false);
      }
    }
    fetchCompetitionData();
  }, []);

  if (loading) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', color: '#1A6B3C', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
        <div style={{ width: '40px', height: '40px', border: '4px solid #f3f3f3', borderTop: '4px solid #1A6B3C', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 1rem auto' }}></div>
        <p style={{ fontWeight: 'bold' }}>Loading Advisor Tournament Arena...</p>
        <style>{`
          @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '2.5rem', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', color: '#d93025' }}>
        <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>⚠️</span> Arena Results Unavailable
        </h3>
        <p>{error}</p>
        <p style={{ fontSize: '0.85rem', color: '#666', marginTop: '1rem' }}>
          Please ensure the <code>AdvisorCompetitionWorker</code> Lambda function has run successfully to perform selection scans and backtesting.
        </p>
      </div>
    );
  }

  const advisors = data?.advisors || {};
  const horizonData = data?.horizons?.[selectedHorizon];

  if (!horizonData) {
    return (
      <div style={{ padding: '3rem', textAlign: 'center', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', color: '#666' }}>
        <h3>No competition results available for this horizon.</h3>
        <p>Try selecting a different time horizon above.</p>
      </div>
    );
  }

  const leaderboard = horizonData.leaderboard || [];
  const timeline = horizonData.timeline || [];

  // Colors mapping for advisors
  const advisorColors = {
    'Graham': '#1e88e5',    // Classic Blue
    'Munger': '#2e7d32',    // Deep Green
    'Fisher': '#e65100',    // Dark Orange
    'SPY': '#78909c'        // Cool Slate Grey
  };

  const handleExportConfig = (advId, advData) => {
    const config = {
      advisor: advData.name,
      title: advData.title,
      strategy: advId,
      exportedAt: new Date().toISOString(),
      holdings: advData.selections.map(s => ({
        ticker: s.ticker,
        companyName: s.companyName,
        targetWeightPct: parseFloat((s.weight * 100).toFixed(2))
      }))
    };
    
    navigator.clipboard.writeText(JSON.stringify(config, null, 2))
      .then(() => {
        alert(`${advData.name} Direct-Indexing config copied to clipboard successfully!`);
      })
      .catch(err => {
        console.error("Clipboard copy failed: ", err);
        alert("Failed to copy configuration to clipboard.");
      });
  };

  const formatPercentage = (num) => {
    if (num === undefined || num === null) return '0.00%';
    const pct = (num * 100).toFixed(2);
    return `${pct > 0 ? '+' : ''}${pct}%`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      
      {/* 1. Header Control Panel */}
      <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ margin: 0, color: '#1A6B3C', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span>🏆</span> Agentic Advisors Tournament
          </h2>
          <span style={{ fontSize: '0.85rem', color: '#666' }}>Watch AI investment managers compete with their custom portfolios.</span>
        </div>
        
        {/* Horizon Selectors */}
        <div style={{ display: 'flex', gap: '6px', backgroundColor: '#f1f8e9', padding: '4px', borderRadius: '6px' }}>
          {['6M', '1Y', '2Y', '3Y', '5Y'].map(horizon => (
            <button
              key={horizon}
              onClick={() => setSelectedHorizon(horizon)}
              style={{
                padding: '6px 12px',
                border: 'none',
                borderRadius: '4px',
                fontWeight: 'bold',
                fontSize: '0.85rem',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                backgroundColor: selectedHorizon === horizon ? '#1A6B3C' : 'transparent',
                color: selectedHorizon === horizon ? 'white' : '#1A6B3C',
              }}
            >
              {horizon}
            </button>
          ))}
        </div>
      </div>

      {/* 2. Leaderboard Table */}
      <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
        <h3 style={{ margin: '0 0 1rem 0', color: '#333', borderBottom: '2px solid #f1f8e9', paddingBottom: '0.5rem' }}>
          Horizon Standings ({horizonData.label})
        </h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ backgroundColor: '#f9fbf7', borderBottom: '2px solid #e1e8dd' }}>
                <th style={{ padding: '12px 16px', color: '#555', fontWeight: 'bold' }}>Rank</th>
                <th style={{ padding: '12px 16px', color: '#555', fontWeight: 'bold' }}>Advisor / Portfolio</th>
                <th style={{ padding: '12px 16px', color: '#555', fontWeight: 'bold', textAlign: 'right' }}>Total Return</th>
                <th style={{ padding: '12px 16px', color: '#555', fontWeight: 'bold', textAlign: 'right' }}>Annualized Return</th>
                <th style={{ padding: '12px 16px', color: '#555', fontWeight: 'bold', textAlign: 'right' }}>Max Drawdown</th>
                <th style={{ padding: '12px 16px', color: '#555', fontWeight: 'bold', textAlign: 'right' }}>Sharpe Ratio</th>
                <th style={{ padding: '12px 16px', color: '#555', fontWeight: 'bold', textAlign: 'right' }}>Alpha vs S&P 500</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((item, idx) => {
                const isBenchmark = item.advisorId === 'SPY';
                const rowColor = isBenchmark ? '#f5f7f8' : (idx === 0 ? '#fffdf0' : 'white');
                const badgeColor = idx === 0 ? '#ffd700' : (idx === 1 ? '#c0c0c0' : (idx === 2 ? '#cd7f32' : '#e0e0e0'));
                
                return (
                  <tr 
                    key={item.advisorId} 
                    style={{ 
                      backgroundColor: rowColor, 
                      borderBottom: '1px solid #eef2eb',
                      fontWeight: isBenchmark ? 'bold' : 'normal',
                      transition: 'background-color 0.2s',
                    }}
                  >
                    <td style={{ padding: '14px 16px' }}>
                      <span style={{ 
                        display: 'inline-flex', 
                        alignItems: 'center', 
                        justifyContent: 'center', 
                        width: '24px', 
                        height: '24px', 
                        borderRadius: '50%', 
                        backgroundColor: badgeColor, 
                        color: idx < 3 ? 'black' : '#666',
                        fontWeight: 'bold',
                        fontSize: '0.85rem'
                      }}>
                        {isBenchmark ? '•' : idx + 1}
                      </span>
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <div>
                        <span style={{ 
                          fontWeight: 'bold', 
                          color: isBenchmark ? '#555' : advisorColors[item.advisorId],
                          cursor: isBenchmark ? 'default' : 'pointer',
                          textDecoration: isBenchmark ? 'none' : 'underline'
                        }}
                        onClick={() => {
                          if (!isBenchmark) setActiveAdvisor(item.advisorId);
                        }}
                        >
                          {item.name}
                        </span>
                        <div style={{ fontSize: '0.75rem', color: '#777', marginTop: '2px' }}>{item.title}</div>
                      </div>
                    </td>
                    <td style={{ 
                      padding: '14px 16px', 
                      textAlign: 'right', 
                      color: item.totalReturn >= 0 ? '#2e7d32' : '#c62828',
                      fontWeight: 'bold'
                    }}>
                      {formatPercentage(item.totalReturn)}
                    </td>
                    <td style={{ 
                      padding: '14px 16px', 
                      textAlign: 'right',
                      color: item.annualizedReturn >= 0 ? '#2e7d32' : '#c62828'
                    }}>
                      {formatPercentage(item.annualizedReturn)}
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right', color: '#c62828' }}>
                      -{formatPercentage(item.maxDrawdown).replace('+', '')}
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 'bold' }}>
                      {item.sharpe.toFixed(2)}
                    </td>
                    <td style={{ 
                      padding: '14px 16px', 
                      textAlign: 'right', 
                      fontWeight: 'bold',
                      color: item.alpha >= 0 ? '#2e7d32' : '#c62828'
                    }}>
                      {isBenchmark ? '-' : formatPercentage(item.alpha)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. Performance Trend Line Chart */}
      <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
        <h3 style={{ margin: '0 0 1.5rem 0', color: '#333' }}>
          Simulated Growth of $10,000 ({horizonData.startDate} to {horizonData.endDate})
        </h3>
        <div style={{ width: '100%', height: 350 }}>
          <ResponsiveContainer>
            <LineChart data={timeline} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
              <XAxis 
                dataKey="date" 
                tick={{ fontSize: 11, fill: '#666' }} 
                stroke="#ccc"
                tickFormatter={(date) => {
                  try {
                    const parts = date.split('-');
                    return `${parts[1]}/${parts[0].substring(2)}`;
                  } catch (e) {
                    return date;
                  }
                }}
              />
              <YAxis 
                tick={{ fontSize: 11, fill: '#666' }} 
                stroke="#ccc"
                tickFormatter={(val) => `$${val.toLocaleString()}`} 
                domain={['dataMin - 1000', 'dataMax + 1000']}
              />
              <Tooltip 
                formatter={(value) => [`$${Math.round(value).toLocaleString()}`]}
                labelStyle={{ fontWeight: 'bold', color: '#333' }}
              />
              <Legend iconType="circle" wrapperStyle={{ fontSize: '0.9rem', paddingTop: '10px' }} />
              <Line 
                name="Benjamin Graham (Deep Value)" 
                type="monotone" 
                dataKey="Graham" 
                stroke={advisorColors.Graham} 
                strokeWidth={2.5} 
                dot={false}
                activeDot={{ r: 6 }}
              />
              <Line 
                name="Charlie Munger (Moat)" 
                type="monotone" 
                dataKey="Munger" 
                stroke={advisorColors.Munger} 
                strokeWidth={2.5} 
                dot={false}
                activeDot={{ r: 6 }}
              />
              <Line 
                name="Philip Fisher (Growth)" 
                type="monotone" 
                dataKey="Fisher" 
                stroke={advisorColors.Fisher} 
                strokeWidth={2.5} 
                dot={false}
                activeDot={{ r: 6 }}
              />
              <Line 
                name="S&P 500 Index (Benchmark)" 
                type="monotone" 
                dataKey="SPY" 
                stroke={advisorColors.SPY} 
                strokeWidth={2.0} 
                strokeDasharray="5 5"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 4. Advisor Profile Showcase & Holdings Detail */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '2rem' }}>
        
        {/* Advisor Selectors Card */}
        <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <h3 style={{ margin: 0, color: '#333' }}>AI Advisor Personas</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {Object.entries(advisors).map(([advId, advData]) => {
              const isActive = activeAdvisor === advId;
              const color = advisorColors[advId];
              return (
                <div
                  key={advId}
                  onClick={() => setActiveAdvisor(advId)}
                  style={{
                    padding: '1.2rem',
                    borderRadius: '8px',
                    border: `2px solid ${isActive ? color : '#eaeaea'}`,
                    backgroundColor: isActive ? `${color}05` : 'white',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    position: 'relative',
                  }}
                >
                  <h4 style={{ margin: '0 0 4px 0', color: color }}>{advData.name}</h4>
                  <span style={{ fontSize: '0.75rem', fontWeight: 'bold', color: '#555' }}>{advData.title}</span>
                  <p style={{ fontSize: '0.8rem', color: '#666', margin: '8px 0 0 0', lineHeight: '1.4' }}>{advData.desc}</p>
                  
                  {isActive && (
                    <div style={{
                      position: 'absolute',
                      right: '12px',
                      top: '12px',
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      backgroundColor: color
                    }} />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Selected Holdings Card */}
        {activeAdvisor && advisors[activeAdvisor] && (
          <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', display: 'flex', flexDirection: 'column', justifyBetween: 'space-between', gap: '1.5rem' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #f1f8e9', paddingBottom: '0.5rem', marginBottom: '1rem' }}>
                <h3 style={{ margin: 0, color: '#333' }}>
                  {advisors[activeAdvisor].name} Portfolio
                </h3>
                <button
                  onClick={() => handleExportConfig(activeAdvisor, advisors[activeAdvisor])}
                  style={{
                    padding: '6px 12px',
                    border: '1px solid #1A6B3C',
                    borderRadius: '4px',
                    backgroundColor: 'transparent',
                    color: '#1A6B3C',
                    fontWeight: 'bold',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                  onMouseOver={(e) => {
                    e.currentTarget.style.backgroundColor = '#1A6B3C';
                    e.currentTarget.style.color = 'white';
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                    e.currentTarget.style.color = '#1A6B3C';
                  }}
                >
                  📥 Export Config
                </button>
              </div>

              {/* Thesis text escaping (React escaping avoids dangerouslySetInnerHTML) */}
              <div style={{ backgroundColor: '#f9f9f9', padding: '1rem', borderRadius: '6px', borderLeft: `4px solid ${advisorColors[activeAdvisor]}`, fontSize: '0.85rem', color: '#555', fontStyle: 'italic', marginBottom: '1.2rem', lineHeight: '1.5' }}>
                &ldquo;{advisors[activeAdvisor].thesis}&rdquo;
              </div>

              {/* Holdings list */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {advisors[activeAdvisor].selections.map((holding) => (
                  <div 
                    key={holding.ticker} 
                    style={{ 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center', 
                      padding: '10px 12px', 
                      backgroundColor: '#fafafa', 
                      borderRadius: '4px', 
                      fontSize: '0.85rem',
                      border: '1px solid #f0f0f0'
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 'bold', color: '#1a1a1a', textDecoration: 'underline', cursor: 'pointer' }}>
                        {holding.ticker}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#666', marginLeft: '8px' }}>{holding.companyName}</span>
                    </div>
                    <span style={{ fontWeight: 'bold', color: advisorColors[activeAdvisor], backgroundColor: `${advisorColors[activeAdvisor]}10`, padding: '2px 6px', borderRadius: '4px', fontSize: '0.8rem' }}>
                      {(holding.weight * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

      </div>

      {/* 5. SEC Regulatory Hypothetical Performance Disclosure Footer */}
      <div style={{ backgroundColor: '#fafbf9', border: '1px solid #e1e8dd', padding: '1.2rem', borderRadius: '6px', fontSize: '0.78rem', color: '#666', lineHeight: '1.6', textAlign: 'justify' }}>
        <strong style={{ color: '#444', display: 'block', marginBottom: '4px' }}>Regulatory Disclosure & Backtest Limitations</strong>
        {data?.updatedAt && <div style={{ fontSize: '0.7rem', color: '#888', marginBottom: '6px' }}>Last updated: {new Date(data.updatedAt).toLocaleString()}</div>}
        This is hypothetical, backtested performance. These results did not involve actual trading and were produced with the benefit of hindsight. Hypothetical performance has inherent limitations and does not reflect the impact that material economic and market factors may have had on actual decision-making. Past performance is no guarantee of future results. All simulator investments are simulated models and represent hypothetical outcomes under fixed rules.
      </div>

    </div>
  );
}
