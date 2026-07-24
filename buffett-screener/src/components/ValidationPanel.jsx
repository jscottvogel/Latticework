import { useState, useEffect } from 'react';
import { 
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, 
  ResponsiveContainer, ReferenceLine, LineChart, Line, Legend 
} from 'recharts';
import outputs from '../../amplify_outputs.json';

export default function ValidationPanel() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [validationData, setValidationData] = useState(null);
  const [selectedHorizon, setSelectedHorizon] = useState('30');
  const [subTab, setSubTab] = useState('predictive'); // 'predictive', 'sandbox', 'vintages'

  // Sandbox inputs
  const [startingCapital, setStartingCapital] = useState(10000);
  const [allocMethod, setAllocMethod] = useState('top10'); // 'top10', 'top5', 'threshold75', 'threshold70'

  useEffect(() => {
    async function fetchSummary() {
      const bucketName = outputs?.custom?.dataBucketName;
      if (!bucketName) {
        setError("S3 Bucket Name not found in configurations.");
        setLoading(false);
        return;
      }
      const domain = outputs?.custom?.distributionDomainName || `${bucketName}.s3.amazonaws.com`;
      const url = `https://${domain}/dashboard/validation_summary.json?t=${Date.now()}`;
      try {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`Failed to fetch validation summary. Status: ${response.status}`);
        }
        const data = await response.json();
        setValidationData(data);
      } catch (err) {
        console.error("Error loading validation summary:", err);
        setError(err.message || "Failed to load validation summary.");
      } finally {
        setLoading(false);
      }
    }

    fetchSummary();
  }, []);

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: '#666', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
        Loading validation summary from S3...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '2rem', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', color: '#d93025' }}>
        <h3 style={{ marginTop: 0 }}>Validation Data Unavailable</h3>
        <p>{error}</p>
        <p style={{ fontSize: '0.85rem', color: '#666' }}>
          Please make sure the <code>BacktestValidator</code> Lambda has run at least once to compute outcomes and export the dashboard validation summary.
        </p>
      </div>
    );
  }

  const horizons = validationData?.horizons || {};
  const currentData = horizons[selectedHorizon];

  if (!currentData) {
    return (
      <div style={{ padding: '2rem', backgroundColor: 'white', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', color: '#666' }}>
        No validation metrics found for the selected horizon.
      </div>
    );
  }

  // Format correlations data for Recharts BarChart
  const rawCorrelations = currentData.correlations || {};
  const chartData = [
    { name: 'Moat', correlation: rawCorrelations.moat || 0 },
    { name: 'Fin Health', correlation: rawCorrelations.financialHealth || 0 },
    { name: 'Management', correlation: rawCorrelations.management || 0 },
    { name: 'Simplicity', correlation: rawCorrelations.simplicity || 0 },
    { name: 'Safety', correlation: rawCorrelations.marginOfSafety || 0 },
    { name: 'Composite', correlation: rawCorrelations.composite || 0 },
  ];

  const calibration = currentData.calibration || {};
  const rawPairs = currentData.rawPairs || [];

  // Group by runId for Sandbox Portfolio Calculation
  const runsMap = {};
  rawPairs.forEach(p => {
    if (!runsMap[p.runId]) {
      runsMap[p.runId] = {
        runId: p.runId,
        date: p.date || p.runId,
        pairs: []
      };
    }
    runsMap[p.runId].pairs.push(p);
  });

  const sortedRuns = Object.values(runsMap).sort((a, b) => new Date(a.date) - new Date(b.date));

  // Compute Growth Data using a non-overlapping rolling maturity model
  let portfolioValue = startingCapital;
  let benchmarkValue = startingCapital;
  const growthData = [];

  let nextAvailableDate = null;
  const horizonDays = parseInt(selectedHorizon);

  sortedRuns.forEach(run => {
    const runDate = new Date(run.date);

    // Reinvest only when the previous investment has reached maturity to prevent overlapping compounding
    if (nextAvailableDate === null || runDate >= nextAvailableDate) {
      let selectedPairs = [];
      if (allocMethod === 'top10') {
        selectedPairs = [...run.pairs].sort((a, b) => b.score - a.score).slice(0, 10);
      } else if (allocMethod === 'top5') {
        selectedPairs = [...run.pairs].sort((a, b) => b.score - a.score).slice(0, 5);
      } else if (allocMethod === 'threshold75') {
        selectedPairs = run.pairs.filter(p => p.score >= 7.5);
      } else if (allocMethod === 'threshold70') {
        selectedPairs = run.pairs.filter(p => p.score >= 7.0);
      }

      if (selectedPairs.length > 0) {
        const avgStockReturn = selectedPairs.reduce((sum, p) => sum + p.stockReturn, 0) / selectedPairs.length;
        const avgSpReturn = selectedPairs.reduce((sum, p) => sum + p.spReturn, 0) / selectedPairs.length;

        portfolioValue = portfolioValue * (1 + avgStockReturn);
        benchmarkValue = benchmarkValue * (1 + avgSpReturn);

        growthData.push({
          date: runDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' }),
          'Value Screener Portfolio': parseFloat(portfolioValue.toFixed(2)),
          'S&P 500 Index': parseFloat(benchmarkValue.toFixed(2)),
          portfolioReturn: avgStockReturn,
          benchmarkReturn: avgSpReturn
        });

        // Skip subsequent runs until this cohort matures
        const matureDate = new Date(runDate);
        matureDate.setDate(matureDate.getDate() + horizonDays);
        nextAvailableDate = matureDate;
      }
    }
  });

  // Calculate backtest performance statistics
  const totalRuns = growthData.length;
  const portfolioFinalValue = portfolioValue;
  const benchmarkFinalValue = benchmarkValue;
  const portfolioTotalReturn = totalRuns > 0 ? ((portfolioValue - startingCapital) / startingCapital) * 100 : 0;
  const benchmarkTotalReturn = totalRuns > 0 ? ((benchmarkValue - startingCapital) / startingCapital) * 100 : 0;
  const netAlpha = portfolioTotalReturn - benchmarkTotalReturn;

  const beatRunsCount = growthData.filter(d => d.portfolioReturn > d.benchmarkReturn).length;
  const portfolioBeatRate = totalRuns > 0 ? (beatRunsCount / totalRuns) * 100 : 0;

  // Spread Chart data calculation
  const topTierPairs = rawPairs.filter(p => p.score >= 7.5);
  const avoidTierPairs = rawPairs.filter(p => p.score < 5.0);
  const topAvgReturn = topTierPairs.reduce((sum, p) => sum + p.stockReturn, 0) / (topTierPairs.length || 1);
  const avoidAvgReturn = avoidTierPairs.reduce((sum, p) => sum + p.stockReturn, 0) / (avoidTierPairs.length || 1);
  const spAvgReturn = rawPairs.reduce((sum, p) => sum + p.spReturn, 0) / (rawPairs.length || 1);

  const spreadData = [
    { name: 'Top Tier (Score >= 7.5)', return: parseFloat((topAvgReturn * 100).toFixed(2)), count: topTierPairs.length },
    { name: 'S&P 500 Index', return: parseFloat((spAvgReturn * 100).toFixed(2)), count: rawPairs.length },
    { name: 'Avoid Tier (Score < 5.0)', return: parseFloat((avoidAvgReturn * 100).toFixed(2)), count: avoidTierPairs.length }
  ];

  // Group by Monthly Vintages
  const vintagesMap = {};
  rawPairs.forEach(p => {
    if (!p.date) return;
    const dateObj = new Date(p.date);
    const monthKey = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}`;
    if (!vintagesMap[monthKey]) {
      vintagesMap[monthKey] = {
        month: monthKey,
        pairs: []
      };
    }
    vintagesMap[monthKey].pairs.push(p);
  });

  const vintagesList = Object.values(vintagesMap).map(v => {
    // Unique top-rated stocks in that month's cohorts
    const uniquePairs = [];
    const seen = new Set();
    [...v.pairs]
      .sort((a, b) => b.score - a.score)
      .forEach(p => {
        if (!seen.has(p.ticker)) {
          seen.add(p.ticker);
          uniquePairs.push(p);
        }
      });

    const topCohort = uniquePairs.slice(0, 10);
    const avgStockReturn = topCohort.reduce((sum, p) => sum + p.stockReturn, 0) / (topCohort.length || 1);
    const avgSpReturn = topCohort.reduce((sum, p) => sum + p.spReturn, 0) / (topCohort.length || 1);

    // Find star pick (highest stock return)
    let starPick = 'N/A';
    let starReturn = -Infinity;
    topCohort.forEach(p => {
      if (p.stockReturn > starReturn) {
        starReturn = p.stockReturn;
        starPick = `${p.ticker} (+${(p.stockReturn * 100).toFixed(1)}%)`;
      }
    });

    // format month name
    const [year, monthNum] = v.month.split('-');
    const monthName = new Date(parseInt(year), parseInt(monthNum) - 1).toLocaleString('default', { month: 'long', year: 'numeric' });

    return {
      monthKey: v.month,
      monthName: monthName,
      avgReturn: avgStockReturn,
      spReturn: avgSpReturn,
      alpha: avgStockReturn - avgSpReturn,
      starPick: starPick,
      count: topCohort.length
    };
  }).sort((a, b) => b.monthKey.localeCompare(a.monthKey)); // Newest first

  const subTabStyle = (active) => ({
    padding: '10px 20px',
    border: 'none',
    borderBottom: active ? '3px solid #1A6B3C' : '3px solid transparent',
    backgroundColor: 'transparent',
    color: active ? '#1A6B3C' : '#5f6368',
    fontWeight: 'bold',
    fontSize: '0.95rem',
    cursor: 'pointer',
    transition: 'all 0.2s',
    outline: 'none'
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {/* Horizon Selector Header */}
      <div style={{ backgroundColor: 'white', padding: '1.2rem 1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ color: '#1A6B3C', margin: 0, fontSize: '1.5rem' }}>Forward-Return Validation</h2>
          <span style={{ fontSize: '0.8rem', color: '#666' }}>Last Updated: {validationData.updatedAt ? new Date(validationData.updatedAt).toLocaleString() : 'N/A'}</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {['30', '90', '365'].map(h => (
            <button
              key={h}
              onClick={() => setSelectedHorizon(h)}
              style={{
                padding: '8px 16px',
                border: '1px solid #1A6B3C',
                borderRadius: '4px',
                backgroundColor: selectedHorizon === h ? '#1A6B3C' : 'white',
                color: selectedHorizon === h ? 'white' : '#1A6B3C',
                fontWeight: 'bold',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              {h}-Day Horizon
            </button>
          ))}
        </div>
      </div>

      {/* Sub-Tab Navigation Bar */}
      <div style={{ display: 'flex', borderBottom: '1px solid #e0e0e0', gap: '1rem', marginTop: '-1rem' }}>
        <button onClick={() => setSubTab('predictive')} style={subTabStyle(subTab === 'predictive')}>
          📊 Predictive Accuracy
        </button>
        <button onClick={() => setSubTab('sandbox')} style={subTabStyle(subTab === 'sandbox')}>
          📈 Portfolio Simulator
        </button>
        <button onClick={() => setSubTab('vintages')} style={subTabStyle(subTab === 'vintages')}>
          🏆 Vintage Leaderboard
        </button>
      </div>

      {/* SUB-TAB 1: PREDICTIVE ACCURACY */}
      {subTab === 'predictive' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '2rem' }}>
            
            {/* Pearson Correlation Chart */}
            <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
              <h3 style={{ color: '#1A6B3C', margin: '0 0 1rem 0', fontSize: '1.2rem' }}>Excess Return Correlation</h3>
              <p style={{ fontSize: '0.85rem', color: '#666', marginBottom: '1.5rem' }}>
                Pearson correlation coefficient (\(r\)) between each score component and the stock's excess return vs. S&P 500. A positive value indicates the score successfully predicted outperformance.
              </p>
              
              <div style={{ height: '300px', width: '100%' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" interval={0} tick={{ fontSize: 10 }} />
                    <YAxis domain={[-1, 1]} tick={{ fontSize: 10 }} />
                    <Tooltip 
                      formatter={(value) => [value.toFixed(3), 'Pearson Correlation (r)']}
                      contentStyle={{ borderRadius: '8px', border: '1px solid #ccc' }}
                    />
                    <ReferenceLine y={0} stroke="#666" />
                    <Bar dataKey="correlation" fill="#2E8B57" radius={[4, 4, 0, 0]}>
                      {chartData.map((entry, index) => (
                        <Cell 
                          key={`cell-${index}`} 
                          fill={entry.correlation >= 0 ? '#1A6B3C' : '#d93025'} 
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Verdict Calibration Stats Card */}
            <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', display: 'flex', flexDirection: 'column' }}>
              <h3 style={{ color: '#1A6B3C', margin: '0 0 1rem 0', fontSize: '1.2rem' }}>Verdict Calibration</h3>
              <p style={{ fontSize: '0.85rem', color: '#666', marginBottom: '1.5rem' }}>
                Tracks how many stocks marked <strong>INVESTIGATE</strong> with <strong>HIGH</strong> confidence actually beat the S&P 500 over the {selectedHorizon}-day window.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', flexGrow: 1, justifyContent: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ fontSize: '0.9rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Outperformance Rate</span>
                  <div style={{ fontSize: '3.5rem', fontWeight: 'bold', color: calibration.investigateHighBeatRate >= 0.5 ? '#1A6B3C' : '#f29900', margin: '0.5rem 0' }}>
                    {(calibration.investigateHighBeatRate * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '0.85rem', color: '#555' }}>
                    Beat S&P 500 in <strong>{calibration.investigateHighBeatCount}</strong> of <strong>{calibration.investigateHighCount}</strong> matured high-confidence recommendations.
                  </div>
                </div>

                <div style={{ borderTop: '1px solid #eee', paddingTop: '1.5rem', display: 'flex', justifyContent: 'space-around', textAlign: 'center' }}>
                  <div>
                    <span style={{ fontSize: '0.8rem', color: '#666' }}>Total Matured Outcomes</span>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#333', marginTop: '4px' }}>
                      {currentData.count}
                    </div>
                  </div>
                  <div>
                    <span style={{ fontSize: '0.8rem', color: '#666' }}>Active recommendations</span>
                    <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#333', marginTop: '4px' }}>
                      {calibration.investigateHighCount}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Beat Rate by Score Tier Chart */}
          <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
            <h3 style={{ color: '#1A6B3C', margin: '0 0 1rem 0', fontSize: '1.2rem' }}>Beat Rate by Score Tier</h3>
            <p style={{ fontSize: '0.85rem', color: '#666', marginBottom: '1.5rem' }}>
              Measures the percentage of matured outcomes that outperformed the S&P 500 benchmark grouped by the composite score tier. A higher score tier should ideally correspond to a higher beat rate.
            </p>
            
            <div style={{ height: '260px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart 
                  data={(currentData.tiers || []).map(t => ({
                    name: t.name,
                    displayRate: (t.beatRate * 100),
                    count: t.count,
                    beatCount: t.beatCount
                  }))} 
                  margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 10 }} />
                  <Tooltip 
                    formatter={(value, name, props) => [`${value.toFixed(1)}% (Beat ${props.payload.beatCount} of ${props.payload.count} runs)`, 'Beat Rate']}
                    contentStyle={{ borderRadius: '8px', border: '1px solid #ccc' }}
                  />
                  <Bar dataKey="displayRate" fill="#1A6B3C" radius={[4, 4, 0, 0]} barSize={50}>
                    {(currentData.tiers || []).map((entry, index) => {
                      const rate = entry.beatRate * 100;
                      return (
                        <Cell 
                          key={`cell-${index}`} 
                          fill={rate >= 50 ? '#1A6B3C' : '#f29900'} 
                        />
                      );
                    })}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* SUB-TAB 2: PORTFOLIO BACKTEST SANDBOX */}
      {subTab === 'sandbox' && (
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
                    Compounds the average realized return of the selected picks run-by-run vs. the S&P 500 index. Prices automatically adjust for dividends, representing full dividend reinvestment.
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
      )}

      {/* SUB-TAB 3: COHORT VINTAGE PERFORMANCE LEADERBOARD */}
      {subTab === 'vintages' && (
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
                    {vintagesList.map((vintage) => (
                      <tr key={vintage.monthKey}>
                        <td style={{ fontWeight: '600' }}>{vintage.monthName}</td>
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
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
