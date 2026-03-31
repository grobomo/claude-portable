# 001 -- Dashboard Authentication

## Goal
Add session-based authentication to the CCC fleet dashboard (port 8082) with login page, admin panel, forced password change, and bcrypt-hashed credential storage.

## Success Criteria
- [ ] Login page with username/password form
- [ ] Default admin/admin user created on first run
- [ ] Force password change on first login
- [ ] Admin panel to add users and force password resets
- [ ] Session-based auth with secure httpOnly cookies
- [ ] All dashboard routes protected behind auth middleware
- [ ] Credentials stored in local JSON file with bcrypt hashes
- [ ] Auth middleware integrated into existing HealthHandler class

## Approach
1. Add `scripts/dashboard_auth.py` module -- session management, user CRUD, bcrypt hashing
2. Add auth routes to HealthHandler in git-dispatch.py -- login/logout/admin/change-password
3. Add auth middleware that wraps existing dashboard routes
4. Embed login page HTML and admin panel HTML inline (same pattern as dashboard.html serving)
5. Keep /health and /board endpoints public (machine-to-machine), protect only dashboard/UI routes
