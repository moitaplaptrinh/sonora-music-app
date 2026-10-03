# SONORA Super VIP — Full Stack Starter

## Windows local
1. Install Python 3.11+.
2. Open CMD in this folder.
3. Run: `python server.py`
4. Open: `http://127.0.0.1:8787/`

Do not open `index.html` with `file://`.

## GitHub + Railway production-style deployment
GitHub stores the code. Railway runs the Python server and provides the public URL.

Recommended repository files:
- index.html
- server.py
- requirements.txt
- .gitignore
- README.md

On Railway:
1. Create a project from the GitHub repo.
2. Set Start Command to `python server.py`.
3. Generate a public domain for the service.
4. Add a Volume mounted at `/data`.
5. Add variable `SONORA_DATA_DIR=/data`.
6. Redeploy.

The app is then available from the Railway URL. The frontend and `/api/*` endpoints are same-origin, so login cookies work without GitHub Pages/CORS complexity.

## Current starter limitations
- Password reset does not send real email.
- Uploads are stored on the server volume; for large-scale use, replace with S3/R2-style object storage.
- SQLite is fine for a small single-server community; for larger scale use PostgreSQL.
- Add production rate limiting, CSRF protections, moderation, antivirus/media validation, backups, and HTTPS before a public launch with real users.
