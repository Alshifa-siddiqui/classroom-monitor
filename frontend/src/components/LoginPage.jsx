import React, { useState } from 'react';
import { auth, api } from '../api';

export default function LoginPage({ onLogin }) {
  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [adminCode, setAdminCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const switchMode = (m) => { setMode(m); setError(''); };

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (mode === 'signup') {
      if (password.length < 8) {
        setError('Password must be at least 8 characters');
        return;
      }
      if (password !== confirm) {
        setError('Passwords do not match');
        return;
      }
    }
    setBusy(true);
    try {
      const r = mode === 'login'
        ? await auth.login(username.trim(), password)
        : await api.signup(username.trim(), password, adminCode.trim());
      onLogin({ username: r.username, role: r.role });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <h1>Classroom Monitor</h1>
        <div className="auth-tabs">
          <button type="button"
                  className={`tab ${mode === 'login' ? 'active' : ''}`}
                  onClick={() => switchMode('login')}>Sign in</button>
          <button type="button"
                  className={`tab ${mode === 'signup' ? 'active' : ''}`}
                  onClick={() => switchMode('signup')}>Create account</button>
        </div>
        <label>
          Username or email
          <input value={username} onChange={(e) => setUsername(e.target.value)}
                 autoComplete="username" maxLength={60} required autoFocus />
        </label>
        <label>
          Password
          <input type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)}
                 autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                 maxLength={200} required />
        </label>
        {mode === 'signup' && (
          <>
            <label>
              Confirm password
              <input type="password" value={confirm}
                     onChange={(e) => setConfirm(e.target.value)}
                     autoComplete="new-password" maxLength={200} required />
            </label>
            <label>
              Admin code <span className="muted">(optional)</span>
              <input type="password" value={adminCode}
                     onChange={(e) => setAdminCode(e.target.value)}
                     autoComplete="off" maxLength={100}
                     placeholder="leave blank for a viewer account" />
            </label>
            <p className="hint">Without a code, new accounts start as <strong>viewer</strong>
              (dashboard only). Enter the admin code to create an <strong>admin</strong>
              account. An administrator can also change roles later.</p>
          </>
        )}
        {error && <div className="login-error">{error}</div>}
        <button className="btn primary" type="submit" disabled={busy}>
          {busy ? 'Please wait…' : (mode === 'login' ? 'Sign in' : 'Create account')}
        </button>
      </form>
    </div>
  );
}
