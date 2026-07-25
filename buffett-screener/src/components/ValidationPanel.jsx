import { useState, useEffect } from 'react';
import outputs from '../../amplify_outputs.json';
import PredictiveAccuracyTab from './PredictiveAccuracyTab';
import PortfolioSimulatorTab from './PortfolioSimulatorTab';
import VintageLeaderboardTab from './VintageLeaderboardTab';

export default function ValidationPanel() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [validationData, setValidationData] = useState(null);
  const [selectedHorizon, setSelectedHorizon] = useState('30');
  const [subTab, setSubTab] = useState('predictive'); // 'predictive', 'sandbox', 'vintages'
  const [expandedMonth, setExpandedMonth] = useState(null); // 'YYYY-MM'

  // Sandbox inputs
  const [startingCapital, setStartingCapital] = useState(10000);
  const [allocMethod, setAllocMethod] = useState('top10'); // 'top10', 'top5', 'threshold75', 'threshold70'

  useEffect(() => {
    setExpandedMonth(null);
  }, [selectedHorizon, subTab]);

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

  // Compute Growth Data using an equal-allocation cohort reinvestment model.
  // This simulates allocating a fixed portion of capital (10% of starting capital) 
  // to each run's picks, tracking the cumulative dollar gains chronologically.
  // This incorporates all runs and avoids sequential compounding overlaps.
  let portfolioValue = startingCapital;
  let benchmarkValue = startingCapital;
  const growthData = [];
  const allocationPerRun = startingCapital * 0.10;

  sortedRuns.forEach(run => {
    const runDate = new Date(run.date);
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

      // Dollar profit/loss from this run's allocation
      const runGain = allocationPerRun * avgStockReturn;
      const benchmarkGain = allocationPerRun * avgSpReturn;

      portfolioValue += runGain;
      benchmarkValue += benchmarkGain;

      growthData.push({
        date: runDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' }),
        'Value Screener Portfolio': parseFloat(portfolioValue.toFixed(2)),
        'S&P 500 Index': parseFloat(benchmarkValue.toFixed(2)),
        portfolioReturn: avgStockReturn,
        benchmarkReturn: avgSpReturn
      });
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
      count: topCohort.length,
      picks: topCohort
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
        <PredictiveAccuracyTab 
          chartData={chartData} 
          calibration={calibration} 
          selectedHorizon={selectedHorizon} 
          currentData={currentData} 
        />
      )}

      {/* SUB-TAB 2: PORTFOLIO BACKTEST SANDBOX */}
      {subTab === 'sandbox' && (
        <PortfolioSimulatorTab
          rawPairs={rawPairs}
          startingCapital={startingCapital}
          setStartingCapital={setStartingCapital}
          allocMethod={allocMethod}
          setAllocMethod={setAllocMethod}
          portfolioFinalValue={portfolioFinalValue}
          benchmarkFinalValue={benchmarkFinalValue}
          growthData={growthData}
          totalRuns={totalRuns}
          portfolioTotalReturn={portfolioTotalReturn}
          benchmarkTotalReturn={benchmarkTotalReturn}
          netAlpha={netAlpha}
          portfolioBeatRate={portfolioBeatRate}
          spreadData={spreadData}
        />
      )}

      {/* SUB-TAB 3: COHORT VINTAGE PERFORMANCE LEADERBOARD */}
      {subTab === 'vintages' && (
        <VintageLeaderboardTab
          vintagesList={vintagesList}
          selectedHorizon={selectedHorizon}
          expandedMonth={expandedMonth}
          setExpandedMonth={setExpandedMonth}
        />
      )}
    </div>
  );
}
