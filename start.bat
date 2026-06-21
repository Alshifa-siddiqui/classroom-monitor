@echo off
REM ============================================================
REM  Classroom Monitor - one-click start (backend serves the UI)
REM  Open http://localhost:8000 on this PC, or
REM  http://<this-PC-IP>:8000 from another device on the network.
REM ============================================================
cd /d "%~dp0backend"
echo Starting Classroom Monitor on port 8000 ...
echo Local:   http://localhost:8000
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo Network: http://%%a:8000
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
