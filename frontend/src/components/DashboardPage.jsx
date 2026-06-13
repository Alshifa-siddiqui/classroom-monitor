import React, { useEffect, useMemo, useState } from 'react';
import { api, auth } from '../api';
import { useWebSocket } from '../useWebSocket';
import VideoPanel from './VideoPanel.jsx';
import StatCards from './StatCards.jsx';
import AttendanceTable from './AttendanceTable.jsx';
import AttentionChart from './AttentionChart.jsx';
import EmotionPie from './EmotionPie.jsx';
import AlertsPanel from './AlertsPanel.jsx';

export default function DashboardPage({ pushToast }) {
  const { connected, frame, analytics, liveAlerts } = useWebSocket(true);
  const [sessionActive, setSessionActive] = useState(false);
  const [sessionName, setSessionName] = useState('Morning Class');
  const [historical, setHistorical] = useState(null);
  const [studentFilter, setStudentFilter] = useState('all');
  const canControl = auth.hasRole('admin');

  const students = analytics?.students ?? [];
  const summary = analytics?.summary ?? {};

  const filteredStudents = useMemo(
    () => (studentFilter === 'all'
      ? students
      : students.filter((s) => String(s.student_id) === studentFilter)),
    [students, studentFilter]
  );

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const params = { minutes: 60 };
        if (studentFilter !== 'all') params.student_id = studentFilter;
        const data = await api.analytics(params);
        if (!cancelled) setHistorical(data);
      } catch (e) {
        if (!cancelled) pushToast(e.message, 'error');
      }
    };
    refresh();
    const id = setInterval(refresh, 10000);
    return () => { cancelled = true; clearInterval(id); };
  }, [studentFilter]);

  const handleStart = async () => {
    try {
      await api.startSession(sessionName || 'Session');
      setSessionActive(true);
      pushToast('Session started');
    } catch (e) {
      pushToast(e.message, 'error');
    }
  };

  const handleEnd = async () => {
    try {
      await api.endSession();
      setSessionActive(false);
      pushToast('Session ended — attendance saved. Open the Reports tab to download.');
    } catch (e) {
      pushToast(e.message, 'error');
    }
  };

  const cameraLive = connected && Boolean(frame);
  const presentCount = summary.present_count ?? 0;
  const absentCount = students.filter((s) => !s.present).length;

  return (
    <>
      <div className="controls-row session-bar">
        <span className={`status-chip ${connected ? 'ok' : 'bad'}`}>
          {connected ? '● Connected' : '○ Disconnected'}
        </span>
        <span className={`status-chip ${cameraLive ? 'ok' : 'idle'}`}>
          {cameraLive ? '🎥 Camera live' : '🎥 Camera off'}
        </span>
        <span className="status-chip idle">
          {cameraLive ? `${presentCount} in class` : 'No active session'}
        </span>
        {canControl && (
          <>
            <input
              value={sessionName}
              onChange={(e) => setSessionName(e.target.value)}
              placeholder="Session name"
              maxLength={120}
              disabled={sessionActive}
            />
            {sessionActive || cameraLive ? (
              <button className="btn danger" onClick={handleEnd}>■ End session</button>
            ) : (
              <button className="btn primary big" onClick={handleStart}>▶ Start session</button>
            )}
          </>
        )}
        <select value={studentFilter} onChange={(e) => setStudentFilter(e.target.value)}>
          <option value="all">All students</option>
          {students.map((s) => (
            <option key={s.student_id} value={String(s.student_id)}>{s.name}</option>
          ))}
        </select>
      </div>

      <StatCards summary={summary} totalAlerts={liveAlerts.length}
                 absentCount={absentCount} />

      <main className="grid">
        <section className="panel video">
          <h2>Live feed</h2>
          <VideoPanel frame={frame} active={sessionActive || Boolean(frame)} />
        </section>

        <section className="panel">
          <h2>Alerts</h2>
          <AlertsPanel liveAlerts={liveAlerts} />
        </section>

        <section className="panel">
          <h2>Attention over time</h2>
          <AttentionChart
            timeline={historical?.attention_timeline ?? []}
            liveAvg={summary.avg_attention}
          />
        </section>

        <section className="panel">
          <h2>Emotion distribution</h2>
          <EmotionPie
            live={summary.emotion_distribution}
            historical={historical?.emotion_distribution}
          />
        </section>

        <section className="panel wide">
          <h2>Students</h2>
          <AttendanceTable students={filteredStudents} />
        </section>
      </main>
    </>
  );
}
