# -*- coding: utf-8 -*-
"""
Safe database migration script.
Adds new columns/tables to existing database WITHOUT data loss.
Only run when upgrading from an older schema version.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from app import create_app
from app.extensions import db
from sqlalchemy import text


def migrate():
    """Apply schema migrations safely."""
    app = create_app()

    with app.app_context():
        print('[INFO] Starting database migration...')

        # Get existing columns to check what needs adding
        existing_cols = db.session.execute(text("PRAGMA table_info(tabs)")).fetchall()
        existing_col_names = [row[1] for row in existing_cols]

        # Migration 1: Add tab_type to tabs
        if 'tab_type' not in existing_col_names:
            print('[MIG] Adding tabs.tab_type...')
            db.session.execute(text("ALTER TABLE tabs ADD COLUMN tab_type VARCHAR(20) DEFAULT 'bulletin'"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 2: Add icon to tabs
        if 'icon' not in existing_col_names:
            print('[MIG] Adding tabs.icon...')
            db.session.execute(text("ALTER TABLE tabs ADD COLUMN icon VARCHAR(50) DEFAULT ''"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 3: Add url to tabs
        if 'url' not in existing_col_names:
            print('[MIG] Adding tabs.url...')
            db.session.execute(text("ALTER TABLE tabs ADD COLUMN url VARCHAR(500) DEFAULT ''"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 4: Add parent_id to tabs (for future use)
        if 'parent_id' not in existing_col_names:
            print('[MIG] Adding tabs.parent_id...')
            db.session.execute(text("ALTER TABLE tabs ADD COLUMN parent_id INTEGER"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 5: Add category_id to columns table
        existing_cols_cols = db.session.execute(text("PRAGMA table_info(columns)")).fetchall()
        existing_cols_col_names = [row[1] for row in existing_cols_cols]
        if 'category_id' not in existing_cols_col_names:
            print('[MIG] Adding columns.category_id...')
            db.session.execute(text("ALTER TABLE columns ADD COLUMN category_id INTEGER"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 6: Create new tables if they don't exist
        existing_tables = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
        existing_table_names = [row[0] for row in existing_tables]

        if 'task_categories' not in existing_table_names:
            print('[MIG] Creating task_categories...')
            db.create_all()  # creates all missing tables
            print('[MIG]   Done')

        if 'bulletin_categories' not in existing_table_names:
            print('[MIG] Creating bulletin_categories (via create_all)...')
            db.create_all()
            print('[MIG]   Done')

        # Migration 7: Create any remaining missing tables (bulletin_attachments, etc.)
        if 'bulletin_attachments' not in existing_table_names:
            print('[MIG] Creating missing tables via create_all...')
            db.create_all()
            print('[MIG]   Done')

        # Migration 8: Add category_id to bulletins + make column_id nullable
        existing_bulletin_cols = db.session.execute(text("PRAGMA table_info(bulletins)")).fetchall()

        # Check if column_id is still NOT NULL (need to recreate table)
        col_id_info = [r for r in existing_bulletin_cols if r[1] == 'column_id']
        column_id_not_null = col_id_info and col_id_info[0][3] == 1

        if column_id_not_null:
            print('[MIG] Making bulletins.column_id nullable + adding category_id...')
            has_cat_id = any(r[1] == 'category_id' for r in existing_bulletin_cols)
            cat_part = ', category_id INTEGER REFERENCES bulletin_categories(id) ON DELETE SET NULL'
            sel_cols = 'id, column_id, COALESCE(category_id, NULL), title, content, attachments, is_pinned, is_active, expire_date, status, created_by, created_at, updated_at'
            if not has_cat_id:
                sel_cols = sel_cols.replace('COALESCE(category_id, NULL)', 'NULL')

            db.session.execute(text(f"""
                CREATE TABLE bulletins_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    column_id INTEGER REFERENCES columns(id) ON DELETE SET NULL
                    {cat_part},
                    title VARCHAR(500) NOT NULL,
                    content TEXT,
                    attachments TEXT DEFAULT '[]',
                    is_pinned INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    expire_date DATE,
                    status VARCHAR(20) DEFAULT 'published',
                    created_by INTEGER REFERENCES users(id),
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
            db.session.execute(text(f"INSERT INTO bulletins_new SELECT {sel_cols} FROM bulletins"))
            db.session.execute(text("DROP TABLE bulletins"))
            db.session.execute(text("ALTER TABLE bulletins_new RENAME TO bulletins"))
            for idx_col in ['column_id', 'category_id', 'is_pinned', 'is_active', 'expire_date', 'status', 'created_by', 'created_at']:
                db.session.execute(text(f"CREATE INDEX IF NOT EXISTS ix_bulletins_{idx_col} ON bulletins({idx_col})"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 9: Add progress to tasks table
        existing_task_cols = db.session.execute(text("PRAGMA table_info(tasks)")).fetchall()
        existing_task_col_names = [row[1] for row in existing_task_cols]
        if 'progress' not in existing_task_col_names:
            print('[MIG] Adding tasks.progress...')
            db.session.execute(text("ALTER TABLE tasks ADD COLUMN progress INTEGER DEFAULT 0"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 10: Add task reminder acknowledgement field
        existing_task_cols = db.session.execute(text("PRAGMA table_info(tasks)")).fetchall()
        existing_task_col_names = [row[1] for row in existing_task_cols]
        if 'reminder_seen_at' not in existing_task_col_names:
            print('[MIG] Adding tasks.reminder_seen_at...')
            db.session.execute(text("ALTER TABLE tasks ADD COLUMN reminder_seen_at DATETIME"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 11: Create read/comment/memo group tables
        existing_tables = db.session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
        existing_table_names = [row[0] for row in existing_tables]

        missing_new_tables = [
            'read_records',
            'comments',
            'memo_groups',
        ]
        if any(t not in existing_table_names for t in missing_new_tables):
            print('[MIG] Creating read/comment/memo group tables...')
            db.create_all()
            print('[MIG]   Done')

        # Migration 12: Add group_id to memos
        existing_memo_cols = db.session.execute(text("PRAGMA table_info(memos)")).fetchall()
        existing_memo_col_names = [row[1] for row in existing_memo_cols]
        if 'group_id' not in existing_memo_col_names:
            print('[MIG] Adding memos.group_id...')
            db.session.execute(text("ALTER TABLE memos ADD COLUMN group_id INTEGER"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_memos_group_id ON memos(group_id)"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 13: Add avatar to users
        existing_user_cols = db.session.execute(text("PRAGMA table_info(users)")).fetchall()
        existing_user_col_names = [row[1] for row in existing_user_cols]
        if 'avatar' not in existing_user_col_names:
            print('[MIG] Adding users.avatar...')
            db.session.execute(text("ALTER TABLE users ADD COLUMN avatar VARCHAR(500) DEFAULT ''"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 14: Create online_documents table
        if 'online_documents' not in existing_table_names:
            print('[MIG] Creating online_documents table...')
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS online_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title VARCHAR(500) NOT NULL,
                    content TEXT DEFAULT '',
                    doc_type VARCHAR(20) DEFAULT 'rich',
                    status VARCHAR(20) DEFAULT 'draft' CHECK(status IN ('draft','published','archived')),
                    view_roles VARCHAR(200) DEFAULT 'all',
                    edit_roles VARCHAR(200) DEFAULT '["super_admin","dept_admin"]',
                    is_active INTEGER DEFAULT 1,
                    related_type VARCHAR(50) DEFAULT '',
                    related_id INTEGER DEFAULT 0,
                    created_by INTEGER REFERENCES users(id),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            for idx_col in ['created_by', 'status', 'is_active']:
                db.session.execute(text(f"CREATE INDEX IF NOT EXISTS ix_online_documents_{idx_col} ON online_documents({idx_col})"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 15: Create spreadsheets table
        if 'spreadsheets' not in existing_table_names:
            print('[MIG] Creating spreadsheets table...')
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS spreadsheets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(500) NOT NULL,
                    sheet_data TEXT DEFAULT '',
                    status VARCHAR(20) DEFAULT 'draft' CHECK(status IN ('draft','published','archived')),
                    view_roles VARCHAR(200) DEFAULT 'all',
                    edit_roles VARCHAR(200) DEFAULT '["super_admin","dept_admin"]',
                    is_active INTEGER DEFAULT 1,
                    related_type VARCHAR(50) DEFAULT '',
                    related_id INTEGER DEFAULT 0,
                    created_by INTEGER REFERENCES users(id),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            for idx_col in ['created_by', 'status', 'is_active']:
                db.session.execute(text(f"CREATE INDEX IF NOT EXISTS ix_spreadsheets_{idx_col} ON spreadsheets({idx_col})"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 16: Add comment reply/rating columns
        existing_comment_cols = db.session.execute(text("PRAGMA table_info(comments)")).fetchall()
        existing_comment_col_names = [row[1] for row in existing_comment_cols]
        if 'parent_id' not in existing_comment_col_names:
            print('[MIG] Adding comments.parent_id...')
            db.session.execute(text("ALTER TABLE comments ADD COLUMN parent_id INTEGER REFERENCES comments(id)"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_comments_parent_id ON comments(parent_id)"))
            db.session.commit()
            print('[MIG]   Done')
        if 'likes' not in existing_comment_col_names:
            print('[MIG] Adding comments.likes/dislikes...')
            db.session.execute(text("ALTER TABLE comments ADD COLUMN likes INTEGER DEFAULT 0"))
            db.session.execute(text("ALTER TABLE comments ADD COLUMN dislikes INTEGER DEFAULT 0"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 17: Create comment_votes table
        if 'comment_votes' not in existing_table_names:
            print('[MIG] Creating comment_votes table...')
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS comment_votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    comment_id INTEGER NOT NULL REFERENCES comments(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    vote INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(comment_id, user_id)
                )
            """))
            for idx_col in ['comment_id', 'user_id']:
                db.session.execute(text(f"CREATE INDEX IF NOT EXISTS ix_comment_votes_{idx_col} ON comment_votes({idx_col})"))
            db.session.commit()
            print('[MIG]   Done')

        # Migration 18: Create doc_versions and sheet_version tables
        if 'doc_versions' not in existing_table_names:
            print('[MIG] Creating doc_versions table...')
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS doc_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER NOT NULL REFERENCES online_documents(id) ON DELETE CASCADE,
                    content TEXT DEFAULT '',
                    title VARCHAR(500) DEFAULT '',
                    version_num INTEGER NOT NULL,
                    change_summary VARCHAR(500) DEFAULT '',
                    created_by INTEGER REFERENCES users(id),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            for idx_col in ['doc_id', 'created_by']:
                db.session.execute(text(f"CREATE INDEX IF NOT EXISTS ix_doc_versions_{idx_col} ON doc_versions({idx_col})"))
            db.session.commit()
            print('[MIG]   Done')
        if 'sheet_versions' not in existing_table_names:
            print('[MIG] Creating sheet_versions table...')
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS sheet_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sheet_id INTEGER NOT NULL REFERENCES spreadsheets(id) ON DELETE CASCADE,
                    sheet_data TEXT DEFAULT '',
                    name VARCHAR(500) DEFAULT '',
                    version_num INTEGER NOT NULL,
                    change_summary VARCHAR(500) DEFAULT '',
                    created_by INTEGER REFERENCES users(id),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            for idx_col in ['sheet_id', 'created_by']:
                db.session.execute(text(f"CREATE INDEX IF NOT EXISTS ix_sheet_versions_{idx_col} ON sheet_versions({idx_col})"))
            db.session.commit()
            print('[MIG]   Done')

        print('[OK] Migration complete - no data lost')
        print('[INFO] Restart the server for changes to take effect')


if __name__ == '__main__':
    migrate()
