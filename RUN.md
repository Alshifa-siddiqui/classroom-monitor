# Running Classroom Monitor (single-PC / LAN deployment)

The backend now **serves the dashboard itself** — one process, one port (8000),
one URL. No separate frontend server, no two terminals, no CORS.

## Every day: start it

Double-click **`start.bat`** (in the project root), or run:

```powershell
cd C:\Users\Admin\Desktop\classroom-monitor\backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open:
- **On this PC:** http://localhost:8000
- **From any phone/laptop on the same Wi-Fi:** `http://<this-PC-IP>:8000`
  (this PC's IP is **192.168.100.128**, so http://192.168.100.128:8000)

Sign in `admin` / `admin123`.

> The IP can change when the PC reconnects to Wi-Fi. If the network address stops
> working, re-check it with `ipconfig` (look for "IPv4 Address"), or ask your
> router to reserve a fixed IP for this PC.

## One-time: let other devices connect (firewall)

Open **PowerShell as Administrator** (right-click → Run as administrator) and paste:

```powershell
New-NetFirewallRule -DisplayName "Classroom Monitor 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
```

(Only needed for access from *other* devices; localhost works without it.)

## One-time: start automatically on boot (optional)

Run in a normal PowerShell (no admin needed) to launch at every logon:

```powershell
$action  = New-ScheduledTaskAction -Execute "C:\Users\Admin\Desktop\classroom-monitor\start.bat"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "ClassroomMonitor" -Action $action -Trigger $trigger -Description "Classroom Monitor server"
```

Remove it later with `Unregister-ScheduledTask -TaskName "ClassroomMonitor"`.

## One-time: change the admin password

Sign in as admin → **Users** tab is for accounts, but to change *your own*
password use the API once (PowerShell):

```powershell
# (password change endpoint is admin-managed; simplest: create a new admin via
#  the signup admin-code, then delete the default admin from the Users tab)
```

Or set a strong `ADMIN_PASSWORD` in `backend\.env` **before first run on a fresh
database** so the seeded admin uses it.

## If you change the dashboard code later

The browser loads the **built** copy, so after editing anything in `frontend/src`
rebuild once:

```powershell
cd C:\Users\Admin\Desktop\classroom-monitor\frontend
npm run build
```

then restart `start.bat`. (For active development, `npm run dev` on port 5173
still works against the backend on 8000.)

## Health checks

- http://localhost:8000/health → `{"status":"ok"}` (is it up?)
- http://localhost:8000/ready → database + AI models status
