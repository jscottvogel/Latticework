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
