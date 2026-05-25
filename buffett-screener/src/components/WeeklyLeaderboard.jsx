import React, { useState } from 'react';
import './TableStyles.css';

export default function WeeklyLeaderboard({ stockScores }) {
  const [expandedRow, setExpandedRow] = useState(null);
  const [filterType, setFilterType] = useState('active'); // 'active' (default) or 'all'
  const [searchTerm, setSearchTerm] = useState('');

  // Sort by composite score desc
  const sorted = [...stockScores].sort((a, b) => b.compositeScore - a.compositeScore);

  // Search and filter logic
  const filtered = sorted.filter(score => {
    const matchesSearch = 
      score.ticker.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (score.companyName && score.companyName.toLowerCase().includes(searchTerm.toLowerCase()));
      
    const matchesFilter = 
      filterType === 'all' || 
      score.verdict === 'INVESTIGATE' || 
      score.verdict === 'MONITOR';
      
    return matchesSearch && matchesFilter;
  });

  const toggleRow = (ticker) => {
    setExpandedRow(expandedRow === ticker ? null : ticker);
  };

  const getVerdictBadge = (verdict) => {
    if (verdict === 'INVESTIGATE') return 'badge-success';
    if (verdict === 'MONITOR') return 'badge-warning';
    return 'badge-danger';
  };

  const getBandClass = (band) => {
    if (band === 'TIGHT') return 'pill tight';
    if (band === 'MODERATE') return 'pill moderate';
    return 'pill wide';
  };

  return (
    <div className="table-container">
      <h2>Daily Leaderboard</h2>
      <p className="subtitle">Latest AI scoring and quantitative results.</p>
      
      {/* Premium Search and Filtering Controls */}
      <div className="table-controls" style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        marginBottom: '1.5rem', 
        gap: '1rem', 
        flexWrap: 'wrap' 
      }}>
        <div className="search-wrapper" style={{ position: 'relative', flexGrow: 1, maxWidth: '300px' }}>
          <input 
            type="text" 
            placeholder="Search ticker or company..." 
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              padding: '10px 16px 10px 38px',
              borderRadius: '24px',
              border: '1px solid #e0e0e0',
              fontSize: '0.9rem',
              outline: 'none',
              transition: 'all 0.2s ease',
              boxSizing: 'border-box',
              backgroundColor: '#f8f9fa'
            }}
            onFocus={(e) => {
              e.target.style.borderColor = '#1A6B3C';
              e.target.style.backgroundColor = '#ffffff';
              e.target.style.boxShadow = '0 0 0 3px rgba(26, 107, 60, 0.1)';
            }}
            onBlur={(e) => {
              e.target.style.borderColor = '#e0e0e0';
              e.target.style.backgroundColor = '#f8f9fa';
              e.target.style.boxShadow = 'none';
            }}
          />
          <span style={{ 
            position: 'absolute', 
            left: '14px', 
            top: '50%', 
            transform: 'translateY(-50%)', 
            color: '#888',
            fontSize: '1.1rem',
            pointerEvents: 'none'
          }}>
            🔍
          </span>
        </div>
        
        <div className="filter-buttons" style={{ 
          display: 'flex', 
          gap: '4px', 
          backgroundColor: '#f1f3f4', 
          padding: '4px', 
          borderRadius: '24px' 
        }}>
          <button 
            onClick={() => setFilterType('active')}
            style={{
              padding: '8px 16px',
              borderRadius: '20px',
              border: 'none',
              cursor: 'pointer',
              fontSize: '0.85rem',
              fontWeight: '600',
              backgroundColor: filterType === 'active' ? '#1A6B3C' : 'transparent',
              color: filterType === 'active' ? 'white' : '#5f6368',
              transition: 'all 0.2s ease'
            }}
          >
            Investigate & Monitor
          </button>
          <button 
            onClick={() => setFilterType('all')}
            style={{
              padding: '8px 16px',
              borderRadius: '20px',
              border: 'none',
              cursor: 'pointer',
              fontSize: '0.85rem',
              fontWeight: '600',
              backgroundColor: filterType === 'all' ? '#1A6B3C' : 'transparent',
              color: filterType === 'all' ? 'white' : '#5f6368',
              transition: 'all 0.2s ease'
            }}
          >
            All Screened ({sorted.length})
          </button>
        </div>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th title="Current position on the leaderboard based on composite score">Rank</th>
            <th title="Stock ticker symbol">Ticker</th>
            <th title="Company name">Company</th>
            <th title="Overall AI-generated composite score">Score</th>
            <th title="Economic Moat score: Does the company have a durable competitive advantage?">Moat</th>
            <th title="Financial Health score: Are the financials strong and debt manageable?">Fin</th>
            <th title="Management Quality score: Is management competent and shareholder-friendly?">Mgmt</th>
            <th title="Business Simplicity score: Is the business simple and easy to understand?">Simp</th>
            <th title="Margin of Safety score: Is the stock undervalued compared to intrinsic value?">Safe</th>
            <th title="Final AI verdict recommendation (e.g., INVESTIGATE, MONITOR, AVOID)">Verdict</th>
            <th title="Monte Carlo Confidence Band: Indicates the tightness/certainty of simulated outcomes (Tight, Moderate, Wide)">MC Band</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 && (
            <tr><td colSpan="11" className="empty-state">No matching scores found.</td></tr>
          )}
          {filtered.map((score, index) => (
            <React.Fragment key={score.ticker}>
              <tr onClick={() => toggleRow(score.ticker)} className="clickable-row">
                <td>#{index + 1}</td>
                <td className="fw-bold">{score.ticker}</td>
                <td>{score.companyName}</td>
                <td className="fw-bold highlight-green">{score.compositeScore?.toFixed(1)}</td>
                <td>{score.scoreMoat}</td>
                <td>{score.scoreFinancialHealth}</td>
                <td>{score.scoreManagement}</td>
                <td>{score.scoreSimplicity}</td>
                <td>{score.scoreMarginOfSafety}</td>
                <td>
                  <span className={`badge ${getVerdictBadge(score.verdict)}`}>
                    {score.verdict}
                  </span>
                </td>
                <td>
                  <span className={getBandClass(score.mcConfidenceBand)}>
                    {score.mcConfidenceBand || 'N/A'}
                  </span>
                </td>
              </tr>
              {expandedRow === score.ticker && (
                <tr className="expanded-row">
                  <td colSpan="11">
                    <div className="expanded-content">
                      <div className="expanded-section" style={{ gridColumn: 'span 2' }}>
                        <h4>One Line Thesis</h4>
                        <p>{score.oneLineThesis}</p>
                      </div>
                      <div className="expanded-section">
                        <h4>Key Risks</h4>
                        <ul>
                          {score.keyRisks?.map((r, i) => <li key={i}>{r}</li>) || <li>None</li>}
                        </ul>
                      </div>
                      <div className="expanded-section">
                        <h4>Red Flags</h4>
                        <ul style={{ color: '#d93025' }}>
                          {score.redFlags?.map((r, i) => <li key={i}>{r}</li>) || <li>None</li>}
                        </ul>
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
