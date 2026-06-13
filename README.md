# Real-Time AI Classroom Monitoring System

Full-stack system: OpenCV computer-vision pipeline + FastAPI backend + React dashboard + SQLite/PostgreSQL storage, with JWT/role-based access control, student registration, and exportable reports.

**Docs:** [Architecture](docs/ARCHITECTURE.md) · [Feature list](docs/FEATURES.md) · [Deployment guide](docs/DEPLOYMENT.md) · [Demo & screenshots](docs/DEMO_AND_SCREENSHOTS.md) · [Architecture diagram](docs/architecture.svg)

## Features

- **Vision pipeline**: YuNet face detection (landmarks), SFace face recognition
  (128-d embeddings, confidence-scored matching, ambiguous matches held as
  "identifying" instead of duplicated), FER+ emotion classification, heuristic
  attention scoring, camera auto-reconnect, idle-scene throttling
- **Student registration**: register by name, camera face enrollment (multiple
  embeddings per student), duplicate-face and duplicate-name rejection, edit /
  delete / search, real names on the live dashboard
- **Attendance**: entry / exit / duration per session, absence alerts
- **Reports**: daily / weekly / monthly attendance, attention and emotion
  trends — CSV, PDF, JSON
- **Analytics**: live dashboard (video, attention chart, emotion pie, alerts)
  plus historical trends with date-range and hour/day bucketing, peak
  attendance and most-distracted periods
- **Auth**: JWT (HS256, stdlib) with admin / teacher / viewer roles, PBKDF2
  password hashing, login rate limiting, audit logging; legacy `X-API-Key`
  still accepted (admin-equivalent) for backward compatibility
- **Hardening**: structured (text/JSON) logging, global error handler, per-IP
  REST rate limiting, WebSocket connection caps + slow-client eviction,
  graceful shutdown, DB init retry, config validation (refuses default
  secrets in `PRODUCTION=true`), `/health` + `/ready` probes

## Quick start

```powershell
# Backend
cd backend
python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\download_models.py        # ~83 MB of ONNX/Caffe models
copy .env.example .env                    # then set real secrets
python -m uvicorn app.main:app --port 8000

# Frontend
cd frontend
copy .env.example .env
npm install
npm run dev                               # http://localhost:5173
```

Sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` (default `admin` / `admin123`
— change before any real use). Create teacher/viewer accounts via
`POST /auth/users`.

### Tests

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q          # 16 tests: auth, RBAC, CRUD, reports, analytics
scripts\e2e_verify.ps1             # end-to-end checks against a running server
python scripts\live_check.py 30    # live WebSocket diagnostics
```

## Roles

| Role | Access |
|---|---|
| viewer | Dashboard + live WebSocket only |
| teacher | + students (read), attendance, reports, trends |
| admin | Everything: sessions, registration, enrollment, user management |

## API

`Authorization: Bearer <jwt>` on REST, `?token=<jwt>` on WebSocket
(legacy `X-API-Key` header / `?api_key=` also work).

| Endpoint | Method | Min role |
|---|---|---|
| `/auth/login` `/auth/me` | POST / GET | — / any |
| `/auth/users` | GET, POST, DELETE | admin |
| `/start-session` `/end-session` | POST | admin |
| `/students` (`?search=`) | GET | teacher |
| `/students` / `/students/{id}` | POST / PUT / DELETE | admin |
| `/students/{id}/enroll` | POST | admin |
| `/attendance` | GET | teacher |
| `/analytics` | GET | viewer |
| `/analytics/trends?from=&to=&bucket=` | GET | teacher |
| `/reports/{attendance,attention,emotion}?period=&date=&format=` | GET | teacher |
| `/live` | WS | viewer |
| `/health` `/ready` | GET | public |

## Deployment notes

- Set `PRODUCTION=true` — startup then refuses to run with default
  `API_KEY` / `JWT_SECRET` / `ADMIN_PASSWORD`.
- Put the backend behind TLS (reverse proxy); JWTs travel in headers/query.
- PostgreSQL: `pip install psycopg2-binary`, set `DATABASE_URL`.
- Frontend: `npm run build`, serve `dist/` statically; set `VITE_API_URL`,
  `VITE_WS_URL` to the backend's public URL and add it to `FRONTEND_ORIGIN`.
- One backend process drives one camera (`CAMERA_SOURCE`); run multiple
  instances on different ports for multiple rooms.
