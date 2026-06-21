import React, { useEffect, useState } from 'react';
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis,
  Tooltip, CartesianGrid, Legend,
} from 'recharts';
import { api } from '../api';

const EMOTION_COLORS = {
  neutral: '#8b93a3', happy: '#4caf7d', distracted: '#e0a23a',
  sleepy: '#7b6cf0', bored: '#e05a5a',
};

function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function TrendsPage({ pushToast }) {
  const [from, setFrom] = useState(daysAgo(7));
  const [to, setTo] = useState(daysAgo(0));
  const [bucket, setBucket] = useState('day');
  const [trends, setTrends] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.trends(from, to, bucket)
      .then((data) => { if (!cancelled) setTrends(data); })
      .catch((e) => { if (!cancelled) pushToast(e.message, 'error'); });
    return () => { cancelled = true; };
  }, [from, to, bucket]);

  const emotionData = (trends?.emotions ?? []).map((p) => ({ bucket: p.bucket, ...p.counts }));
  const emotionKeys = [...new Set(emotionData.flatMap(
    (p) => Object.keys(p).filter((k) => k !== 'bucket')))];

  const tooltipStyle = { background: '#1b1f29', border: '1px solid #2a2f3a' };
  const tick = { fontSize: 10, fill: '#8b93a3' };

  return (
    <main>
      <div className="controls-row">
        <label className="inline">From
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="inline">To
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <select value={bucket} onChange={(e) => setBucket(e.target.value)}>
          <option value="day">Per day</option>
          <option value="hour">Per hour</option>
        </select>
      </div>

      <div className="stat-cards">
        <div className="card">
          <div className="card-value">
            {trends?.peak_attendance ? trends.peak_attendance.value : '—'}
          </div>
          <div className="card-label">
            Peak attendance {trends?.peak_attendance ? `(${trends.peak_attendance.bucket})` : ''}
          </div>
        </div>
        <div className="card">
          <div className="card-value">
            {trends?.most_distracted
              ? `${(trends.most_distracted.value * 100).toFixed(0)}%` : '—'}
          </div>
          <div className="card-label">
            Lowest attention {trends?.most_distracted ? `(${trends.most_distracted.bucket})` : ''}
          </div>
        </div>
      </div>

      <main className="grid">
        <section className="panel">
          <h2>Attendance trend</h2>
          {(trends?.attendance ?? []).length === 0 ? <div className="empty">No data</div> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={trends.attendance}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3a" />
                <XAxis dataKey="bucket" tick={tick} minTickGap={30} />
                <YAxis allowDecimals={false} tick={tick} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="value" name="Students present" fill="#5b8def" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </section>

        <section className="panel">
          <h2>Attention trend</h2>
          {(trends?.attention ?? []).length === 0 ? <div className="empty">No data</div> : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={trends.attention}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3a" />
                <XAxis dataKey="bucket" tick={tick} minTickGap={30} />
                <YAxis domain={[0, 1]} tick={tick} />
                <Tooltip contentStyle={tooltipStyle}
                         formatter={(v) => [`${(v * 100).toFixed(0)}%`, 'Attention']} />
                <Line type="monotone" dataKey="value" stroke="#4caf7d" dot strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </section>

        <section className="panel wide">
          <h2>Emotion trend</h2>
          {emotionData.length === 0 ? <div className="empty">No data</div> : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={emotionData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3a" />
                <XAxis dataKey="bucket" tick={tick} minTickGap={30} />
                <YAxis allowDecimals={false} tick={tick} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {emotionKeys.map((k) => (
                  <Bar key={k} dataKey={k} stackId="emotions"
                       fill={EMOTION_COLORS[k] || '#5b8def'} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          )}
        </section>
      </main>
    </main>
  );
}
