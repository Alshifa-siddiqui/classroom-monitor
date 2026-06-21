# Deployment Guide

## 0. Prerequisites
- Python 3.12+, Node 20+, a camera (USB/built-in) or RTSP source.
- Production: a Linux host (camera passthrough), PostgreSQL 15+, a domain + TLS.

## 1. Local / single-machine run

```powershell
# Backend
cd backend
python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\download_models.py        # ~83 MB of ONNX/Caffe models
copy .env.example .env                    # edit secrets (see §3)
python -m uvicorn app.main:app --port 8000

# Frontend (second terminal)
cd frontend
copy .env.example .env
npm install
npm run dev                               # http://localhost:5173
```

Sign in `admin` / `admin123` (change before real use). To self-register as admin,
set `ADMIN_SIGNUP_CODE` in `backend/.env` and enter it in the signup form's
"Admin code" field.

## 2. Environment variables (production values)

| Var | Dev | Production |
|---|---|---|
| `PRODUCTION` | `false` | `true` (refuses default secrets) |
| `API_KEY` | `test-key-123` | `openssl rand -hex 24` (or disable legacy key) |
| `JWT_SECRET` | default | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `JWT_EXPIRES_MINUTES` | `480` | `480` (or lower) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin`/`admin123` | strong unique values |
| `ADMIN_SIGNUP_CODE` | optional | long random string, or empty to disable admin signup |
| `DATABASE_URL` | sqlite file | `postgresql+psycopg2://user:pass@host:5432/classroom` |
| `FRONTEND_ORIGIN` | localhost | `https://classroom.example.com` |
| `CAMERA_SOURCE` | `0` | device index or `rtsp://…` |
| `LOG_FORMAT` | `text` | `json` |
| `RATE_LIMIT_PER_MINUTE` / `LOGIN_RATE_LIMIT_PER_MINUTE` | `240`/`10` | tune to load |

Frontend build-time vars (`frontend/.env`): `VITE_API_URL`, `VITE_WS_URL` → the
backend's public HTTPS/WSS URL.

## 3. Database: SQLite → PostgreSQL
1. `pip install psycopg2-binary`.
2. Set `DATABASE_URL=postgresql+psycopg2://…`.
3. First boot runs `create_all` + additive column migration + student-code backfill
   against PostgreSQL (verify once on staging).
4. To carry existing data: `pgloader sqlite://backend/classroom.db postgresql://…`,
   then start the backend once to apply backfills. (Test data → start fresh is fine.)
5. **Backups:** nightly `pg_dump -Fc classroom`, retained off-host; back up before
   any schema change (`students` + `face_embeddings` are irreplaceable).

## 4. Production server (Docker Compose)

`backend/Dockerfile`:
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn psycopg2-binary
COPY app ./app
COPY scripts ./scripts
COPY models ./models
EXPOSE 8000
CMD ["gunicorn","app.main:app","-k","uvicorn.workers.UvicornWorker", \
     "-w","1","-b","0.0.0.0:8000","--timeout","120","--graceful-timeout","30"]
```
**Use `-w 1` per backend instance** — the pipeline, WS registry, rate limiters and
caches are in-process. Scale by running one instance *per camera/room*, not more
workers per instance. Camera passthrough (Linux host): `--device=/dev/video0`.

`frontend/Dockerfile` (multi-stage): `npm ci && npm run build` (with
`VITE_API_URL`/`VITE_WS_URL` build args) → serve `dist/` via Nginx.

## 5. Reverse proxy (Nginx) + HTTPS
```nginx
server {
  listen 443 ssl;
  server_name classroom.example.com;
  ssl_certificate     /etc/letsencrypt/live/classroom.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/classroom.example.com/privkey.pem;

  location /        { root /usr/share/nginx/html; try_files $uri /index.html; }
  location /api/    { proxy_pass http://backend:8000/; proxy_set_header Host $host; }
  location /live {                       # WebSocket — Upgrade headers required
    proxy_pass http://backend:8000/live;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
  }
}
```
TLS via Certbot (Let's Encrypt); redirect 80→443; WSS works automatically once
the page is HTTPS and the `/live` block carries the Upgrade headers.

## 6. Security hardening checklist
- [ ] `PRODUCTION=true`; real `JWT_SECRET`, `API_KEY`, `ADMIN_PASSWORD`.
- [ ] Decide on legacy API key: rotate it, or disable that path before launch.
- [ ] Pin `FRONTEND_ORIGIN` to the real domain; HTTPS/WSS only; enable HSTS.
- [ ] Keep `LOGIN_RATE_LIMIT_PER_MINUTE` low; set `ADMIN_SIGNUP_CODE` strong or empty.
- [ ] Confirm every route's role after configuration; verify `/ready` is all-`ok`.
- [ ] Enable `pg_dump` backups and log shipping.

## 7. Deployment sequence (zero → live)
1. Provision host + PostgreSQL; create DB/user.
2. Generate secrets; write production env.
3. Build backend image (bake `models/`) and frontend image (with build-time API URLs).
4. `docker compose up -d` (postgres, backend per camera with `--device`, nginx).
5. Issue TLS cert; enable the WSS proxy block; redirect 80→443.
6. First boot: confirm migration ran, admin seeded; `GET /ready` → all `ok`.
7. Smoke test: admin login → register student w/ account → enroll a real face →
   start session → confirm overlay + attendance → student login → portal →
   download CSV/PDF.
8. Enable backups + monitoring on `/health` and `/ready`. Go live.

## Scaling limits (current architecture)
- One backend process = one camera = one room. Multi-room = one instance per camera.
- In-memory WS/limiter/cache state → no horizontal scaling without Redis (out of scope).
- SQLite fine for a single room; PostgreSQL recommended for multi-room shared data.
