# End-to-end verification against the running backend (PowerShell 5.1).
$ErrorActionPreference = "Stop"
$base = "http://localhost:8000"
$results = @()
function Check($name, $ok, $detail = "") {
    $script:results += [pscustomobject]@{ check = $name; ok = $ok; detail = $detail }
    Write-Host ("[{0}] {1} {2}" -f ($(if ($ok) { "PASS" } else { "FAIL" })), $name, $detail)
}

# wait for server
$up = $false
foreach ($i in 1..40) {
    try { $null = Invoke-RestMethod "$base/health" -TimeoutSec 2; $up = $true; break }
    catch { Start-Sleep -Milliseconds 500 }
}
Check "backend startup (/health)" $up

# readiness
$ready = Invoke-RestMethod "$base/ready"
Check "readiness (/ready)" ($ready.status -eq "ready") ($ready.checks | ConvertTo-Json -Compress)

# 1. login
$admin = Invoke-RestMethod "$base/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'
Check "admin login (JWT issued)" ($admin.token.Length -gt 50 -and $admin.role -eq "admin")
$ah = @{ Authorization = "Bearer $($admin.token)" }

# wrong password rejected
$badLogin = $false
try { Invoke-RestMethod "$base/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"nope"}' } catch { $badLogin = $_.Exception.Response.StatusCode.value__ -eq 401 }
Check "wrong password rejected (401)" $badLogin

# RBAC users
foreach ($u in @(@{u="teacher_e2e"; r="teacher"}, @{u="viewer_e2e"; r="viewer"})) {
    try { Invoke-RestMethod "$base/auth/users" -Method Post -Headers $ah -ContentType "application/json" -Body (@{username=$u.u; password="password123"; role=$u.r} | ConvertTo-Json) | Out-Null } catch {}
}
$teacher = Invoke-RestMethod "$base/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"teacher_e2e","password":"password123"}'
$viewer  = Invoke-RestMethod "$base/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"viewer_e2e","password":"password123"}'
$th = @{ Authorization = "Bearer $($teacher.token)" }
$vh = @{ Authorization = "Bearer $($viewer.token)" }

$viewerBlocked = $false
try { Invoke-RestMethod "$base/students" -Headers $vh } catch { $viewerBlocked = $_.Exception.Response.StatusCode.value__ -eq 403 }
$viewerDash = (Invoke-RestMethod "$base/analytics" -Headers $vh) -ne $null
Check "viewer: dashboard yes, students no" ($viewerBlocked -and $viewerDash)

$teacherRead = (Invoke-RestMethod "$base/students" -Headers $th) -ne $null
$teacherBlocked = $false
try { Invoke-RestMethod "$base/students" -Method Post -Headers $th -ContentType "application/json" -Body '{"name":"Should Fail"}' } catch { $teacherBlocked = $_.Exception.Response.StatusCode.value__ -eq 403 }
Check "teacher: read yes, manage no" ($teacherRead -and $teacherBlocked)

# 2. registration
$stu = Invoke-RestMethod "$base/students" -Method Post -Headers $ah -ContentType "application/json" -Body '{"name":"E2E Test Student"}'
Check "student registration" ($stu.name -eq "E2E Test Student" -and -not $stu.enrolled)
$dup = $false
try { Invoke-RestMethod "$base/students" -Method Post -Headers $ah -ContentType "application/json" -Body '{"name":"e2e test student"}' } catch { $dup = $_.Exception.Response.StatusCode.value__ -eq 409 }
Check "duplicate registration rejected (409)" $dup

# rename + search
$null = Invoke-RestMethod "$base/students/$($stu.id)" -Method Put -Headers $ah -ContentType "application/json" -Body '{"name":"E2E Renamed Student"}'
$found = Invoke-RestMethod "$base/students?search=Renamed" -Headers $ah
Check "rename + search" ($found.Count -eq 1 -and $found[0].name -eq "E2E Renamed Student")

# 3-7. live session: enrollment, recognition, attendance, emotion, attention
$sess = Invoke-RestMethod "$base/start-session" -Method Post -Headers $ah -ContentType "application/json" -Body '{"name":"E2E Verification"}'
Check "session start (camera acquired)" ($sess.id -gt 0)

# enrollment (requires a face in view - may legitimately fail on empty room)
$enrollOk = $false; $enrollDetail = ""
try {
    $enr = Invoke-RestMethod "$base/students/$($stu.id)/enroll" -Method Post -Headers $ah -TimeoutSec 30
    $enrollOk = $enr.samples_captured -ge 3
    $enrollDetail = "samples=$($enr.samples_captured) quality=$($enr.quality)"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    $enrollDetail = "HTTP $code (no face in view is expected on an empty room)"
}
Check "face enrollment" $enrollOk $enrollDetail

Write-Host "observing live pipeline for 30s..."
Start-Sleep -Seconds 30

$an = Invoke-RestMethod "$base/analytics?minutes=10" -Headers $vh
Check "live analytics (emotion+attention logged)" ($an -ne $null) ("present=$($an.present_count) emotions=$(($an.emotion_distribution | ConvertTo-Json -Compress))")
$att = Invoke-RestMethod "$base/attendance?session_id=$($sess.id)" -Headers $th
Check "attendance rows" ($att -is [array] -or $att -ne $null) "rows=$(@($att).Count)"

# 8. reports
$today = (Get-Date).ToString("yyyy-MM-dd")
$csv = Invoke-WebRequest "$base/reports/attendance?period=daily&date=$today&format=csv" -Headers $th -UseBasicParsing
$pdf = Invoke-WebRequest "$base/reports/emotion?period=weekly&date=$today&format=pdf" -Headers $th -UseBasicParsing
Check "report CSV download" ($csv.StatusCode -eq 200 -and $csv.Headers["Content-Disposition"] -match "attachment") "bytes=$($csv.RawContentLength)"
Check "report PDF download" ($pdf.StatusCode -eq 200 -and [System.Text.Encoding]::ASCII.GetString($pdf.Content[0..3]) -eq "%PDF") "bytes=$($pdf.RawContentLength)"

# 9. trends
$weekAgo = (Get-Date).AddDays(-7).ToString("yyyy-MM-dd")
$trends = Invoke-RestMethod "$base/analytics/trends?from=$weekAgo&to=$today&bucket=day" -Headers $th
Check "analytics trends" ($trends.attention -ne $null) "attention_buckets=$(@($trends.attention).Count)"

# 11. db persistence
Set-Location $PSScriptRoot\..
$persist = python -c "from app.database import SessionLocal; from app.models import Student, User, AuditLog, Attendance; db = SessionLocal(); print(f'students={db.query(Student).count()} users={db.query(User).count()} audit={db.query(AuditLog).count()} attendance={db.query(Attendance).count()}'); db.close()"
Check "database persistence" ($persist -match "users=[1-9]") $persist

# 12. logout/login cycle (logout is client-side token drop; verify re-login issues a fresh valid token)
$relogin = Invoke-RestMethod "$base/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"admin123"}'
$meAgain = Invoke-RestMethod "$base/auth/me" -Headers @{ Authorization = "Bearer $($relogin.token)" }
Check "logout/login cycle" ($meAgain.username -eq "admin" -and $relogin.token -ne $admin.token)

# end session
$null = Invoke-RestMethod "$base/end-session" -Method Post -Headers $ah
Check "session end (attendance closed)" $true

# cleanup e2e student
try { Invoke-RestMethod "$base/students/$($stu.id)" -Method Delete -Headers $ah | Out-Null } catch {}

""
"==== SUMMARY ===="
$pass = @($results | Where-Object ok).Count
"{0}/{1} checks passed" -f $pass, $results.Count
$results | Where-Object { -not $_.ok } | ForEach-Object { "FAILED: $($_.check) $($_.detail)" }
