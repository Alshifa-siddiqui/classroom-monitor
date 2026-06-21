import React from 'react';
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const COLORS = {
  neutral: '#8b93a3',
  happy: '#4caf7d',
  distracted: '#e0a23a',
  sleepy: '#7b6cf0',
  bored: '#e05a5a',
};

export default function EmotionPie({ live, historical }) {
  // prefer the cumulative session distribution; the instantaneous live
  // snapshot only has one entry per student and makes a degenerate pie
  const source = historical && Object.keys(historical).length ? historical : live || {};
  const data = Object.entries(source)
    .filter(([k]) => k !== 'absent')
    .map(([name, value]) => ({ name, value }));

  if (!data.length) {
    return <div className="empty">No emotion data yet</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={45}
             outerRadius={75} paddingAngle={2}>
          {data.map((entry) => (
            <Cell key={entry.name} fill={COLORS[entry.name] || '#5b8def'} />
          ))}
        </Pie>
        <Tooltip contentStyle={{ background: '#1b1f29', border: '1px solid #2a2f3a' }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
