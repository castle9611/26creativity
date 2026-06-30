# -*- coding: utf-8 -*-
"""
Database migration script for adding performance indexes.
Run once: python python\python.exe app\migrations.py
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from app import create_app
from app.extensions import db


def add_indexes():
    """Add performance indexes to existing database."""
    app = create_app()

    with app.app_context():
        from app.schema import migrate_onlyoffice_schema
        migrate_onlyoffice_schema()
        print('[OK] ONLYOFFICE document schema ready')
        # First, migrate tabs table for new columns
        tab_migrations = [
            "ALTER TABLE tabs ADD COLUMN tab_type VARCHAR(20) DEFAULT 'bulletin'",
            "ALTER TABLE tabs ADD COLUMN icon VARCHAR(50) DEFAULT '📁'",
            "ALTER TABLE tabs ADD COLUMN url VARCHAR(500) DEFAULT ''",
            "ALTER TABLE tabs ADD COLUMN parent_id INTEGER",
        ]

        for sql in tab_migrations:
            try:
                db.session.execute(db.text(sql))
                db.session.commit()
                print(f"[OK] Tab column added")
            except Exception as e:
                if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                    print(f"[SKIP] Tab column already exists")
                else:
                    print(f"[WARN] Tab migration: {e}")

        # Migrate columns table: add category_id and change tab_id reference
        column_migrations = [
            "ALTER TABLE columns ADD COLUMN category_id INTEGER",
        ]

        for sql in column_migrations:
            try:
                db.session.execute(db.text(sql))
                db.session.commit()
                print(f"[OK] Column migration: category_id added")
            except Exception as e:
                if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                    print(f"[SKIP] Column category_id already exists")
                else:
                    print(f"[WARN] Column migration: {e}")

        # If tab_id exists in columns, migrate data to category_id using bulletin_categories as bridge
        try:
            result = db.session.execute(db.text("PRAGMA table_info(columns)"))
            columns_info = [row[1] for row in result]
            if 'tab_id' in columns_info and 'category_id' in columns_info:
                # Migrate data: update category_id from bulletin_categories via tab_id
                db.session.execute(db.text("""
                    UPDATE columns
                    SET category_id = (
                        SELECT bc.id FROM bulletin_categories bc
                        WHERE bc.tab_id = columns.tab_id
                        LIMIT 1
                    )
                    WHERE tab_id IS NOT NULL AND category_id IS NULL
                """))
                db.session.commit()
                print("[OK] Column data migrated from tab_id to category_id")
        except Exception as e:
            print(f"[WARN] Column data migration: {e}")

        # Add avatar column to users table (2026-06-09)
        try:
            db.session.execute(db.text(
                "ALTER TABLE users ADD COLUMN avatar VARCHAR(500) DEFAULT ''"
            ))
            db.session.commit()
            print("[OK] Added avatar column to users table")
        except Exception as e:
            if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                print("[SKIP] avatar column already exists")
            else:
                print(f"[WARN] avatar migration: {e}")

        # Create online_documents table (2026-06-09)
        try:
            db.session.execute(db.text("""
                CREATE TABLE IF NOT EXISTS online_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title VARCHAR(500) NOT NULL,
                    content TEXT DEFAULT '',
                    doc_type VARCHAR(20) DEFAULT 'rich',
                    status VARCHAR(20) DEFAULT 'draft',
                    view_roles VARCHAR(200) DEFAULT 'all',
                    edit_roles VARCHAR(200) DEFAULT '["super_admin","dept_admin"]',
                    is_active INTEGER DEFAULT 1,
                    related_type VARCHAR(50) DEFAULT '',
                    related_id INTEGER DEFAULT 0,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            """))
            db.session.commit()
            print("[OK] online_documents table created")
        except Exception as e:
            if 'already exists' in str(e).lower():
                print("[SKIP] online_documents table already exists")
            else:
                print(f"[WARN] online_documents table: {e}")

        # Create spreadsheets table (2026-06-09)
        try:
            db.session.execute(db.text("""
                CREATE TABLE IF NOT EXISTS spreadsheets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(500) NOT NULL,
                    sheet_data TEXT DEFAULT '',
                    status VARCHAR(20) DEFAULT 'draft',
                    view_roles VARCHAR(200) DEFAULT 'all',
                    edit_roles VARCHAR(200) DEFAULT '["super_admin","dept_admin"]',
                    is_active INTEGER DEFAULT 1,
                    related_type VARCHAR(50) DEFAULT '',
                    related_id INTEGER DEFAULT 0,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            """))
            db.session.commit()
            print("[OK] spreadsheets table created")
        except Exception as e:
            if 'already exists' in str(e).lower():
                print("[SKIP] spreadsheets table already exists")
            else:
                print(f"[WARN] spreadsheets table: {e}")

        indexes = [
            # User indexes
            "CREATE INDEX IF NOT EXISTS ix_users_role ON users(role)",
            "CREATE INDEX IF NOT EXISTS ix_users_department ON users(department)",
            "CREATE INDEX IF NOT EXISTS ix_users_is_active ON users(is_active)",

            # Task indexes
            "CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks(status)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_priority ON tasks(priority)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_department ON tasks(department)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_assignee_id ON tasks(assignee_id)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_creator_id ON tasks(creator_id)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_created_at ON tasks(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_tasks_deadline ON tasks(deadline)",

            # Bulletin indexes
            "CREATE INDEX IF NOT EXISTS ix_bulletins_status ON bulletins(status)",
            "CREATE INDEX IF NOT EXISTS ix_bulletins_column_id ON bulletins(column_id)",
            "CREATE INDEX IF NOT EXISTS ix_bulletins_is_pinned ON bulletins(is_pinned)",
            "CREATE INDEX IF NOT EXISTS ix_bulletins_expire_date ON bulletins(expire_date)",
            "CREATE INDEX IF NOT EXISTS ix_bulletins_created_at ON bulletins(created_at)",

            # Column indexes
            "CREATE INDEX IF NOT EXISTS ix_columns_tab_id ON columns(tab_id)",
            "CREATE INDEX IF NOT EXISTS ix_columns_is_active ON columns(is_active)",

            # Tab indexes
            "CREATE INDEX IF NOT EXISTS ix_tabs_is_active ON tabs(is_active)",
            "CREATE INDEX IF NOT EXISTS ix_tabs_is_pinned ON tabs(is_pinned)",

            # Memo indexes
            "CREATE INDEX IF NOT EXISTS ix_memos_created_by ON memos(created_by)",
            "CREATE INDEX IF NOT EXISTS ix_memos_memo_type ON memos(memo_type)",
            "CREATE INDEX IF NOT EXISTS ix_memos_is_archived ON memos(is_archived)",
            "CREATE INDEX IF NOT EXISTS ix_memos_created_at ON memos(created_at)",

            # File indexes
            "CREATE INDEX IF NOT EXISTS ix_files_uploaded_by ON files(uploaded_by)",
            "CREATE INDEX IF NOT EXISTS ix_files_related_type ON files(related_type)",
            "CREATE INDEX IF NOT EXISTS ix_files_related_id ON files(related_id)",
            "CREATE INDEX IF NOT EXISTS ix_files_is_deleted ON files(is_deleted)",
            "CREATE INDEX IF NOT EXISTS ix_files_created_at ON files(created_at)",

            # Log indexes
            "CREATE INDEX IF NOT EXISTS ix_operation_logs_user_id ON operation_logs(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_operation_logs_action ON operation_logs(action)",
            "CREATE INDEX IF NOT EXISTS ix_operation_logs_created_at ON operation_logs(created_at)",

            # Login log indexes
            "CREATE INDEX IF NOT EXISTS ix_login_logs_user_id ON login_logs(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_login_logs_login_time ON login_logs(login_time)",

            # TaskTransfer indexes
            "CREATE INDEX IF NOT EXISTS ix_task_transfers_task_id ON task_transfers(task_id)",
            "CREATE INDEX IF NOT EXISTS ix_task_transfers_from_user_id ON task_transfers(from_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_task_transfers_to_user_id ON task_transfers(to_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_task_transfers_status ON task_transfers(status)",
            "CREATE INDEX IF NOT EXISTS ix_task_transfers_reviewed_by ON task_transfers(reviewed_by)",

            # SharedFolder indexes
            "CREATE INDEX IF NOT EXISTS ix_shared_folders_is_active ON shared_folders(is_active)",

            # SystemConfig indexes
            "CREATE INDEX IF NOT EXISTS ix_system_config_key ON system_config(config_key)",
        ]

        # Create bulletin_attachments table if not exists
        try:
            db.session.execute(db.text("""
                CREATE TABLE IF NOT EXISTS bulletin_attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bulletin_id INTEGER NOT NULL,
                    filename VARCHAR(500) NOT NULL,
                    original_name VARCHAR(500) NOT NULL,
                    file_path VARCHAR(1000) NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    file_type VARCHAR(100) DEFAULT '',
                    uploaded_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bulletin_id) REFERENCES bulletins(id) ON DELETE CASCADE
                )
            """))
            db.session.commit()
            print("[OK] bulletin_attachments table created")
        except Exception as e:
            if 'already exists' in str(e).lower():
                print("[SKIP] bulletin_attachments table already exists")
            else:
                print(f"[WARN] bulletin_attachments table: {e}")

        bulletin_attachment_indexes = [
            "CREATE INDEX IF NOT EXISTS ix_bulletin_attachments_bulletin_id ON bulletin_attachments(bulletin_id)",
            "CREATE INDEX IF NOT EXISTS ix_bulletin_attachments_uploaded_by ON bulletin_attachments(uploaded_by)",
        ]
        for idx_sql in bulletin_attachment_indexes:
            try:
                db.session.execute(db.text(idx_sql))
                db.session.commit()
                idx_name = idx_sql.split('IF NOT EXISTS ')[1].split(' ON')[0]
                print(f"[OK] {idx_name}")
            except Exception as e:
                err_msg = str(e)[:60]
                print(f"[SKIP] {idx_name} ({err_msg})")

        success_count = 0
        skip_count = 0

        for idx_sql in indexes:
            try:
                db.session.execute(db.text(idx_sql))
                db.session.commit()
                success_count += 1
                idx_name = idx_sql.split('IF NOT EXISTS ')[1].split(' ON')[0]
                print(f"[OK] {idx_name}")
            except Exception as e:
                skip_count += 1
                idx_name = idx_sql.split('IF NOT EXISTS ')[1].split(' ON')[0] if 'IF NOT EXISTS' in idx_sql else idx_sql[:50]
                err_msg = str(e)[:60]
                print(f"[SKIP] {idx_name} ({err_msg})")

        print(f"\n{'='*50}")
        print(f"Database migration completed!")
        print(f"  - Indexes created: {success_count}")
        print(f"  - Skipped (already exists or error): {skip_count}")
        print(f"{'='*50}")


def vacuum_database():
    """Optimize database file after adding indexes."""
    app = create_app()

    with app.app_context():
        try:
            # SQLite ANALYZE to update statistics
            db.session.execute(db.text("ANALYZE"))
            db.session.commit()
            print("[OK] Database statistics updated")
        except Exception as e:
            print(f"[WARN] Optimization error: {e}")


if __name__ == '__main__':
    print("Starting database migration...")
    print("")
    add_indexes()
    print("")
    vacuum_database()
    print("")
    print("Migration complete! Restart the application to apply changes.")
