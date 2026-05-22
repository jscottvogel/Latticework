import { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import InvestableTable from './components/InvestableTable';
import WeeklyLeaderboard from './components/WeeklyLeaderboard';
import TrendChart from './components/TrendChart';
import ScoreCard from './components/ScoreCard';
import Footer from './components/Footer';
import './App.css';

import { generateClient } from 'aws-amplify/data';
import outputs from '../amplify_outputs.json';

const client = generateClient();

function App() {
  const [activeTab, setActiveTab] = useState('investable');
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const [weeklyRuns, setWeeklyRuns] = useState([]);
  const [stockScores, setStockScores] = useState([]);
  const [rollingScores, setRollingScores] = useState([]);
  const [trendData, setTrendData] = useState([]);
  
  useEffect(() => {
    async function fetchData() {
      try {
        const { data: runs, errors: runErrs } = await client.models.WeeklyRun.list({ limit: 1000 });
        const { data: rolling, errors: rollingErrs } = await client.models.RollingScore.list({ limit: 1000 });
        
        const allErrs = [...(runErrs || []), ...(rollingErrs || [])];
        if (allErrs.length > 0) {
          console.error('GraphQL partial mapping errors (likely old corrupt records):', allErrs);
        }
        
        // Filter out null records that failed schema validation
        const validRuns = (runs || []).filter(r => r !== null && r.createdAt);
        const validRolling = (rolling || []).filter(r => r !== null && r.ticker && r.createdAt);

        // Sort runs by createdAt descending
        const sortedRuns = [...validRuns].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
        
        // Fetch scores for the last 4 runs to build history
        let validScores = [];
        let historicalTrendData = [];

        if (sortedRuns.length > 0) {
          const last4Runs = sortedRuns.slice(0, 4);
          
          const scoresPromises = last4Runs.map(run => 
            client.models.StockScore.list({ 
              filter: { runId: { eq: run.runId } },
              limit: 1000 
            })
          );
          
          const scoresResults = await Promise.all(scoresPromises);
          
          // Latest valid scores are in the first result (since last4Runs[0] is the newest)
          validScores = (scoresResults[0].data || []).filter(s => s !== null && s.ticker && s.createdAt);
          validScores.sort((a, b) => (b.compositeScore || 0) - (a.compositeScore || 0));
          
          // Get the top 10 tickers from the latest run to track their trends
          const top10Tickers = validScores.slice(0, 10).map(s => s.ticker);
          
          // Build history data from oldest to newest (reverse order)
          historicalTrendData = last4Runs.slice().reverse().map(run => {
            const runDateStr = run.runDate || new Date(run.createdAt).toLocaleDateString();
            const dataPoint = { week: runDateStr };
            
            const runIndex = last4Runs.findIndex(r => r.runId === run.runId);
            const runScores = scoresResults[runIndex].data || [];
            
            top10Tickers.forEach(ticker => {
              const scoreEntry = runScores.find(s => s.ticker === ticker);
              if (scoreEntry && scoreEntry.compositeScore != null) {
                dataPoint[ticker] = parseFloat(scoreEntry.compositeScore.toFixed(2));
              }
            });
            
            return dataPoint;
          });
        }

        setWeeklyRuns(sortedRuns);
        setStockScores(validScores);
        setRollingScores(validRolling);
        setTrendData(historicalTrendData);
      } catch (err) {
        console.error('Error fetching data:', err);
      } finally {
        setLoading(false);
      }
    }
    
    // Initial fetch
    fetchData();
    
    // Poll every 10 seconds to auto-update
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleRunNow = useCallback(async () => {
    const url = outputs?.custom?.orchestratorUrl;
    if (!url) {
      alert("Orchestrator URL not found in config. Make sure the backend has been deployed.");
      return;
    }
    
    setIsTriggering(true);
    try {
      const res = await fetch(url, { method: 'POST' });
      if (res.ok) {
        alert("Pipeline triggered successfully! It may take several minutes to complete.");
      } else {
        alert("Failed to trigger pipeline. Status: " + res.status);
      }
    } catch (err) {
      console.error(err);
      alert("Error triggering pipeline.");
    } finally {
      setIsTriggering(false);
    }
  }, []);

  // Expose to window for console execution
  useEffect(() => {
    window.runBuffettPipeline = handleRunNow;
    return () => {
      delete window.runBuffettPipeline;
    };
  }, [handleRunNow]);

  const latestRun = weeklyRuns[0];

  return (
    <div className="app-container">
      <Header 
        lastUpdated={latestRun?.createdAt ? new Date(latestRun.createdAt).toLocaleDateString() : null}
        runCost={latestRun?.totalCostUsd}
        onRunNow={handleRunNow}
        isTriggering={isTriggering}
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
            Latest Run
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
