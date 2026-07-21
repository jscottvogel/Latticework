import { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import InvestableTable from './components/InvestableTable';
import WeeklyLeaderboard from './components/WeeklyLeaderboard';
import TrendChart from './components/TrendChart';
import ScoreCard from './components/ScoreCard';
import Footer from './components/Footer';
import ValidationPanel from './components/ValidationPanel';
import ThemeBaskets from './components/ThemeBaskets';
import './App.css';

import { generateClient } from 'aws-amplify/data';
import outputs from '../amplify_outputs.json';

const client = generateClient();

function App() {
  const [ activeTab, setActiveTab ] = useState( 'investable' );
  const [ loading, setLoading ] = useState( true );
  const [ isTriggering, setIsTriggering ] = useState( false );
  const [ weeklyRuns, setWeeklyRuns ] = useState( [] );
  const [ stockScores, setStockScores ] = useState( [] );
  const [ rollingScores, setRollingScores ] = useState( [] );
  const [ trendData, setTrendData ] = useState( [] );
  const [ selectedRunId, setSelectedRunId ] = useState( '' );
  const [ selectedRunScores, setSelectedRunScores ] = useState( [] );

  useEffect( () => {
    async function fetchData() {
      try {
        const { data: runs, errors: runErrs } = await client.models.WeeklyRun.list( { limit: 1000 } );
        const { data: rolling, errors: rollingErrs } = await client.models.RollingScore.list( { limit: 1000 } );

        const allErrs = [ ...( runErrs || [] ), ...( rollingErrs || [] ) ];
        if ( allErrs.length > 0 ) {
          console.error( 'GraphQL partial mapping errors (likely old corrupt records):', allErrs );
        }

        // Filter out null records that failed schema validation
        const validRuns = ( runs || [] ).filter( r => r !== null && r.createdAt );
        const validRolling = ( rolling || [] ).filter( r => r !== null && r.ticker && r.createdAt );

        // Sort runs by createdAt descending
        const sortedRuns = [ ...validRuns ].sort( ( a, b ) => new Date( b.createdAt ) - new Date( a.createdAt ) );

        // Fetch scores for the last 30 runs to build history
        let validScores = [];
        let historicalTrendData = [];

        // Filter runs that actually completed and have candidates scored for the history chart
        const completedRunsWithData = sortedRuns.filter( r => r.status === 'COMPLETE' && r.candidatesScored > 0 );

        if ( completedRunsWithData.length > 0 ) {
          const last30Runs = completedRunsWithData.slice( 0, 30 );

          const scoresPromises = last30Runs.map( run =>
            client.models.StockScore.list( {
              filter: { runId: { eq: run.runId } },
              limit: 1000
            } )
          );

          const scoresResults = await Promise.all( scoresPromises );

          // Latest valid scores are in the first result (since last4Runs[0] is the newest)
          validScores = ( scoresResults[ 0 ].data || [] ).filter( s => s !== null && s.ticker && s.createdAt );
          validScores.sort( ( a, b ) => ( b.compositeScore || 0 ) - ( a.compositeScore || 0 ) );

          // Get the top 10 tickers (excluding AVOID/INSUFFICIENT_DATA/CANNOT EVALUATE) from the latest run to track their trends
          const top10Tickers = validScores
            .filter( s => s.verdict === 'INVESTIGATE' || s.verdict === 'MONITOR' )
            .slice( 0, 10 )
            .map( s => s.ticker );

          // Build history data from oldest to newest (reverse order)
          historicalTrendData = last30Runs.slice().reverse().map( run => {
            const runDateStr = run.runDate || new Date( run.createdAt ).toLocaleDateString();
            const dataPoint = { week: runDateStr };

            const runIndex = last30Runs.findIndex( r => r.runId === run.runId );
            const runScores = scoresResults[ runIndex ].data || [];

            top10Tickers.forEach( ticker => {
              const scoreEntry = runScores.find( s => s.ticker === ticker );
              if ( scoreEntry && scoreEntry.compositeScore != null ) {
                dataPoint[ ticker ] = parseFloat( scoreEntry.compositeScore.toFixed( 2 ) );
              }
            } );

            return dataPoint;
          } );
        }

        setWeeklyRuns( sortedRuns );
        setStockScores( validScores );
        setRollingScores( validRolling );
        setTrendData( historicalTrendData );

        const latestCompletedRunId = completedRunsWithData[ 0 ]?.runId;
        if ( latestCompletedRunId && !selectedRunId ) {
          setSelectedRunId( latestCompletedRunId );
        }
      } catch ( err ) {
        console.error( 'Error fetching data:', err );
      } finally {
        setLoading( false );
      }
    }

    // Initial fetch
    fetchData();

    // Poll every 10 seconds to auto-update
    const interval = setInterval( fetchData, 10000 );
    return () => clearInterval( interval );
  }, [] );

  useEffect( () => {
    if ( !selectedRunId ) return;
    
    async function fetchSelectedScores() {
      try {
        const { data: scores } = await client.models.StockScore.list( {
          filter: { runId: { eq: selectedRunId } },
          limit: 1000
        } );
        const valid = ( scores || [] ).filter( s => s !== null && s.ticker && s.createdAt );
        valid.sort( ( a, b ) => ( b.compositeScore || 0 ) - ( a.compositeScore || 0 ) );
        setSelectedRunScores( valid );
      } catch ( err ) {
        console.error( "Error fetching scores for run", selectedRunId, err );
      }
    }
    
    fetchSelectedScores();
  }, [ selectedRunId, weeklyRuns ] );

  const handleRunNow = useCallback( async () => {
    const url = outputs?.custom?.orchestratorUrl;
    if ( !url ) {
      alert( "Orchestrator URL not found in config. Make sure the backend has been deployed." );
      return;
    }

    setIsTriggering( true );
    try {
      const headers = {};
      const triggerSecret = import.meta.env.VITE_TRIGGER_SECRET;
      if ( triggerSecret ) {
        headers[ 'X-Trigger-Secret' ] = triggerSecret;
      }
      const res = await fetch( url, {
        method: 'POST',
        headers: headers
      } );
      if ( res.ok ) {
        alert( "Pipeline triggered successfully! It may take several minutes to complete." );
      } else {
        alert( "Failed to trigger pipeline. Status: " + res.status );
      }
    } catch ( err ) {
      console.error( err );
      alert( "Error triggering pipeline." );
    } finally {
      setIsTriggering( false );
    }
  }, [] );

  const handlePrioritizeScan = useCallback( async ( ticker ) => {
    const url = outputs?.custom?.orchestratorUrl;
    if ( !url ) {
      alert( "Orchestrator URL not found in config." );
      return;
    }
    
    try {
      const headers = { 'Content-Type': 'application/json' };
      const triggerSecret = import.meta.env.VITE_TRIGGER_SECRET;
      if ( triggerSecret ) {
        headers[ 'X-Trigger-Secret' ] = triggerSecret;
      }
      
      const res = await fetch( url, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify( { prioritize_ticker: ticker } )
      } );
      
      if ( res.ok ) {
        alert( `Successfully prioritized ${ticker} for next daily screen!` );
      } else {
        const errData = await res.json();
        alert( `Failed to prioritize ${ticker}: ${errData.error || errData.reason || res.statusText}` );
      }
    } catch ( err ) {
      console.error( err );
      alert( `Error prioritizing ${ticker}` );
    }
  }, [] );

  // Expose to window for console execution
  useEffect( () => {
    window.runBuffettPipeline = handleRunNow;
    return () => {
      delete window.runBuffettPipeline;
    };
  }, [ handleRunNow ] );

  const latestRun = weeklyRuns.find( r => r.status === 'COMPLETE' );

  return (
    <div className="app-container">
      <Header
        lastUpdated={ latestRun?.createdAt ? new Date( latestRun.createdAt ).toLocaleDateString() : null }
        runCost={ latestRun?.totalCostUsd }
        universeCoverage={ latestRun?.universeCoveragePct }
        screenedCumulative={ latestRun?.stocksScreenedCumulative }
        onRunNow={ handleRunNow }
        isTriggering={ isTriggering }
      />

      <main className="main-content">
        <div className="tabs">
          <button
            className={ `tab ${ activeTab === 'investable' ? 'active' : '' }` }
            onClick={ () => setActiveTab( 'investable' ) }
          >
            Investable
          </button>
          <button
            className={ `tab ${ activeTab === 'thisWeek' ? 'active' : '' }` }
            onClick={ () => setActiveTab( 'thisWeek' ) }
          >
            Latest Run
          </button>
          <button
            className={ `tab ${ activeTab === 'history' ? 'active' : '' }` }
            onClick={ () => setActiveTab( 'history' ) }
          >
            History
          </button>
          <button
            className={ `tab ${ activeTab === 'validation' ? 'active' : '' }` }
            onClick={ () => setActiveTab( 'validation' ) }
          >
            Validation
          </button>
          <button
            className={ `tab ${ activeTab === 'themes' ? 'active' : '' }` }
            onClick={ () => setActiveTab( 'themes' ) }
          >
            Themes
          </button>
        </div>

        { loading ? (
          <div className="loading-spinner">Loading data...</div>
        ) : (
          <div className="tab-content">
            { activeTab === 'investable' && (
              <InvestableTable rollingScores={ rollingScores } onPrioritize={ handlePrioritizeScan } />
            ) }

            { activeTab === 'thisWeek' && (
              <>
                <div style={{ backgroundColor: 'white', padding: '1rem 1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                  <div>
                    <h3 style={{ margin: 0, color: '#1A6B3C' }}>Historical Run Selector</h3>
                    <span style={{ fontSize: '0.8rem', color: '#666' }}>Browse components and details of any past pipeline execution.</span>
                  </div>
                  <div>
                    <label htmlFor="run-select" style={{ marginRight: '8px', fontWeight: 'bold', fontSize: '0.9rem', color: '#333' }}>Select Run: </label>
                    <select
                      id="run-select"
                      value={selectedRunId}
                      onChange={(e) => setSelectedRunId(e.target.value)}
                      style={{ padding: '6px 12px', border: '1px solid #1A6B3C', borderRadius: '4px', fontSize: '0.9rem', outline: 'none', cursor: 'pointer' }}
                    >
                      {weeklyRuns
                        .filter(r => r.status === 'COMPLETE' && r.candidatesScored > 0)
                        .map(r => {
                          const dateStr = r.runDate || new Date(r.createdAt).toLocaleDateString();
                          return (
                            <option key={r.runId} value={r.runId}>
                              {dateStr} ({r.runId})
                            </option>
                          );
                        })}
                    </select>
                  </div>
                </div>

                <WeeklyLeaderboard stockScores={ selectedRunScores } onPrioritize={ handlePrioritizeScan } />
                <div style={ { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem' } }>
                  { selectedRunScores
                    .filter( s => s.verdict === 'INVESTIGATE' || s.verdict === 'MONITOR' )
                    .slice( 0, 3 )
                    .map( score => (
                      <ScoreCard key={ score.ticker } scoreData={ score } />
                    ) )
                  }
                </div>
              </>
            ) }

            { activeTab === 'history' && (
              <TrendChart historyData={ trendData } />
            ) }

            { activeTab === 'validation' && (
              <ValidationPanel />
            ) }

            { activeTab === 'themes' && (
              <ThemeBaskets onPrioritize={ handlePrioritizeScan } />
            ) }
          </div>
        ) }
      </main>
      <Footer />
    </div>
  );
}

export default App;
