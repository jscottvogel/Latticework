import { useState, useEffect } from 'react';
import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import outputs from '../../amplify_outputs.json';

export default function ValidationPanel() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [validationData, setValidationData] = useState(null);
  const [selectedHorizon, setSelectedHorizon] = useState('90');

  useEffect(() => {
    async function fetchSummary() {
      const bucketName = outputs?.custom?.dataBucketName;
      if (!bucketName) {
        setError("S3 Bucket Name not found in configurations.");
        setLoading(false);
        return;
      }
      const url = `https://${bucketName}.s3.amazonaws.com/dashboard/validation_summary.json`;
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
      {/* Horizon Selector */}
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

      {/* Grid of Results */}
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

        {/* Calibration Stats Card */}
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
  );
}
