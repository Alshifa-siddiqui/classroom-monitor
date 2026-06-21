import React, { useCallback, useEffect, useRef, useState } from 'react';
import { auth } from './api';
import LoginPage from './components/LoginPage.jsx';
import DashboardPage from './components/DashboardPage.jsx';
import StudentsPage from './components/StudentsPage.jsx';
import ReportsPage from './components/ReportsPage.jsx';
import TrendsPage from './components/TrendsPage.jsx';
import UsersPage from './components/UsersPage.jsx';
import StudentPortal from './components/StudentPortal.jsx';
import Toasts from './components/Toasts.jsx';

const TABS = [
  { id: 'dashboard', label: 'Dashboard', minRole: 'viewer' },
  { id: 'students', label: 'Students', minRole: 'teacher' },
  { id: 'reports', label: 'Reports', minRole: 'teacher' },
  { id: 'analytics', label: 'Analytics', minRole: 'teacher' },
  { id: 'users', label: 'Users', minRole: 'admin' },
];

export default function App() {
  const [user, setUser] = useState(
    auth.isAuthed() ? { username: auth.username, role: auth.role } : null
  );
  const [tab, setTab] = useState('dashboard');
  const [toasts, setToasts] = useState([]);
  const toastId = useRef(0);

  const pushToast = useCallback((message, kind = 'success') => {
    const id = ++toastId.current;
    setToasts((prev) => [...prev, { id, message, kind }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 5000);
  }, []);

  useEffect(() => {
    const onExpired = () => { setUser(null); };
    window.addEventListener('cm-auth-expired', onExpired);
    return () => window.removeEventListener('cm-auth-expired', onExpired);
  }, []);

  if (!user) {
    return <LoginPage onLogin={(u) => { setUser(u); setTab('dashboard'); }} />;
  }

  const visibleTabs = TABS.filter((t) => auth.hasRole(t.minRole));
  const logout = () => { auth.logout(); setUser(null); };
  const isStudent = user.role === 'student';

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-nav">
          <h1>Classroom Monitor</h1>
          {!isStudent && (
            <nav className="tabs">
              {visibleTabs.map((t) => (
                <button key={t.id}
                        className={`tab ${tab === t.id ? 'active' : ''}`}
                        onClick={() => setTab(t.id)}>
                  {t.label}
                </button>
              ))}
            </nav>
          )}
        </div>
        <div className="user-box">
          <span className="user-badge">{user.username} · {user.role}</span>
          <button className="btn small" onClick={logout}>Sign out</button>
        </div>
      </header>

      {isStudent && <StudentPortal pushToast={pushToast} />}
      {!isStudent && tab === 'dashboard' && <DashboardPage pushToast={pushToast} />}
      {tab === 'students' && auth.hasRole('teacher') && <StudentsPage pushToast={pushToast} />}
      {tab === 'reports' && auth.hasRole('teacher') && <ReportsPage pushToast={pushToast} />}
      {tab === 'analytics' && auth.hasRole('teacher') && <TrendsPage pushToast={pushToast} />}
      {tab === 'users' && auth.hasRole('admin') && <UsersPage pushToast={pushToast} />}

      <Toasts toasts={toasts} />
    </div>
  );
}
