# 14-step classroom workflow verification (run against a live backend).
$ErrorActionPreference = "Stop"
$base = "http://localhost:8000"
$results = @()
function Check($n, $name, $ok, $detail = "") {
    $script:results += [pscustomobject]@{ n = $n; check = $name; ok = $ok; detail = $detail }
    Write-Host ("[{0}] {1}. {2} {3}" -f ($(if ($ok) { "PASS" } else { "FAIL" })), $n, $name, $detail)
}

foreach ($i in 1..40) { try { $null = Invoke-RestMethod "$base/health" -TimeoutSec 2; break } catch { Start-Sleep -Milliseconds 500 } }

# teacher/admin login (step 5)
$admin = Invoke-RestMethod "$base/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'
$ah = @{ Authorization = "Bearer $($admin.token)" }
Check 5 "teacher/admin login" ($admin.role -eq "admin")

# 1+2: create student with account -> receives auto ID
$uid = Get-Random -Maximum 9999
$email = "workflow$uid@school.edu"
$stu = Invoke-RestMethod "$base/students" -Method Post -Headers $ah -ContentType "application/json" -Body (@{name="Workflow Student $uid"; email=$email; password="studentpass1"} | ConvertTo-Json)
Check 1 "create student (with account)" ($stu.has_account -eq $true) "email=$email"
Check 2 "student receives unique ID" ($stu.student_code -match "^STU-\d{4}-\d{3,}$") $stu.student_code

# 6: session starts
$sess = Invoke-RestMethod "$base/start-session" -Method Post -Headers $ah -ContentType "application/json" -Body '{"name":"Workflow Verification"}'
Check 6 "session starts (camera acquired)" ($sess.id -gt 0) "session=$($sess.id)"

# 3: face enrollment (requires the student facing the camera)
$enrollOk = $false; $enrollDetail = ""
try {
    $enr = Invoke-RestMethod "$base/students/$($stu.id)/enroll" -Method Post -Headers $ah -TimeoutSec 40
    $enrollOk = $enr.samples_captured -ge 3
    $enrollDetail = "samples=$($enr.samples_captured) quality=$($enr.quality)"
} catch {
    $enrollDetail = "no face in camera view (HTTP $($_.Exception.Response.StatusCode.value__))"
}
Check 3 "face enrollment" $enrollOk $enrollDetail

# 4: student login with email/password
$slogin = Invoke-RestMethod "$base/auth/login" -Method Post -ContentType "application/json" -Body (@{username=$email; password="studentpass1"} | ConvertTo-Json)
$sh = @{ Authorization = "Bearer $($slogin.token)" }
Check 4 "student login (email+password)" ($slogin.role -eq "student" -and $slogin.student_id -eq $stu.id)
$portal = Invoke-RestMethod "$base/me/student" -Headers $sh
$blocked = $false
try { Invoke-RestMethod "$base/students" -Headers $sh } catch { $blocked = $_.Exception.Response.StatusCode.value__ -eq 403 }
Check 4 "student portal + staff features blocked" (($portal.student_code -eq $stu.student_code) -and $blocked)

Write-Host "observing live pipeline for 35s (face the camera for steps 7-12)..."
Start-Sleep -Seconds 35

# 7-12: detection / recognition / overlay payload / attendance via live snapshot
Set-Location $PSScriptRoot\..
$snap = python -c @"
import asyncio, json, sys
sys.path.insert(0, '.')
from app.config import settings
import websockets

async def main():
    url = f'ws://localhost:8000/live?api_key={settings.API_KEY}'
    best = None
    async with websockets.connect(url, max_size=4*1024*1024) as ws:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 15
        while loop.time() < deadline:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            except asyncio.TimeoutError:
                break
            if msg['type'] == 'analytics':
                present = [s for s in msg['students'] if s['present']]
                if present:
                    best = present[0]
                    break
    print(json.dumps(best))

asyncio.run(main())
"@
$live = $null
if ($snap -and $snap -ne "null") { $live = $snap | ConvertFrom-Json }
if ($live) {
    Check 7 "face detected" $true
    Check 8 "student recognized" ($null -ne $live.name) "name=$($live.name) conf=$($live.identity_confidence)"
    Check 9 "student ID shown" ($null -ne $live.student_code -and $live.student_code -ne "") "id=$($live.student_code)"
    Check 10 "emotion shown" ($live.emotion -in @("neutral","happy","distracted","sleepy","bored")) "emotion=$($live.emotion)"
    Check 11 "attention shown" ($live.attention -ge 0 -and $live.attention -le 1) "attention=$($live.attention) ($($live.attention_label))"
} else {
    Check 7 "face detected" $false "nobody in camera view during the window"
    Check 8 "student recognized" $false "skipped (no face)"
    Check 9 "student ID shown" $false "skipped (no face)"
    Check 10 "emotion shown" $false "skipped (no face)"
    Check 11 "attention shown" $false "skipped (no face)"
}

$att = Invoke-RestMethod "$base/attendance?session_id=$($sess.id)" -Headers $ah
Check 12 "attendance recorded" (@($att).Count -gt 0) "rows=$(@($att).Count)"

# 13: session ends
$null = Invoke-RestMethod "$base/end-session" -Method Post -Headers $ah
Check 13 "session ends" $true

# 14: reports generated
$today = (Get-Date).ToString("yyyy-MM-dd")
$csv = Invoke-WebRequest "$base/reports/attendance?period=daily&date=$today&format=csv" -Headers $ah -UseBasicParsing
$pdf = Invoke-WebRequest "$base/reports/attention?period=daily&date=$today&format=pdf" -Headers $ah -UseBasicParsing
Check 14 "reports generated (CSV+PDF)" ($csv.StatusCode -eq 200 -and [System.Text.Encoding]::ASCII.GetString($pdf.Content[0..3]) -eq "%PDF")

""
"==== WORKFLOW SUMMARY ===="
$pass = @($results | Where-Object ok).Count
"{0}/{1} steps passed" -f $pass, $results.Count
$results | Where-Object { -not $_.ok } | ForEach-Object { "FAILED step $($_.n): $($_.check) - $($_.detail)" }
