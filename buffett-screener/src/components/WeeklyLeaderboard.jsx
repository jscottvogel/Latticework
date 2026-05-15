import React, { useState } from 'react';
import './TableStyles.css';

export default function WeeklyLeaderboard({ stockScores }) {
  const [expandedRow, setExpandedRow] = useState(null);

  // Sort by composite score desc
  const sorted = [...stockScores].sort((a, b) => b.compositeScore - a.compositeScore);

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
      <h2>Weekly Leaderboard</h2>
      <p className="subtitle">Latest AI scoring and quantitative results.</p>
      
      <table className="data-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Ticker</th>
            <th>Company</th>
            <th>Score</th>
            <th>Moat</th>
            <th>Fin</th>
            <th>Mgmt</th>
            <th>Simp</th>
            <th>Safe</th>
            <th>Verdict</th>
            <th>MC Band</th>
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && (
            <tr><td colSpan="11" className="empty-state">No scores available for this week.</td></tr>
          )}
          {sorted.map((score, index) => (
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
