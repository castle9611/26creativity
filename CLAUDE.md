# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview
Pure offline intranet OA system (监狱内网办公系统) for Windows 7 64-bit servers. Green portable deployment: unzip → double-click `office_system/start.bat` → running. No Docker, no external network dependencies, no installation required.

## Run / Build / Deploy Commands
All commands are run from the `office_system/` subdirectory:

```batch
# Production startup (auto-inits DB on first run)
start.bat

# Development (uses the bundled portable Python)
python\python.exe run.py

# Backup & restore
python\python.exe backup.py backup
python\python.exe backup.py list
python\python.exe backup.py restore --file <filename.db>

# Database migration
python\python.exe migrate.py

# Offline self-check
python\python.exe health_check.py

# Build offline release package
python\python.exe make_release.py
python\python.exe make_release.py --fresh-data   # excludes current DB/uploads

# Service management
stop.bat
status.bat
start_hidden.bat                  # background (no console window)
enable_autostart.bat              # login-triggered background start
```

Default accounts (all password `admin123`): `admin` (super_admin), `dept_admin` (dept_admin), `user` (normal user).

## Tech Stack (DO NOT upgrade)
- **Python 3.8.10 64-bit portable** — bundled in `office_system/python/`, NOT system Python
- **Flask 2.0.1** + Flask-SQLAlchemy 2.5.1 + SQLite3
- **LayUI 2.9.10** (frontend UI framework, includes built-in jQuery)
- **KindEditor 4.1.11** (rich text editor)
- **x-spreadsheet** (spreadsheet editor)
- All Python deps pre-installed in portable Python; see `requirements.txt` for versions

## Architecture

### Backend: Flask App Factory (`office_system/app/`)
- `__init__.py` → `create_app()` factory: init DB extensions, register 11 blueprints, set up error handlers, theme injector, and context processors
- `config.py` → hardcoded `Config` class (no .env, no environment variables); paths are relative to `BASE_DIR` (the `office_system/` directory)
- `extensions.py` → `db = SQLAlchemy()` singleton
- `models.py` → 22 model classes including: User, LoginLog, Tab, Column, Bulletin, BulletinCategory, BulletinAttachment, Task, TaskAssignee, TaskTransfer, OperationLog, Memo, MemoGroup, File, FileRelation, SharedFolder, SystemConfig, QuickLink, OnlineDocument, Spreadsheet, DocVersion, SheetVersion + 3 validator classes
- `decorators.py` → `@login_required`, `@require_role('dept_admin')`, `@require_super_admin` (super_admin bypasses all checks)
- `utils.py` → `add_log()` (operation audit), `check_visible()` (RBAC), IP detection, pagination, file name helpers
- `database.py` → `init_database()`: seeds 3 default users + default data
- `migrations.py` → incremental schema migration (added indexes, tab_type, category_id, etc.)
- `migrate.py` → auto-run on startup for existing DBs; handles column additions and legacy data migration
- `importers.py` → DOCX/XLSX/CSV/TXT import for online docs/sheets (pure Python, no Office dependency)

### Blueprints (`office_system/app/views/`)
| File | URL Prefix | Purpose |
|------|-----------|---------|
| `auth.py` | `/` | Login/logout/profile/password change |
| `admin.py` | `/admin` | User/Tab/Column/Share/Log/SystemConfig CRUD (super_admin) |
| `tasks.py` | `/tasks` | Task CRUD, status workflow (pending→processing→completed/transferring), transfer approval |
| `bulletin.py` | `/bulletin` | Two-level category→column nav, publish/edit/archive/expire |
| `memo.py` | `/memo` | Private & role-visible public memos, archive |
| `files.py` | `/files` | Upload/download/delete + KindEditor `/api/upload` |
| `docs.py` | `/docs` | Online document editor (A4 page view), versioning, .doc export |
| `sheets.py` | `/sheets` | Online spreadsheet editor, auto-save, .xls export, version restore |
| `contacts.py` | - | Contact directory |
| `stats.py` | - | Dashboard statistics & summary stories |
| `settings.py` | - | Task category & bulletin category settings |
| `__init__.py` | `/` | `index_bp`: public portal, workbench dashboard, search, quick links, health check |

### Frontend: Server-rendered templates (NO SPA, NO API/JSON frontend)
- 45+ Jinja2 templates in `app/templates/`, each loaded as a standalone page inside iframe tabs
- `base.html` — main layout with left sidebar + iframe multi-tab manager (ES5)
- `login.html` — standalone page (no iframe), neumorphism glassmorphism style
- Every iframe page is self-contained HTML with its own `<style>` and `<script>`
- All CSS uses **neumorphism** design: `background: #e0e5ec`, dual box-shadows, rounded corners
- SVGs for icons stored in `static/icons.svg` (sprite sheet), referenced via `<svg><use href="#icon-id"/></svg>` in `_icon.html` partial
- Static frontend libs: LayUI, KindEditor, x-spreadsheet bundled in `static/`
- `static/js/theme.js` → theme switching (light/dark)
- `static/css/app.css` → 96KB neumorphism stylesheet

### Role-Based Access Control
- **super_admin** — full access across all departments (IT department default)
- **dept_admin** — department-scoped CRUD for tasks/bulletins/files within their department
- **user** — view bulletins, process assigned tasks, personal memos, file upload/download
- `visible_roles` field stores JSON like `["super_admin","dept_admin"]` or `"all"`; parsed by `check_visible()` in `utils.py`

### Database
- Single SQLite file: `office_system/data/database.db`
- DB auto-created with seed data on first `run.py` invocation
- No migration framework; incremental `migrate.py` applies ALTER TABLE statements for new columns
- `run.py` checks DB existence → init or migrate → start server
- Backup script creates timestamped copies in `data/backups/`

## Critical Constraints
1. **ES5 / IE11 compatible**: No `const`/`let`, no arrow functions, no template literals, no `fetch()`, no Promises. Use `var`, `function`, `$.ajax()` (LayUI's jQuery).
2. **No CSS Flexbox/Grid**: Use `float`, `display: table/block/inline-block`, `overflow: hidden` for layouts.
3. **All paths relative**: Code uses `os.path.join(BASE_DIR, ...)`; `BASE_DIR` is `office_system/`. Batch scripts use `%~dp0`.
4. **No Chinese in Python**: All Python comments, log strings, identifiers in English. Template UI text is Chinese (end users).
5. **Memory <200MB**: Single-process Flask (threaded=True), SQLite WAL mode, paginated queries (15 default per page), no heavy middleware.
6. **Portable Python at `python\python.exe`**: All deps in `python\Lib\site-packages\`. Never install to system Python.
7. **Static SECRET_KEY**: Hardcoded in `config.py`; acceptable for pure intranet deployment with no external access.

## Key Patterns
- **Task status machine**: `pending → processing → (completed | transferring → [approve|reject] → processing)` — hardcoded state transitions in `tasks.py`, no workflow engine
- **Bulletin expiration**: Filtered at query layer (`expire_date >= today OR NULL`), no cron/scheduler needed
- **File uploads**: Stored in `data/uploads/YYYY-MM/` with UUID filenames; `File.original_name` preserves display name; `FileRelation` maps files to tasks/bulletins/memos
- **DB init auto-detection**: `run.py` checks `data/database.db` existence → `init_database()` or `migrate()`
- **Online documents**: A4 page view in `docs/`; `importers.py` handles DOCX/XLSX/CSV/TXT import via pure Python (zipfile + XML parsing for Office formats)
- **Theme injection**: `register_theme_injector()` in `__init__.py` injects `theme.js` into HTML responses containing `css/app.css`
- **Port health check**: `health_check.py` verifies file presence, low-level Python extensions, Flask app load, and port 5000 availability before startup
