# Feature List

## Authentication & access control
- JWT (HS256) auth with PBKDF2-SHA256 password hashing — standard library only.
- Four roles: **student < viewer < teacher < admin**, enforced server-side on every route.
- Login page with **Sign in** and **Create account** tabs; optional **admin code** at
  signup creates an admin, otherwise a viewer.
- Admin **Users** page: list accounts, change roles, delete (cannot self-demote/delete).
- Case-insensitive usernames/emails; per-IP login rate limiting; audit log of sensitive actions.
- Legacy `X-API-Key` accepted (admin-equivalent) for backward compatibility.

## Student management (unified account + profile)
- Register by name, with optional email + password that creates a linked **student login**.
- Auto-generated unique **Student ID** (`STU-YYYY-NNN`) and registration date.
- Camera **face enrollment**: captures multiple SFace embeddings, quality-checked, duplicate-face rejected.
- Edit (rename), delete (cascades face data, history, and the linked account), and search.
- Duplicate name and duplicate email rejection.

## Live monitoring
- Obvious session workflow: **Start / End session**, camera-status and "in class" chips.
- Video overlay per face: **Name · Student ID · attention state · emotion · attention % · confidence %**.
- Real-time dashboard: present / absent / avg attention / identifying / alerts; attention line
  chart; emotion pie; live student table; alert panel.
- WebSocket live updates with auto-reconnect; feed clears cleanly on session end.

## AI pipeline
- **YuNet** face detection with landmarks (res10 SSD / Haar fallback).
- **SFace** recognition — 128-d embeddings, confidence-scored gallery matching, "identifying"
  hold zone to prevent duplicate identities.
- **FER+** emotion classification (neutral / happy / distracted / sleepy / bored) with vote smoothing.
- Heuristic attention scoring (eye focus + head pose + stability), 0–1 with focused/partial/distracted bands.
- Camera auto-reconnect, idle-scene throttling, per-track state pruning.

## Attendance & analytics
- Entry / exit / duration logging per session; absence, low-attention and negative-emotion alerts.
- Historical **trends** (attendance, attention, emotion) with date-range + hour/day bucketing,
  peak-attendance and most-distracted markers.
- Per-student **profile**: attendance %, avg attention, emotion stats, last seen, attention chart, history.

## Reporting
- **Attendance / attention / emotion** reports, **daily / weekly / monthly**.
- Export as **CSV** (Excel-safe BOM), **PDF** (landscape table), or JSON preview.
- Date filtering; teacher+ access.

## Production hardening
- Structured logging (text/JSON), global error handler, `/health` (liveness) + `/ready` (DB + models).
- Config validation: refuses to start with default secrets when `PRODUCTION=true`.
- Per-IP REST rate limiting, WebSocket connection caps + slow-client eviction, graceful shutdown,
  DB-init retry, additive schema migration, frontend error boundary.

## Verification assets
- 19 automated pytest tests (auth, RBAC, students, reports, analytics, unified-account workflow).
- Scripts: `identity_accuracy.py`, `portal_reports_test.py`, `e2e_verify.ps1`, `workflow_verify.ps1`,
  `live_check.py`, `smoke_test.py`, `sface_smoke.py`.
