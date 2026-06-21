import React from 'react';

const TYPE_LABELS = {
  low_attention: { label: 'Low attention', cls: 'warn' },
  absence: { label: 'Absence', cls: 'danger' },
  emotion: { label: 'Emotion', cls: 'info' },
};

export default function AlertsPanel({ liveAlerts }) {
  if (!liveAlerts.length) {
    return <div className="empty">No alerts</div>;
  }
  return (
    <ul className="alerts-list">
      {liveAlerts.map((a) => {
        const meta = TYPE_LABELS[a.type] || { label: a.type, cls: 'info' };
        return (
          <li key={a.id} className={`alert-item ${meta.cls}`}>
            <span className="alert-type">{meta.label}</span>
            <span className="alert-msg">{a.message}</span>
            <span className="alert-time">
              {new Date(a.timestamp).toLocaleTimeString()}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
