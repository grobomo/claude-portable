# 001 -- Dashboard Authentication -- Summary

## What Was Done

1. **Created `scripts/dashboard_auth.py`** -- standalone auth module with:
   - User store backed by `dashboard_users.json` (bcrypt-hashed passwords)
   - Default `admin/admin` user with `force_password_change=True`
   - Session management (httpOnly cookies, 24h TTL)
   - User CRUD: add, delete, force password reset
   - HTML pages: login, change-password, admin panel (dark theme matching dashboard)

2. **Modified `scripts/git-dispatch.py`** -- integrated auth into HealthHandler:
   - `_require_auth()` middleware checks session cookie, redirects to login if missing
   - Auth routes: `/auth/login`, `/auth/logout`, `/auth/change-password`
   - Admin routes: `/admin`, `/admin/add-user`, `/admin/delete-user`, `/admin/force-reset`
   - Protected: `/`, `/dashboard`, `/dashboard/` (HTML pages)
   - Unprotected: `/health`, `/board`, `/relay/status`, `/api/*`, `/worker/*` (machine-to-machine)

3. **Modified `Dockerfile`** -- added `bcrypt` to pip install

4. **Modified `scripts/dashboard.html`** -- added Admin + Sign Out links to header

5. **Updated `.gitignore`** -- added `scripts/dashboard_users.json`

## Success Criteria Met
- [x] Login page with username/password form
- [x] Default admin/admin user created on first run
- [x] Force password change on first login
- [x] Admin panel to add users and force password resets
- [x] Session-based auth with secure httpOnly cookies
- [x] All dashboard routes protected behind auth middleware
- [x] Credentials stored in local JSON file with bcrypt hashes
- [x] Auth middleware integrated into existing HealthHandler class
