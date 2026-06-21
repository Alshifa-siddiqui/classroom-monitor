import React from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';

const EMOTION_ICONS = {
  neutral: '😐', happy: '😊', distracted: '🙄', sleepy: '😴', bored: '🥱',
};

export default function ProfileView({ profile }) {
  if (!profile) return <div className="empty">Loading profile…</div>;

  const attentionData = (profile.attention_history ?? []).map((p) => ({
    time: new Date(p.timestamp).toLocaleTimeString(),
    score: p.score,
  }));
  const emotionEntries = Object.entries(profile.emotion_stats ?? {});
  const emotionTotal = emotionEntries.reduce((sum, [, n]) => sum + n, 0);

  return (
    <div className="profile-view">
      <div className="stat-cards">
        <div className="card">
          <div className="card-value">{profile.student_code || '—'}</div>
          <div className="card-label">Student ID</div>
        </div>
        <div className="card">
          <div className="card-value">{profile.attendance_percentage}%</div>
          <div className="card-label">
            Attendance ({profile.sessions_attended}/{profile.total_sessions} sessions)
          </div>
        </div>
        <div className="card">
          <div className="card-value">{(profile.avg_attention * 100).toFixed(0)}%</div>
          <div className="card-label">Avg attention ({profile.attention_samples} samples)</div>
        </div>
        <div className="card">
          <div className="card-value">
            {profile.last_seen ? new Date(profile.last_seen).toLocaleString() : 'Never'}
          </div>
          <div className="card-label">Last seen</div>
        </div>
      </div>

      <section className="panel">
        <h2>Details</h2>
        <table className="students-table">
          <tbody>
            <tr><td>Name</td><td>{profile.name}</td></tr>
            <tr><td>Email</td><td>{profile.email || '—'}</td></tr>
            <tr>
              <td>Registered</td>
              <td>{profile.registered_at
                ? new Date(profile.registered_at).toLocaleString() : '—'}</td>
            </tr>
            <tr>
              <td>Face enrollment</td>
              <td>
                <span className={`badge ${profile.enrolled ? 'present' : 'absent'}`}>
                  {profile.enrolled ? 'Enrolled' : 'Not enrolled'}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2>Emotion statistics</h2>
        {emotionTotal === 0 ? <div className="empty">No emotion data yet</div> : (
          <table className="students-table">
            <tbody>
              {emotionEntries.map(([emotion, count]) => (
                <tr key={emotion}>
                  <td>{EMOTION_ICONS[emotion] ?? ''} {emotion}</td>
                  <td>{count}</td>
                  <td>{((count / emotionTotal) * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <h2>Recent attention</h2>
        {attentionData.length === 0 ? <div className="empty">No attention data yet</div> : (
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={attentionData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2f3a" />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#8b93a3' }} minTickGap={40} />
              <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#8b93a3' }} />
              <Tooltip contentStyle={{ background: '#1b1f29', border: '1px solid #2a2f3a' }}
                       formatter={(v) => [`${(v * 100).toFixed(0)}%`, 'Attention']} />
              <Line type="monotone" dataKey="score" stroke="#5b8def" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </section>

      <section className="panel">
        <h2>Attendance history</h2>
        {(profile.attendance_history ?? []).length === 0
          ? <div className="empty">No attendance records yet</div> : (
          <table className="students-table">
            <thead>
              <tr><th>Session</th><th>In</th><th>Out</th><th>Duration</th></tr>
            </thead>
            <tbody>
              {profile.attendance_history.map((r, i) => (
                <tr key={i}>
                  <td>#{r.session_id}</td>
                  <td>{new Date(r.timestamp_in).toLocaleString()}</td>
                  <td>{r.timestamp_out ? new Date(r.timestamp_out).toLocaleTimeString() : '—'}</td>
                  <td>{r.duration != null ? `${Math.round(r.duration / 60)}m ${r.duration % 60}s` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
