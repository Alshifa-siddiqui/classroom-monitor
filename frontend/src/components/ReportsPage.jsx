import React, { useEffect, useState } from 'react';
import { api } from '../api';

const TYPES = [
  { value: 'attendance', label: 'Attendance' },
  { value: 'attention', label: 'Attention trends' },
  { value: 'emotion', label: 'Emotion trends' },
];

export default function ReportsPage({ pushToast }) {
  const [type, setType] = useState('attendance');
  const [period, setPeriod] = useState('daily');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [preview, setPreview] = useState(null);
  const [downloading, setDownloading] = useState('');

  useEffect(() => {
    let cancelled = false;
    api.reportJson(type, period, date)
      .then((data) => { if (!cancelled) setPreview(data); })
      .catch((e) => { if (!cancelled) { setPreview(null); pushToast(e.message, 'error'); } });
    return () => { cancelled = true; };
  }, [type, period, date]);

  const downloadAs = async (format) => {
    setDownloading(format);
    try {
      await api.downloadReport(type, period, date, format);
      pushToast(`${format.toUpperCase()} downloaded`);
    } catch (e) {
      pushToast(e.message, 'error');
    } finally {
      setDownloading('');
    }
  };

  return (
    <main>
      <div className="controls-row">
        <select value={type} onChange={(e) => setType(e.target.value)}>
          {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
        <select value={period} onChange={(e) => setPeriod(e.target.value)}>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </select>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        <button className="btn primary" disabled={downloading !== ''}
                onClick={() => downloadAs('csv')}>
          {downloading === 'csv' ? 'Preparing…' : 'Download CSV'}
        </button>
        <button className="btn primary" disabled={downloading !== ''}
                onClick={() => downloadAs('pdf')}>
          {downloading === 'pdf' ? 'Preparing…' : 'Download PDF'}
        </button>
      </div>

      <section className="panel wide">
        <h2>
          Preview{preview ? ` — ${preview.from} to ${preview.to} (${preview.rows.length} rows)` : ''}
        </h2>
        {!preview || preview.rows.length === 0 ? (
          <div className="empty">No data for this period</div>
        ) : (
          <table className="students-table">
            <thead>
              <tr>{preview.header.map((h) => <th key={h}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {preview.rows.slice(0, 100).map((row, i) => (
                <tr key={i}>{row.map((cell, j) => <td key={j}>{String(cell)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
