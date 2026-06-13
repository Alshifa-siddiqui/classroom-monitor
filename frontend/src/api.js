// When served by the backend (production), VITE_API_URL is empty -> same origin,
// so the app works from any host/IP automatically. Dev keeps localhost:8000.
function defaultWs() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}`;
}
const API_URL = import.meta.env.VITE_API_URL ?? '';
const WS_BASE = import.meta.env.VITE_WS_URL || defaultWs();

const ROLE_LEVELS = { student: 0, viewer: 1, teacher: 2, admin: 3 };

let state = {
  token: localStorage.getItem('cm_token') || '',
  role: localStorage.getItem('cm_role') || '',
  username: localStorage.getItem('cm_user') || '',
};

export const auth = {
  get token() { return state.token; },
  get role() { return state.role; },
  get username() { return state.username; },
  isAuthed: () => Boolean(state.token),
  hasRole: (min) => (ROLE_LEVELS[state.role] || 0) >= (ROLE_LEVELS[min] || 99),
  async login(username, password) {
    const r = await request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
      skipAuth: true,
    });
    state = { token: r.token, role: r.role, username: r.username };
    localStorage.setItem('cm_token', r.token);
    localStorage.setItem('cm_role', r.role);
    localStorage.setItem('cm_user', r.username);
    return r;
  },
  logout() {
    state = { token: '', role: '', username: '' };
    localStorage.removeItem('cm_token');
    localStorage.removeItem('cm_role');
    localStorage.removeItem('cm_user');
  },
};

export function wsUrl() {
  return `${WS_BASE}/live?token=${encodeURIComponent(state.token)}`;
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (!options.skipAuth && state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, { ...options, headers });
  } catch {
    throw new Error(`Backend unreachable at ${API_URL} — is the server running?`);
  }
  if (res.status === 401 && !options.skipAuth) {
    auth.logout();
    window.dispatchEvent(new Event('cm-auth-expired'));
    throw new Error('Session expired — please log in again');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) return null;
  return res.json();
}

async function download(path, filename) {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${state.token}` },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Download failed (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  signup: async (username, password, adminCode = '') => {
    const body = { username, password };
    if (adminCode) body.admin_code = adminCode;
    const r = await request('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(body),
      skipAuth: true,
    });
    state = { token: r.token, role: r.role, username: r.username };
    localStorage.setItem('cm_token', r.token);
    localStorage.setItem('cm_role', r.role);
    localStorage.setItem('cm_user', r.username);
    return r;
  },
  users: () => request('/auth/users'),
  createUser: (username, password, role) =>
    request('/auth/users', { method: 'POST', body: JSON.stringify({ username, password, role }) }),
  changeUserRole: (id, role) =>
    request(`/auth/users/${id}`, { method: 'PUT', body: JSON.stringify({ role }) }),
  deleteUser: (id) => request(`/auth/users/${id}`, { method: 'DELETE' }),
  startSession: (name) => request('/start-session', { method: 'POST', body: JSON.stringify({ name }) }),
  endSession: () => request('/end-session', { method: 'POST' }),
  students: (search = '') =>
    request(`/students${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  createStudent: (name, email, password) =>
    request('/students', {
      method: 'POST',
      body: JSON.stringify(email ? { name, email, password } : { name }),
    }),
  studentProfile: (id) => request(`/students/${id}/profile`),
  myStudentProfile: () => request('/me/student'),
  updateStudent: (id, name) => request(`/students/${id}`, { method: 'PUT', body: JSON.stringify({ name }) }),
  deleteStudent: (id) => request(`/students/${id}`, { method: 'DELETE' }),
  enrollStudent: (id) => request(`/students/${id}/enroll`, { method: 'POST' }),
  attendance: (params = {}) => request(`/attendance?${new URLSearchParams(params)}`),
  analytics: (params = {}) => request(`/analytics?${new URLSearchParams(params)}`),
  trends: (from, to, bucket = 'day') =>
    request(`/analytics/trends?${new URLSearchParams({ from, to, bucket })}`),
  reportJson: (type, period, date) =>
    request(`/reports/${type}?${new URLSearchParams({ period, date, format: 'json' })}`),
  downloadReport: (type, period, date, format) =>
    download(`/reports/${type}?${new URLSearchParams({ period, date, format })}`,
             `${type}_${period}_${date}.${format}`),
};
