import { Fragment } from 'react';

export default function VintageLeaderboardTab({ vintagesList, selectedHorizon, expandedMonth, setExpandedMonth }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {vintagesList.length === 0 ? (
        <div style={{ padding: '3rem', textAlign: 'center', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', color: '#666' }}>
          <h3>No matured cohorts available.</h3>
          <p>Try switching to the 30-Day horizon above.</p>
        </div>
      ) : (
        <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
          <h3 style={{ color: '#1A6B3C', margin: '0 0 1rem 0', fontSize: '1.2rem' }}>Cohort Vintages Leaderboard</h3>
          <p style={{ fontSize: '0.85rem', color: '#666', marginBottom: '1.5rem' }}>
            Performance metrics of the Top 10 recommendations grouped by the calendar month they were made, evaluated over their full {selectedHorizon}-day maturity window.
          </p>

          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Month Vintage</th>
                  <th>Picks Count</th>
                  <th>Cohort Avg Return</th>
                  <th>S&P 500 Return</th>
                  <th>Excess Return (Alpha)</th>
                  <th>Star Performer</th>
                </tr>
              </thead>
              <tbody>
                {vintagesList.map((vintage) => {
                  const isExpanded = expandedMonth === vintage.monthKey;
                  return (
                    <Fragment key={vintage.monthKey}>
                      <tr 
                        onClick={() => setExpandedMonth(isExpanded ? null : vintage.monthKey)}
                        style={{ cursor: 'pointer', transition: 'background-color 0.2s', backgroundColor: isExpanded ? '#f8fafc' : 'transparent' }}
                        onMouseEnter={(e) => { if (!isExpanded) e.currentTarget.style.backgroundColor = '#f8fafc'; }}
                        onMouseLeave={(e) => { if (!isExpanded) e.currentTarget.style.backgroundColor = 'transparent'; }}
                      >
                        <td style={{ fontWeight: '600' }}>
                          <span style={{ marginRight: '8px', color: '#1A6B3C', fontSize: '0.8rem', display: 'inline-block', width: '12px' }}>
                            {isExpanded ? '▼' : '►'}
                          </span>
                          {vintage.monthName}
                        </td>
                        <td>{vintage.count} picks</td>
                        <td style={{ fontWeight: '500', color: vintage.avgReturn >= 0 ? '#1A6B3C' : '#d93025' }}>
                          {(vintage.avgReturn * 100).toFixed(1)}%
                        </td>
                        <td style={{ color: '#555' }}>
                          {(vintage.spReturn * 100).toFixed(1)}%
                        </td>
                        <td style={{ 
                          fontWeight: 'bold', 
                          color: vintage.alpha >= 0 ? '#1A6B3C' : '#d93025',
                          backgroundColor: vintage.alpha >= 0.02 ? 'rgba(26, 107, 60, 0.05)' : vintage.alpha <= -0.02 ? 'rgba(217, 48, 37, 0.05)' : 'transparent'
                        }}>
                          {vintage.alpha >= 0 ? '+' : ''}{(vintage.alpha * 100).toFixed(1)}%
                        </td>
                        <td style={{ fontStyle: 'italic', fontSize: '0.85rem', color: '#1e293b' }}>
                          {vintage.starPick}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr>
                          <td colSpan={6} style={{ backgroundColor: '#f8fafc', padding: '1rem' }}>
                            <div style={{ border: '1px solid #e2e8f0', borderRadius: '6px', overflow: 'hidden', backgroundColor: 'white', boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.02)' }}>
                              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', textAlign: 'left' }}>
                                <thead>
                                  <tr style={{ backgroundColor: '#f1f5f9', borderBottom: '1px solid #e2e8f0' }}>
                                    <th style={{ padding: '8px 12px', color: '#475569' }}>Ticker</th>
                                    <th style={{ padding: '8px 12px', color: '#475569' }}>Score</th>
                                    <th style={{ padding: '8px 12px', color: '#475569' }}>Verdict</th>
                                    <th style={{ padding: '8px 12px', color: '#475569' }}>Stock Return</th>
                                    <th style={{ padding: '8px 12px', color: '#475569' }}>S&P 500 Return</th>
                                    <th style={{ padding: '8px 12px', color: '#475569' }}>Alpha</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {vintage.picks.map(pick => {
                                    const alpha = pick.stockReturn - pick.spReturn;
                                    return (
                                      <tr key={pick.ticker} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                        <td style={{ padding: '8px 12px', fontWeight: 'bold', color: '#0f172a' }}>{pick.ticker}</td>
                                        <td style={{ padding: '8px 12px', color: '#334155' }}>{pick.score.toFixed(2)}</td>
                                        <td style={{ padding: '8px 12px' }}>
                                          <span style={{
                                            padding: '2px 6px',
                                            borderRadius: '4px',
                                            fontSize: '0.75rem',
                                            fontWeight: '600',
                                            backgroundColor: pick.verdict === 'INVESTIGATE' ? '#e2f0d9' : '#fff2cc',
                                            color: pick.verdict === 'INVESTIGATE' ? '#385723' : '#b25900'
                                          }}>
                                            {pick.verdict}
                                          </span>
                                        </td>
                                        <td style={{ padding: '8px 12px', color: pick.stockReturn >= 0 ? '#1A6B3C' : '#d93025', fontWeight: '500' }}>
                                          {(pick.stockReturn * 100).toFixed(1)}%
                                        </td>
                                        <td style={{ padding: '8px 12px', color: '#64748b' }}>
                                          {(pick.spReturn * 100).toFixed(1)}%
                                        </td>
                                        <td style={{ 
                                          padding: '8px 12px', 
                                          fontWeight: 'bold', 
                                          color: alpha >= 0 ? '#1A6B3C' : '#d93025' 
                                        }}>
                                          {alpha >= 0 ? '+' : ''}{(alpha * 100).toFixed(1)}%
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
