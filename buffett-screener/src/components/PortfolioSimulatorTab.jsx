import { LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

export default function PortfolioSimulatorTab({
  rawPairs,
  startingCapital,
  setStartingCapital,
  allocMethod,
  setAllocMethod,
  portfolioFinalValue,
  benchmarkFinalValue,
  growthData,
  totalRuns,
  portfolioTotalReturn,
  benchmarkTotalReturn,
  netAlpha,
  portfolioBeatRate,
  spreadData
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {rawPairs.length === 0 ? (
        <div style={{ padding: '3rem', textAlign: 'center', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', color: '#666' }}>
          <h3>No portfolio backtest outcomes available for this horizon.</h3>
          <p>Try switching to the 30-Day horizon above.</p>
        </div>
      ) : (
        <>
          {/* Backtest Configuration Panel */}
          <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.5rem' }}>
            <div>
              <h4 style={{ margin: '0 0 0.8rem 0', color: '#333' }}>Starting Capital</h4>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontWeight: 'bold', color: '#666' }}>$</span>
                <input 
                  type="number" 
                  value={startingCapital} 
                  onChange={(e) => setStartingCapital(Math.max(100, parseInt(e.target.value) || 0))}
                  style={{ padding: '8px 12px', width: '120px', border: '1px solid #ccc', borderRadius: '4px', fontSize: '0.95rem' }} 
                />
              </div>
              <span style={{ fontSize: '0.75rem', color: '#888', display: 'block', marginTop: '6px' }}>Simulated initial investment amount.</span>
            </div>

            <div>
              <h4 style={{ margin: '0 0 0.8rem 0', color: '#333' }}>Allocation Strategy</h4>
              <select 
                value={allocMethod} 
                onChange={(e) => setAllocMethod(e.target.value)}
                style={{ padding: '8px 12px', border: '1px solid #ccc', borderRadius: '4px', width: '100%', fontSize: '0.95rem', cursor: 'pointer' }}
              >
                <option value="top10">Equal-Weighted Top 10 Picks</option>
                <option value="top5">Equal-Weighted Top 5 Picks</option>
                <option value="threshold75">Screener Tier (Score &gt;= 7.5)</option>
                <option value="threshold70">Screener Tier (Score &gt;= 7.0)</option>
              </select>
              <span style={{ fontSize: '0.75rem', color: '#888', display: 'block', marginTop: '6px' }}>How stocks are chosen for each run's portfolio.</span>
            </div>

            <div>
              <h4 style={{ margin: '0 0 0.8rem 0', color: '#333' }}>Outperformance metrics</h4>
              <div style={{ display: 'flex', gap: '15px' }}>
                <div>
                  <span style={{ fontSize: '0.75rem', color: '#888' }}>Total Portfolio Value</span>
                  <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#1A6B3C' }}>
                    ${portfolioFinalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '0.75rem', color: '#888' }}>S&P 500 Value</span>
                  <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#555' }}>
                    ${benchmarkFinalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Grid of Results */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '2rem' }}>
            
            {/* Simulated Equity Curve Line Chart */}
            <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', gridColumn: 'span 2' }}>
              <h3 style={{ color: '#1A6B3C', margin: '0 0 1rem 0', fontSize: '1.2rem' }}>Simulated Growth of Capital ($10,000)</h3>
              <p style={{ fontSize: '0.85rem', color: '#666', marginBottom: '1.5rem' }}>
                Simulates investing a fixed allocation ($1,000 per run) into each cohort's picks and tracks the cumulative capital growth over time vs. the S&P 500 index.
              </p>

              <div style={{ height: '350px', width: '100%' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={growthData} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} />
                    <YAxis tickFormatter={(v) => `$${v.toLocaleString()}`} tick={{ fontSize: 9 }} />
                    <Tooltip 
                      formatter={(value) => [`$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`]}
                      contentStyle={{ borderRadius: '8px', border: '1px solid #ccc' }}
                    />
                    <Legend wrapperStyle={{ fontSize: '0.9rem', paddingTop: '10px' }} />
                    <Line type="monotone" dataKey="Value Screener Portfolio" stroke="#1A6B3C" strokeWidth={3} dot={false} activeDot={{ r: 6 }} />
                    <Line type="monotone" dataKey="S&P 500 Index" stroke="#94a3b8" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Performance Summary Cards and Beat Rates */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              
              {/* Performance Statistics Card */}
              <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', flexGrow: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                <h4 style={{ margin: '0 0 1rem 0', color: '#555', borderBottom: '1px solid #eee', paddingBottom: '0.5rem' }}>Cumulative Statistics</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.85rem', color: '#666' }}>Total Runs Backtested</span>
                    <span style={{ fontWeight: 'bold' }}>{totalRuns} runs</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.85rem', color: '#666' }}>Portfolio Return</span>
                    <span style={{ fontWeight: 'bold', color: '#1A6B3C' }}>+{portfolioTotalReturn.toFixed(1)}%</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.85rem', color: '#666' }}>S&P 500 Return</span>
                    <span style={{ fontWeight: 'bold', color: '#555' }}>+{benchmarkTotalReturn.toFixed(1)}%</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px dashed #ddd', paddingTop: '8px' }}>
                    <span style={{ fontSize: '0.85rem', color: '#666', fontWeight: 'bold' }}>Net Outperformance (Alpha)</span>
                    <span style={{ fontWeight: 'bold', color: netAlpha >= 0 ? '#1A6B3C' : '#d93025' }}>
                      {netAlpha >= 0 ? '+' : ''}{netAlpha.toFixed(1)}%
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.85rem', color: '#666' }}>Win Rate (Beats S&P)</span>
                    <span style={{ fontWeight: 'bold', color: '#1A6B3C' }}>{portfolioBeatRate.toFixed(1)}%</span>
                  </div>
                </div>
              </div>

              {/* Investigate vs Avoid Spread Chart */}
              <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', flexGrow: 1 }}>
                <h4 style={{ margin: '0 0 1rem 0', color: '#555', borderBottom: '1px solid #eee', paddingBottom: '0.5rem' }}>Investigate vs. Avoid Return Spread</h4>
                <div style={{ height: '160px', width: '100%' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={spreadData} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                      <XAxis type="number" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 9 }} />
                      <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 9 }} />
                      <Tooltip 
                        formatter={(value, name, props) => [`${value}% (across ${props.payload.count} outcomes)`, 'Avg Return']}
                        contentStyle={{ borderRadius: '8px', border: '1px solid #ccc' }}
                      />
                      <Bar dataKey="return" radius={[0, 4, 4, 0]}>
                        {spreadData.map((entry, index) => (
                          <Cell 
                            key={`cell-${index}`} 
                            fill={index === 0 ? '#1A6B3C' : index === 1 ? '#94a3b8' : '#d93025'} 
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
