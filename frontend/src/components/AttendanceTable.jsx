import React from 'react';

const EMOTION_ICONS = {
  neutral: '😐', happy: '😊', distracted: '🙄', sleepy: '😴', bored: '🥱', absent: '∅',
};

export default function AttendanceTable({ students }) {
  if (!students.length) {
    return <div className="empty">No students detected yet</div>;
  }
  return (
    <table className="students-table">
      <thead>
        <tr>
          <th>Student</th>
          <th>ID</th>
          <th>Status</th>
          <th>Attention</th>
          <th>State</th>
          <th>Emotion</th>
          <th>ID conf.</th>
        </tr>
      </thead>
      <tbody>
        {students.map((s) => (
          <tr key={s.student_id} className={s.present ? '' : 'row-absent'}>
            <td>{s.name}</td>
            <td>{s.student_code || `#${s.student_id}`}</td>
            <td>
              <span className={`badge ${s.present ? 'present' : 'absent'}`}>
                {s.present ? 'Present' : 'Absent'}
              </span>
            </td>
            <td>
              <div className="meter">
                <div
                  className={`meter-fill att-${s.attention_label}`}
                  style={{ width: `${Math.round(s.attention * 100)}%` }}
                />
              </div>
              <span className="meter-num">{(s.attention * 100).toFixed(0)}%</span>
            </td>
            <td>{s.attention_label}</td>
            <td>{EMOTION_ICONS[s.emotion] ?? ''} {s.emotion}</td>
            <td>
              {typeof s.identity_confidence === 'number'
                ? `${(Math.min(s.identity_confidence, 1) * 100).toFixed(0)}%`
                : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
