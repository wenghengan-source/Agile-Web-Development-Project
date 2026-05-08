Title: feat: add templates, modal messaging, messages table and routes

Summary
-------
This PR adds four new templates and supporting backend features to improve messaging and user views:

- New templates: `contact.html`, `profile_custom.html`, `stats_custom.html`, `reward.html` under `Habit-tracker/templates`.
- Frontend: modal-based "Send Message" in `friends.html`, Chart.js integration for weekly stats in `stats_custom.html`, client-side validation in `contact.html`.
- Backend: routes added in `Habit-tracker/app.py` to serve the new templates (`/contact`, `/profile_custom`, `/stats_custom`, `/reward`, `/claim_reward`) and persistence for messages.
- Database: `messages` table created in `init_db()` to store contact/modal messages (`habit_tracker.db`).
- Nav: added links to the new pages in `Habit-tracker/templates/base.html`.

Motivation
----------
Improve social messaging and provide richer UI views (custom profile, stats, rewards). Persist messages so they can be reviewed later.

Files changed (high-level)
-------------------------
- Habit-tracker/app.py (routes + `messages` table creation)
- Habit-tracker/templates/base.html (nav + bootstrap JS)
- Habit-tracker/templates/friends.html (modal + trigger button)
- Habit-tracker/templates/contact.html (enhanced form + prefill)
- Habit-tracker/templates/profile_custom.html (new template)
- Habit-tracker/templates/stats_custom.html (new template + Chart.js)
- Habit-tracker/templates/reward.html (new template)
- Habit-tracker/requirements.txt may be updated (Flask requirement suggested)

Additional changes in this branch
-------------------------------
- Added `/edit_profile` route and `edit_profile.html` to allow users to update name/email/password.
- Fixed `stats_custom()` streak calculation to match `/stats` behavior.
- Ensured `contact.html` and `friends.html` modal prefill the sender email from the logged-in user (previously used recipient by mistake).
- Replaced remaining Chinese strings in templates with English for consistency.

Migration / Notes
-----------------
- The app automatically calls `init_db()` on run and will create `habit_tracker.db` and the `messages` table if missing.
- Password storage remains plain-text in this branch; consider hashing passwords in a follow-up PR.

How to test locally
--------------------
1. Create and activate a virtualenv, install deps (or use system python):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r Habit-tracker\requirements.txt
python Habit-tracker\app.py
```

2. Open `http://127.0.0.1:5000/`, register/login, go to `Friends` and click "Send Message" to open modal and send.
3. Verify `habit_tracker.db` contains entries: `sqlite3 habit_tracker.db "SELECT * FROM messages;"` (or use DB browser).

Checklist
---------
- [x] New templates added and linked
- [x] Modal messaging UI wired to `/contact` POST
- [x] Messages persisted to DB
- [ ] Add tests (future)
- [ ] Migrate passwords to hashed storage (important for security)

Suggested PR description to paste into GitHub UI
-------------------------------------------------
Adds custom UI templates and modal-based messaging. Persists messages to a new `messages` table and exposes new routes for profile/stats/rewards.

This change is focused on UX improvements and message persistence; it does not yet address password hashing or access-control around messages. Recommend a follow-up PR for security hardening.

--
You can create the PR on GitHub using the generated branch `feature/add` (already pushed). Open:

https://github.com/wenghengan-source/Agile-Web-Development-Project/pull/new/feature/add

Or, if you have the GitHub CLI configured:

```bash
gh pr create --title "feat: add templates, modal messaging, messages table and routes" --body-file PR_DRAFT_feature_add.md --base main --head feature/add
```
