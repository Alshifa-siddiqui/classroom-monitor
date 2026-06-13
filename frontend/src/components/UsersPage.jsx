import React, { useEffect, useState } from 'react';
import { api, auth } from '../api';

const ROLES = ['viewer', 'teacher', 'admin'];

export default function UsersPage({ pushToast }) {
  const [users, setUsers] = useState([]);

  const refresh = async () => {
    try {
      setUsers(await api.users());
    } catch (e) {
      pushToast(e.message, 'error');
    }
  };

  useEffect(() => { refresh(); }, []);

  const changeRole = async (u, role) => {
    try {
      await api.changeUserRole(u.id, role);
      pushToast(`${u.username} is now ${role}`);
      refresh();
    } catch (e) {
      pushToast(e.message, 'error');
    }
  };

  const remove = async (u) => {
    if (!window.confirm(`Delete account ${u.username}?`)) return;
    try {
      await api.deleteUser(u.id);
      pushToast(`Deleted ${u.username}`);
      refresh();
    } catch (e) {
      pushToast(e.message, 'error');
    }
  };

  return (
    <main>
      <section className="panel wide">
        <h2>User accounts ({users.length})</h2>
        <p className="hint">New self-registered accounts start as viewer.
          Promote them to teacher or admin here.</p>
        <table className="students-table">
          <thead>
            <tr><th>ID</th><th>Username</th><th>Role</th><th>Created</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td>{u.username}{u.username === auth.username ? ' (you)' : ''}</td>
                <td>
                  <select value={u.role} disabled={u.username === auth.username}
                          onChange={(e) => changeRole(u, e.target.value)}>
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
                <td>{new Date(u.created_at).toLocaleDateString()}</td>
                <td className="actions">
                  <button className="btn small danger"
                          disabled={u.username === auth.username}
                          onClick={() => remove(u)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
