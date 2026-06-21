# Architecture

Single-process FastAPI backend serving a React SPA over HTTPS REST + a WebSocket,
backed by SQLite/PostgreSQL, with a background OpenCV vision pipeline.

```mermaid
flowchart TB
  subgraph Client["CLIENT · Browser"]
    SPA["React SPA (Vite)<br/>JWT in localStorage"]
    Staff["Staff UI — role-gated tabs<br/>Dashboard · Students · Reports · Analytics · Users"]
    Portal["Student portal<br/>own history only"]
    Login["Login / Sign-up<br/>(optional admin code)"]
  end

  Client -- "HTTPS REST + WSS WebSocket (Bearer JWT)" --> MW

  subgraph Backend["BACKEND · FastAPI (single process, Uvicorn worker)"]
    MW["Middleware: CORS · JWT+RBAC · rate limit · error handler"]
    subgraph REST["REST services"]
      A["auth_routes"]
      S["students + enroll"]
      R["reports (CSV/PDF/JSON)"]
      AN["analytics + trends (cached)"]
      P["profile · attendance · alerts · audit"]
      WS["WebSocket manager"]
    end
    subgraph AI["AI vision pipeline (thread, OpenCV DNN)"]
      D["① YuNet detect (+landmarks)"]
      T["② IoU tracker + re-ID"]
      ID["③ SFace identity (128-d)"]
      E["④ FER+ emotion"]
      AT["⑤ Attention score"]
      O["⑥ Overlay + attendance"]
      B["⑦ Broadcast frames/analytics/alerts"]
      D --> T --> ID --> E --> AT --> O --> B
    end
    MW --> REST
    MW --> AI
  end

  Cam["webcam / RTSP → frame grabber<br/>(latest-frame, auto-reconnect, idle throttle)"] --> D
  B --> WS

  Backend <--> DB[("SQLite / PostgreSQL — 9 tables<br/>users · students · face_embeddings · sessions ·<br/>attendance · attention_logs · emotion_logs · alerts · audit_logs")]
```

## Request paths

- **REST** (`Authorization: Bearer <jwt>`): every route carries a role dependency
  (`require_role`). Order: middleware (rate-limit + log) → route → service → DB.
- **WebSocket** (`/live?token=<jwt>`): viewer+ only. The pipeline pushes three
  message types — `frame` (base64 JPEG ~5 fps), `analytics` (~2/s), `alert`
  (immediate), plus `session_ended` on stop.

## Pipeline timing

- Capture thread holds only the latest frame (frame skipping).
- CV work runs in a thread-pool executor so the event loop is never blocked.
- After ~50 empty frames, detection drops to every 3rd frame (idle throttle);
  the feed keeps streaming.
- DB flush of attention/emotion samples every 10 s; analytics endpoints are
  TTL-cached (5 s) and trends cached (30 s).

## Identity resolution

Each unresolved track accumulates ≥5 SFace embeddings; the mean is matched
against per-student galleries (cosine). ≥0.40 = match (similarity reported as
confidence), <0.25 = register new student, in-between = held as "identifying"
so ambiguity never spawns a duplicate. Galleries persist across restarts.
