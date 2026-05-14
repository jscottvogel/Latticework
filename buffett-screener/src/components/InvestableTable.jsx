import React, { useState } from 'react';
import './TableStyles.css';

export default function InvestableTable({ rollingScores }) {
  const [expandedRow, setExpandedRow] = useState(null);

  // Filter and sort
  const investable = rollingScores
    .filter(s => s.isInvestable)
    .sort((a, b) => b.avgCompositeScore - a.avgCompositeScore);

  const toggleRow = (ticker) => {
    setExpandedRow(expandedRow === ticker ? null : ticker);
  };

  const getAppearanceColor = (count) => {
    if (count === 4) return 'highlight-green';
    if (count === 3) return 'highlight-amber';
    return '';
  };

  return (
    <div className="table-container">
      <h2>Investable Candidates</h2>
      <p className="subtitle">Consistently in the top 20 for at least 3 of the last 4 weeks.</p>
      
      <table className="data-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Ticker</th>
            <th>Company</th>
            <th>Appearances</th>
            <th>Avg Score</th>
            <th>Inv. Count</th>
            <th>Latest Thesis</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {investable.length === 0 && (
            <tr><td colSpan="8" className="empty-state">No investable candidates currently.</td></tr>
          )}
          {investable.map((score, index) => (
            <React.Fragment key={score.ticker}>
              <tr onClick={() => toggleRow(score.ticker)} className="clickable-row">
                <td>#{index + 1}</td>
                <td className="fw-bold">{score.ticker}</td>
                <td>{score.companyName}</td>
                <td className={getAppearanceColor(score.appearancesLast4Weeks)}>
                  {score.appearancesLast4Weeks}/4
                </td>
                <td>{score.avgCompositeScore?.toFixed(1)}</td>
                <td>{score.investigateCount}</td>
                <td className="thesis-cell">{score.latestThesis}</td>
                <td>
                  <span className="badge badge-success">INVESTABLE</span>
                </td>
              </tr>
              {expandedRow === score.ticker && (
                <tr className="expanded-row">
                  <td colSpan="8">
                    <div className="expanded-content">
                      <div className="expanded-section">
                        <h4>Latest Verdict</h4>
                        <p>{score.latestVerdict || 'N/A'}</p>
                      </div>
                      <div className="expanded-section">
                        <h4>Last Seen</h4>
                        <p>{score.lastSeen}</p>
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
