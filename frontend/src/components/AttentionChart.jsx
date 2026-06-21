import React, { useEffect, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

export default function AttentionChart({ timeline, liveAvg }) {
  const [livePoints, setLivePoints] = useState([]);

  useEffect(() => {
    if (typeof liveAvg !== 'number') return;
    setLivePoints((prev) => [
      ...prev,
      { time: new Date().toLocaleTimeString(), score: liveAvg },
    ].slice(-120));
  }, [liveAvg]);

  const data = livePoints.length
    ? livePoints
    : timeline.map((p) => ({
        time: new Date(p.timestamp).toLocaleTimeString(),
        score: p.avg_score,
      }));

  if (!data.length) {
    return <div className="empty">No attention data yet</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -18 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3a" />
        <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#8b93a3' }} minTickGap={40} />
        <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#8b93a3' }} />
        <Tooltip
          contentStyle={{ background: '#1b1f29', border: '1px solid #2a2f3a' }}
          formatter={(v) => [`${(v * 100).toFixed(0)}%`, 'Attention']}
        />
        <ReferenceLine y={0.7} stroke="#4caf7d" strokeDasharray="4 4" />
        <ReferenceLine y={0.4} stroke="#e05a5a" strokeDasharray="4 4" />
        <Line type="monotone" dataKey="score" stroke="#5b8def" dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}
