import React, { useEffect, useState } from 'react';
import { api, auth } from '../api';
import ProfileView from './ProfileView.jsx';

export default function StudentsPage({ pushToast }) {
  const [students, setStudents] = useState([]);
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState(null); // {mode:'register'|'edit', student?}
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [busy, setBusy] = useState(false);
  const [enrollingId, setEnrollingId] = useState(null);
  const [profile, setProfile] = useState(null); // open profile drawer
  const canManage = auth.hasRole('admin');

  const refresh = async (term = search) => {
    try {
      setStudents(await api.students(term));
    } catch (e) {
      pushToast(e.message, 'error');
    }
  };

  useEffect(() => {
    const id = setTimeout(() => refresh(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  const openRegister = () => {
    setForm({ name: '', email: '', password: '' });
    setModal({ mode: 'register' });
  };
  const openEdit = (s) => {
    setForm({ name: s.name, email: '', password: '' });
    setModal({ mode: 'edit', student: s });
  };

  const openProfile = async (s) => {
    try {
      setProfile(await api.studentProfile(s.id));
    } catch (e) {
      pushToast(e.message, 'error');
    }
  };

  const enroll = async (studentId, studentName) => {
    setEnrollingId(studentId);
    pushToast(`Enrolling ${studentName} — face the camera…`, 'info');
    try {
      const r = await api.enrollStudent(studentId);
      pushToast(`Enrolled ${r.name}: ${r.samples_captured} samples `
                + `(quality ${(r.quality * 100).toFixed(0)}%)`);
      refresh();
    } catch (e) {
      pushToast(`Enrollment failed: ${e.message}`, 'error');
    } finally {
      setEnrollingId(null);
    }
  };

  const submitModal = async (e) => {
    e.preventDefault();
    if (modal.mode === 'register' && form.email && form.password.length < 8) {
      pushToast('Password must be at least 8 characters', 'error');
      return;
    }
    setBusy(true);
    try {
      if (modal.mode === 'register') {
        const created = await api.createStudent(
          form.name.trim(), form.email.trim(), form.password);
        pushToast(`Registered ${created.name} (${created.student_code})`);
        setModal(null);
        await refresh();
        await enroll(created.id, created.name);
      } else {
        await api.updateStudent(modal.student.id, form.name.trim());
        pushToast('Student updated');
        setModal(null);
        refresh();
      }
    } catch (err) {
      pushToast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (s) => {
    if (!window.confirm(`Delete ${s.name} and all their history? This cannot be undone.`)) {
      return;
    }
    try {
      await api.deleteStudent(s.id);
      pushToast(`Deleted ${s.name}`);
      refresh();
    } catch (e) {
      pushToast(e.message, 'error');
    }
  };

  return (
    <main>
      <div className="controls-row">
        <input placeholder="Search students…" value={search}
               onChange={(e) => setSearch(e.target.value)} maxLength={120} />
        {canManage && (
          <button className="btn primary" onClick={openRegister}>+ Register student</button>
        )}
      </div>

      <section className="panel wide">
        <h2>Registered students ({students.length})</h2>
        {students.length === 0 ? (
          <div className="empty">No students found</div>
        ) : (
          <table className="students-table">
            <thead>
              <tr>
                <th>Student ID</th>
                <th>Name</th>
                <th>Email</th>
                <th>Enrollment</th>
                <th>Account</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {students.map((s) => (
                <tr key={s.id}>
                  <td>{s.student_code || `#${s.id}`}</td>
                  <td>{s.name}</td>
                  <td>{s.email || '—'}</td>
                  <td>
                    <span className={`badge ${s.enrolled ? 'present' : 'absent'}`}>
                      {s.enrolled ? `Enrolled (${s.embedding_count})` : 'No face data'}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${s.has_account ? 'present' : 'absent'}`}>
                      {s.has_account ? 'Linked' : 'None'}
                    </span>
                  </td>
                  <td className="actions">
                    <button className="btn small" onClick={() => openProfile(s)}>Profile</button>
                    {canManage && (
                      <>
                        <button className="btn small" disabled={enrollingId !== null}
                                onClick={() => enroll(s.id, s.name)}>
                          {enrollingId === s.id ? 'Capturing…' : (s.enrolled ? 'Re-enroll' : 'Enroll face')}
                        </button>
                        <button className="btn small" onClick={() => openEdit(s)}>Rename</button>
                        <button className="btn small danger" onClick={() => remove(s)}>Delete</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {modal && (
        <div className="modal-backdrop" onClick={() => !busy && setModal(null)}>
          <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={submitModal}>
            <h3>{modal.mode === 'register' ? 'Register student' : `Rename ${modal.student.name}`}</h3>
            <label>
              Full name
              <input value={form.name}
                     onChange={(e) => setForm({ ...form, name: e.target.value })}
                     maxLength={120} required autoFocus />
            </label>
            {modal.mode === 'register' && (
              <>
                <label>
                  Email (optional — gives the student a login)
                  <input type="email" value={form.email}
                         onChange={(e) => setForm({ ...form, email: e.target.value })}
                         maxLength={120} />
                </label>
                {form.email && (
                  <label>
                    Password for the student account
                    <input type="password" value={form.password}
                           onChange={(e) => setForm({ ...form, password: e.target.value })}
                           maxLength={200} required minLength={8} />
                  </label>
                )}
                <p className="hint">A unique Student ID is generated automatically.
                  Face capture starts right after registration — the student should
                  face the camera.</p>
              </>
            )}
            <div className="modal-actions">
              <button type="button" className="btn" disabled={busy}
                      onClick={() => setModal(null)}>Cancel</button>
              <button type="submit" className="btn primary" disabled={busy || !form.name.trim()}>
                {busy ? 'Saving…' : (modal.mode === 'register' ? 'Register & enroll' : 'Save')}
              </button>
            </div>
          </form>
        </div>
      )}

      {profile && (
        <div className="modal-backdrop" onClick={() => setProfile(null)}>
          <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{profile.name} — {profile.student_code}</h3>
              <button className="btn small" onClick={() => setProfile(null)}>Close</button>
            </div>
            <ProfileView profile={profile} />
          </div>
        </div>
      )}
    </main>
  );
}
