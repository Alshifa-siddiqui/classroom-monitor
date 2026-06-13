import React from 'react';

export default function StatCards({ summary, totalAlerts, absentCount = 0 }) {
  const avg = summary.avg_attention ?? 0;
  const label = avg >= 0.7 ? 'focused' : avg >= 0.4 ? 'partial' : 'distracted';
  return (
    <div className="stat-cards five">
      <div className="card">
        <div className="card-value">{summary.present_count ?? 0}</div>
        <div className="card-label">Present</div>
      </div>
      <div className="card">
        <div className="card-value">{absentCount}</div>
        <div className="card-label">Absent</div>
      </div>
      <div className={`card attention-${label}`}>
        <div className="card-value">{(avg * 100).toFixed(0)}%</div>
        <div className="card-label">Avg attention ({label})</div>
      </div>
      <div className="card">
        <div className="card-value">{summary.identifying_count ?? 0}</div>
        <div className="card-label">Identifying</div>
      </div>
      <div className="card">
        <div className="card-value">{totalAlerts}</div>
        <div className="card-label">Alerts this session</div>
      </div>
    </div>
  );
}
