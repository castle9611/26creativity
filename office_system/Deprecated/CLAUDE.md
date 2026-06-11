# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview
Pure offline intranet OA system for Windows 7 64-bit servers. Green portable deployment: unzip → double-click `start.bat` → running. No Docker, no external dependencies, no installation required.

## Run / Test
```batch
# Windows (production)
start.bat                    # auto-inits DB on first run, then starts Flask on 0.0.0.0:5000

# Development (any Python 3.8+)
python run.py                # same as start.bat but uses system Python
python backup.py backup      # create DB backup
python backup.py restore --file <name>  # restore from backup
python backup.py list        # list backups
```

Default accounts: `admin` / `dept_admin` / `user` — all password `admin123`.

## Tech Stack (locked, do NOT upgrade)
- **Python 3.8.10 64-bit portable** (bundled in `python/`)
- **Flask 2.0.1** + Flask-SQLAlchemy 2.5.1
- **SQLite3** single-file (`data/database.db`)
- **LayUI 2.9.10** (frontend UI framework)
- **KindEditor 4.1.11** (rich text editor)
- **x-spreadsheet** (spreadsheet editor)
- All dependencies in `requirements.txt` — pre-installed into portable Python

## Architecture

### Backend: Flask App Factory pattern
- `app/__init__.py` → `create_app()` factory, registers blueprints and error handlers
- `app/config.py` → hardcoded `Config` class (no `.env` needed)
- `app/extensions.py` → `db = SQLAlchemy()` singleton
- `app/models.py` → 12 SQLAlchemy models (User, Tab, Column, Bulletin, Task, TaskTransfer, OperationLog, Memo, File, SharedFolder, SystemConfig, LoginLog)
- `app/decorators.py` → `@login_required`, `@require_role('dept_admin')`, `@require_super_admin` (super_admin bypasses all checks)
- `app/utils.py` → `add_log()`, `check_visible()`, IP detection, pagination helpers
- `app/database.py` → `init_database()` — `db.create_all()` + seed 3 users + 3 default Tabs

### Blueprints (`app/views/`)
| File | Prefix | Purpose |
|------|--------|---------|
| `auth.py` | `/` | login/logout/profile/password change |
| `admin.py` | `/admin` | user/tab/column/share/log/config CRUD (super_admin only) |
| `tasks.py` | `/tasks` | task CRUD, status workflow, transfer & approval |
| `bulletin.py` | `/bulletin` | tab+column two-level nav, publish/edit/archive/delete |
| `memo.py` | `/memo` | private/public memos, archive |
| `files.py` | `/files` | upload/download/delete + `/api/upload` for KindEditor |
| `__init__.py` | `/` | `index_bp` — dashboard with counts + welcome page |

Permission model: `super_admin` (all) > `dept_admin` (dept-scoped) > `user` (self only). Data filtering in query layer, not just UI.

### Frontend: Server-rendered templates (NO SPA)
- 27 Jinja2 templates, each loaded as standalone page inside iframe tabs
- `base.html` — main layout with left sidebar menu + iframe multi-tab (ES5 tab manager)
- `login.html` — standalone (no iframe), neumorphism style
- Each iframe page includes its own `<style>` and `<script>` — self-contained
- All CSS uses neumorphism design: `background: #e0e5ec`, dual box-shadows (light+dark), rounded corners 12-16px

## Critical Constraints (MUST FOLLOW)
1. **IE11 compatible**: No ES6+ (no `const`/`let`, no arrow functions, no template literals, no `fetch()`, no Promises). Use `var`, `function`, `$.ajax()` (LayUI's built-in jQuery).
2. **No Flexbox/Grid**: Use `float`, `display: table/block/inline-block`, `overflow: hidden` for layouts.
3. **All paths relative**: Code uses `os.path.join(BASE_DIR, ...)`, config uses `BASE_DIR` from `config.py`. Startup scripts use `%~dp0`.
4. **No Chinese in Python**: All code comments and log strings in English. Template UI text in Chinese (end users are Chinese).
5. **Memory <200MB**: Single-process Flask, SQLite WAL mode, paginate 15 items/page, no heavy middleware.
6. **Portable Python at `python\python.exe`**: All deps in `python\Lib\site-packages\`. `start.bat` checks this before running.

## Key Patterns
- **RBAC visibility**: `visible_roles` field stores JSON like `["super_admin","dept_admin"]` or `"all"`. `check_visible()` in `utils.py` handles parsing.
- **DB init auto-detection**: `run.py` checks `data/database.db` exists; if not, calls `init_database()`. No manual setup step.
- **File uploads**: Stored in `data/uploads/YYYY-MM/` with UUID filenames. `File.original_name` preserves original. `File.related_type` + `related_id` for association.
- **Task status machine**: `pending → processing → (completed | transferring → [approve|reject] → processing)` — hardcoded in `tasks.py` without a workflow engine.
- **Bulletin expiration**: Query filter `expire_date >= today OR is_pinned=1` at application layer, no cron needed.

## Template Structure
Every iframe-loaded page is a complete HTML document:
```html
<!DOCTYPE html><html><head>
<meta charset="utf-8"><title>...</title>
<meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
<link rel="stylesheet" href="{{ url_for('static', filename='layui/css/layui.css') }}">
<style>:root { --bg: #e0e5ec; --pri: #4a90d9; } ...</style>
</head><body>...content...</body>
<script src="{{ url_for('static', filename='layui/layui.js') }}"></script>
<script>layui.use(['layer','form'],function(){...});</script>
</html>
```
CSS variables `--bg`, `--pri`, `--sd`, `--sl` provide consistent neumorphism. Buttons use class `n-btn`, inputs use `n-inp`/`n-sel`.
