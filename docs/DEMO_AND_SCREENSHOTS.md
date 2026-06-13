# Demo Script & Screenshot Shot List

> These two deliverables require the running app with **a person in front of the
> camera** (the automated tests cover everything else). Both servers must be up:
> `uvicorn app.main:app --port 8000` and `npm run dev`. Sign in as **admin**.

## Screenshot shot list (10 shots)

Capture at 1280×800+, light or dark, browser chrome cropped.

1. **Login page** — showing both "Sign in / Create account" tabs and the admin-code field.
2. **Empty dashboard** — status chips (Connected, Camera off, No active session) + 5 stat cards.
3. **Students page** — student table with Student ID, Name, Email, Enrollment, Account columns.
4. **Registration modal** — name + email + password fields open.
5. **Enrollment in progress / success toast** — "Enrolled … N samples (quality …%)".
6. **Live dashboard with a face** — overlay card on the feed showing Name · ID · emotion ·
   attention · confidence, plus Present/Absent/Avg-attention cards populated.
7. **Attention chart + emotion pie** populated during a live session.
8. **Reports page** — type/period/date controls + a preview table, Download CSV/PDF buttons.
9. **Analytics (trends)** — attendance bar + attention line + emotion stacked bar.
10. **Student portal** — signed in as a student: ID, attendance %, avg attention, emotion stats, history.

Optional: **Users page** (role dropdowns) to show RBAC management.

## 2–3 minute demo video — storyboard

| Time | Scene | Say / show |
|---|---|---|
| 0:00–0:15 | Login | "This is the Classroom Monitor. I sign in as an administrator." Show the role badge top-right. |
| 0:15–0:40 | Register a student | Students → Register: enter name, email, password. "Each student gets a unique ID and a login account." Show the new `STU-2026-NNN` row. |
| 0:40–1:05 | Face enrollment | Click Enroll, face the camera. "It captures several face embeddings and links them to this student." Show the success toast + "Enrolled" badge. |
| 1:05–1:35 | Live session | Dashboard → Start session. "The camera comes on and recognizes the student." Point at the overlay: Name, ID, emotion, attention %, confidence %. Show Present count and the live charts moving. |
| 1:35–1:55 | End + attendance | End session. "Attendance, attention and emotion are all saved." Show the feed clear and the chip return to Camera off. |
| 1:55–2:20 | Reports | Reports tab → Attendance/daily → Download CSV, then PDF. Open the file briefly. |
| 2:20–2:45 | Student portal | Sign out, sign in as the student. "Students see only their own profile — attendance %, attention, emotion history." |
| 2:45–3:00 | Wrap | Back to dashboard/analytics trends. "Real-time monitoring, per-student history, exportable reports — role-separated for staff and students." |

**Recording tip (Windows):** `Win+Alt+R` (Xbox Game Bar) or OBS. One continuous take
per scene is fine; trim between scenes.
