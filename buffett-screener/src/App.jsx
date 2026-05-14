import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import InvestableTable from './components/InvestableTable';
import WeeklyLeaderboard from './components/WeeklyLeaderboard';
import TrendChart from './components/TrendChart';
import ScoreCard from './components/ScoreCard';
import Footer from './components/Footer';
import './App.css';

// In Gen 2, if data client is set up:
// import { generateClient } from 'aws-amplify/data';
// const client = generateClient();

function App() {
  const [activeTab, setActiveTab] = useState('investable');
  const [loading, setLoading] = useState(true);
  const [weeklyRuns, setWeeklyRuns] = useState([]);
  const [stockScores, setStockScores] = useState([]);
  const [rollingScores, setRollingScores] = useState([]);
  const [trendData, setTrendData] = useState([]);
  
  useEffect(() => {
    // In a real scenario, fetch via AppSync:
    /*
    async function fetchData() {
      try {
        const { data: runs } = await client.models.WeeklyRun.list({ limit: 10 });
        const { data: scores } = await client.models.StockScore.list({ limit: 100 });
        const { data: rolling } = await client.models.RollingScore.list({ limit: 100 });
        // ... set state
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
    */

    // MOCK DATA FOR DEMO
    setTimeout(() => {
      setWeeklyRuns([{ runId: '2025-W03', totalCostUsd: 1.25, createdAt: new Date().toISOString() }]);
      setRollingScores([
        { ticker: 'AAPL', companyName: 'Apple Inc', appearancesLast4Weeks: 4, avgCompositeScore: 8.5, investigateCount: 4, isInvestable: true, latestThesis: 'Strong moat and FCF.', latestVerdict: 'INVESTIGATE', lastSeen: '2025-W03' },
        { ticker: 'MSFT', companyName: 'Microsoft Corp', appearancesLast4Weeks: 3, avgCompositeScore: 8.2, investigateCount: 3, isInvestable: true, latestThesis: 'Cloud growth continues.', latestVerdict: 'INVESTIGATE', lastSeen: '2025-W03' },
        { ticker: 'TSLA', companyName: 'Tesla Inc', appearancesLast4Weeks: 1, avgCompositeScore: 6.0, investigateCount: 0, isInvestable: false, latestThesis: 'Margin compression.', latestVerdict: 'MONITOR', lastSeen: '2025-W03' }
      ]);
      setStockScores([
        { ticker: 'AAPL', companyName: 'Apple Inc', scoreMoat: 9, scoreFinancialHealth: 9, scoreManagement: 8, scoreSimplicity: 8, scoreMarginOfSafety: 7, compositeScore: 8.5, verdict: 'INVESTIGATE', mcConfidenceBand: 'TIGHT', rankThisWeek: 1, oneLineThesis: 'Exceptional brand moat.', keyRisks: ['China exposure'], redFlags: [] },
        { ticker: 'MSFT', companyName: 'Microsoft Corp', scoreMoat: 9, scoreFinancialHealth: 8, scoreManagement: 9, scoreSimplicity: 7, scoreMarginOfSafety: 6, compositeScore: 8.2, verdict: 'INVESTIGATE', mcConfidenceBand: 'TIGHT', rankThisWeek: 2, oneLineThesis: 'Enterprise software dominance.', keyRisks: ['AI spend ROI'], redFlags: [] }
      ]);
      setTrendData([
        { week: '2025-W00', AAPL: 8.0, MSFT: 7.9 },
        { week: '2025-W01', AAPL: 8.1, MSFT: 8.0 },
        { week: '2025-W02', AAPL: 8.4, MSFT: 8.1 },
        { week: '2025-W03', AAPL: 8.5, MSFT: 8.2 }
      ]);
      setLoading(false);
    }, 1000);
  }, []);

  const latestRun = weeklyRuns[0];

  return (
    <div className="app-container">
      <Header 
        lastUpdated={latestRun?.createdAt ? new Date(latestRun.createdAt).toLocaleDateString() : null}
        runCost={latestRun?.totalCostUsd}
      />

      <main className="main-content">
        <div className="tabs">
          <button 
            className={`tab ${activeTab === 'investable' ? 'active' : ''}`}
            onClick={() => setActiveTab('investable')}
          >
            Investable
          </button>
          <button 
            className={`tab ${activeTab === 'thisWeek' ? 'active' : ''}`}
            onClick={() => setActiveTab('thisWeek')}
          >
            This Week
          </button>
          <button 
            className={`tab ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            History
          </button>
        </div>

        {loading ? (
          <div className="loading-spinner">Loading data...</div>
        ) : (
          <div className="tab-content">
            {activeTab === 'investable' && (
              <InvestableTable rollingScores={rollingScores} />
            )}
            
            {activeTab === 'thisWeek' && (
              <>
                <WeeklyLeaderboard stockScores={stockScores} />
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem' }}>
                  {stockScores.slice(0, 3).map(score => (
                    <ScoreCard key={score.ticker} scoreData={score} />
                  ))}
                </div>
              </>
            )}
            
            {activeTab === 'history' && (
              <TrendChart historyData={trendData} />
            )}
          </div>
        )}
      </main>
      <Footer />
    </div>
  );
}

export default App;
