# Real-Time AI Classroom Monitoring System

Full-stack system that watches a classroom through a webcam in real time:
detects and recognizes students, tracks attendance, attention and emotion, and
serves it all on a live dashboard with role-based logins and exportable reports.

**Stack:** OpenCV CV pipeline (YuNet · SFace · FER+) · FastAPI backend ·
React dashboard · SQLite/PostgreSQL · JWT auth with role-based access control.

**Docs:** [Architecture](docs/ARCHITECTURE.md) · [Feature list](docs/FEATURES.md) ·
[Run & deploy](RUN.md) · [Full deployment guide](docs/DEPLOYMENT.md) ·
[Demo & screenshots](docs/DEMO_AND_SCREENSHOTS.md) ·
[Architecture diagram](docs/architecture.svg)

---

## Features

- **Vision pipeline** — YuNet face detection (with landmarks), SFace face
  recognition (128-d embeddings, confidence-scored matching, ambiguous matches
  held as "identifying" rather than duplicated), FER+ emotion classification,
  heuristic attention scoring, camera auto-reconnect, idle-scene throttling.
- **Students as unified accounts** — register by name, optionally with email +
  password to create a linked **student login**; auto-generated **Student ID**
  (`STU-YYYY-NNN`); camera face enrollment (multiple embeddings per student);
  duplicate-face and duplicate-name rejection; edit / delete / search.
- **Live monitoring** — Start/End session, camera-status indicator, and a video
  overlay per face showing **name · ID · emotion · attention % · confidence %**.
- **Attendance** — entry / exit / duration per session, with absence,
  low-attention and negative-emotion alerts.
- **Analytics** — live dashboard (video, attention chart, emotion pie, alerts)
  plus historical **trends** (attendance / attention / emotion) with date-range
  and hour/day bucketing, peak-attendance and most-distracted markers.
- **Student portal** — students log in and see only their own profile:
  attendance %, average attention, emotion stats, last seen, and history.
- **Reports** — attendance / attention / emotion, daily / weekly / monthly,
  exported as **CSV · PDF · JSON**.
- **Auth & RBAC** — JWT (HS256, stdlib) + PBKDF2 hashing; four roles
  (student / viewer / teacher / admin); self-signup (admin code optional for
  elevated accounts); login rate limiting; audit logging. Legacy `X-API-Key`
  still accepted (admin-equivalent) for backward compatibility.
- **Production hardening** — structured (text/JSON) logging, global error
  handler, per-IP rate limiting, WebSocket connection caps + slow-client
  eviction, graceful shutdown, DB-init retry, additive schema migration, config
  validation (refuses default secrets when `PRODUCTION=true`), `/health` +
  `/ready` probes, frontend error boundary.

---

## Architecture

A single-process FastAPI backend serves the React SPA over HTTPS REST + a
WebSocket, runs a background OpenCV vision pipeline, and persists to
SQLite/PostgreSQL. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full
diagram and [docs/architecture.svg](docs/architecture.svg) for the image.

```
Browser (React SPA, JWT)
      │  HTTPS REST  +  WSS WebSocket
      ▼
FastAPI backend  ── middleware: CORS · JWT+RBAC · rate limit · error handler
      ├── REST services: auth · students/enroll · reports · analytics ·
      │                  profile · attendance · alerts · audit · WS manager
      └── AI pipeline (background thread, OpenCV DNN):
            webcam → YuNet detect → tracker+re-ID → SFace identity →
            FER+ emotion → attention → overlay+attendance → broadcast
      ▼
SQLite / PostgreSQL — 9 tables
  users · students · face_embeddings · sessions · attendance ·
  attention_logs · emotion_logs · alerts · audit_logs
```

**Identity resolution:** each unresolved track accumulates ≥5 SFace embeddings;
the mean is matched against per-student galleries (cosine). ≥0.40 = match
(similarity reported as confidence), <0.25 = register new student, in-between =
held as "identifying" so ambiguity never spawns a duplicate.

**Pipeline timing:** the capture thread keeps only the latest frame; CV work
runs in a thread-pool executor so the event loop never blocks; detection drops
to every 3rd frame once the room is empty; analytics endpoints are TTL-cached.

---

## Quick start

Models are required for recognition; download them once:

```powershell
cd backend
python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\download_models.py        # ~83 MB of ONNX/Caffe models
copy .env.example .env                    # set real secrets before any real use
```

### Run it (single process — recommended)

The backend serves the built dashboard, so it's **one process on one port**.

```powershell
# build the UI once (re-run after any frontend change)
cd frontend ; npm install ; npm run build

# start everything
cd ..\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** (or `http://<this-PC-IP>:8000` from another device
on the same network). On Windows you can just double-click **`start.bat`**.
Sign in with `ADMIN_USERNAME` / `ADMIN_PASSWORD` (default `admin` / `admin123`).

### Run it (development — hot reload)

```powershell
# terminal 1
cd backend ; python -m uvicorn app.main:app --port 8000
# terminal 2
cd frontend ; copy .env.example .env ; npm run dev   # http://localhost:5173
```

---

## Roles

| Role | Access |
|---|---|
| **student** | Own profile/history only (student portal) |
| **viewer** | Live dashboard + WebSocket |
| **teacher** | + students (read), attendance, reports, analytics/trends |
| **admin** | Everything: sessions, registration, enrollment, user management |

Self-signup creates a **viewer** by default; supplying the configured
`ADMIN_SIGNUP_CODE` at signup creates an **admin**. Admins manage roles from the
**Users** page.

---

## API

`Authorization: Bearer <jwt>` on REST, `?token=<jwt>` on the WebSocket
(legacy `X-API-Key` header / `?api_key=` also work).

| Endpoint | Method | Min role |
|---|---|---|
| `/auth/login` · `/auth/signup` | POST | public |
| `/auth/me` | GET | any |
| `/auth/users` | GET · POST | admin |
| `/auth/users/{id}` | PUT (role) · DELETE | admin |
| `/start-session` · `/end-session` | POST | admin |
| `/students` (`?search=`) | GET | teacher |
| `/students` · `/students/{id}` | POST · PUT · DELETE | admin |
| `/students/{id}/enroll` | POST | admin |
| `/students/{id}/profile` | GET | teacher |
| `/me/student` | GET | student |
| `/attendance` | GET | teacher |
| `/analytics` | GET | viewer |
| `/analytics/trends?from=&to=&bucket=` | GET | teacher |
| `/reports/{attendance,attention,emotion}?period=&date=&format=` | GET | teacher |
| `/live` | WS | viewer |
| `/health` · `/ready` | GET | public |

---

## Tests

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q          # 19 tests: auth, RBAC, students, reports, analytics, portal
python scripts\identity_accuracy.py   # re-identification accuracy (synthetic)
python scripts\portal_reports_test.py # live data path: register → portal → reports
scripts\e2e_verify.ps1                # end-to-end checks against a running server
python scripts\live_check.py 30       # live WebSocket diagnostics
```

---

## Deployment

For a classroom, run it on the PC the camera is attached to and reach it over the
LAN — see **[RUN.md](RUN.md)** for the one-click start, firewall, and auto-start
steps. For a full server deploy (Docker, PostgreSQL, Nginx, HTTPS), see
**[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

Key notes:
- Set `PRODUCTION=true` so startup refuses default `API_KEY` / `JWT_SECRET` /
  `ADMIN_PASSWORD`.
- PostgreSQL: `pip install psycopg2-binary`, set `DATABASE_URL`.
- One backend process drives one camera (`CAMERA_SOURCE`); run one instance per
  room for multiple cameras.

## Known limitations

- One process = one camera = one room; in-memory WS/rate-limit/cache state does
  not scale horizontally without Redis.
- Attention is a heuristic (eye focus + head pose + stability), not gaze tracking.
- `sleepy` / `bored` emotions are the least reliable (eye-state heuristic layered
  on FER+, which has no native drowsiness class).
- Logout is client-side; JWTs stay valid until expiry (no revocation list).
