import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from 'recharts';
export default function ScoreCard({ scoreData }) {
  if (!scoreData) return null;

  const data = [
    { subject: 'Moat', A: scoreData.scoreMoat || 0, fullMark: 10 },
    { subject: 'Financial Health', A: scoreData.scoreFinancialHealth || 0, fullMark: 10 },
    { subject: 'Management', A: scoreData.scoreManagement || 0, fullMark: 10 },
    { subject: 'Simplicity', A: scoreData.scoreSimplicity || 0, fullMark: 10 },
    { subject: 'Margin of Safety', A: scoreData.scoreMarginOfSafety || 0, fullMark: 10 },
  ];

  const getVerdictColor = (verdict) => {
    if (verdict === 'INVESTIGATE') return '#1e8e3e';
    if (verdict === 'MONITOR') return '#f29900';
    return '#d93025';
  };

  return (
    <div style={{ backgroundColor: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)', display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
        <div>
          <h3 style={{ margin: 0, fontSize: '1.5rem', color: '#1A6B3C' }}>{scoreData.ticker}</h3>
          <p style={{ margin: '4px 0', fontSize: '0.9rem', color: '#666' }}>{scoreData.companyName}</p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '2rem', fontWeight: 'bold', color: getVerdictColor(scoreData.verdict) }}>
            {scoreData.compositeScore?.toFixed(1)}
          </div>
          <span style={{ 
            backgroundColor: getVerdictColor(scoreData.verdict) + '20', 
            color: getVerdictColor(scoreData.verdict),
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '0.75rem',
            fontWeight: 'bold'
          }}>
            {scoreData.verdict}
          </span>
        </div>
      </div>
      
      <p style={{ fontStyle: 'italic', fontSize: '0.85rem', color: '#555', flexGrow: 1 }}>
        "{scoreData.oneLineThesis}"
      </p>

      <div style={{ height: '250px', width: '100%', marginTop: '1rem' }}>
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
            <PolarGrid />
            <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10, fill: '#666' }} />
            <PolarRadiusAxis angle={30} domain={[0, 10]} tick={{ fontSize: 10 }} />
            <Radar name={scoreData.ticker} dataKey="A" stroke="#1A6B3C" fill="#1A6B3C" fillOpacity={0.4} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
