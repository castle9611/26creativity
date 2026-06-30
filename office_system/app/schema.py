# -*- coding: utf-8 -*-
"""Small, idempotent SQLite compatibility migrations."""
from app.extensions import db


ONLINE_DOCUMENT_COLUMNS = {
    'editor_kind': "VARCHAR(20) NOT NULL DEFAULT 'legacy_html'",
    'office_type': "VARCHAR(10) DEFAULT ''", 'file_ext': "VARCHAR(10) DEFAULT ''",
    'original_filename': "VARCHAR(500) DEFAULT ''", 'stored_filename': "VARCHAR(100) DEFAULT ''",
    'storage_relpath': "VARCHAR(1000) DEFAULT ''", 'mime_type': "VARCHAR(150) DEFAULT ''",
    'file_size': 'INTEGER DEFAULT 0', 'file_version': 'INTEGER NOT NULL DEFAULT 1',
    'document_key': "VARCHAR(100) DEFAULT ''", 'checksum': "VARCHAR(64) DEFAULT ''",
    'last_editor_id': 'INTEGER', 'last_saved_at': 'DATETIME'
}
DOC_VERSION_COLUMNS = {
    'storage_relpath': "VARCHAR(1000) DEFAULT ''", 'file_size': 'INTEGER DEFAULT 0',
    'checksum': "VARCHAR(64) DEFAULT ''",
    'version_kind': "VARCHAR(20) NOT NULL DEFAULT 'legacy_html'"
}


def migrate_onlyoffice_schema():
    inspector = db.inspect(db.engine)
    tables = set(inspector.get_table_names())
    if 'online_documents' not in tables or 'doc_versions' not in tables:
        db.create_all()
        inspector = db.inspect(db.engine)
    for table, definitions in (('online_documents', ONLINE_DOCUMENT_COLUMNS),
                               ('doc_versions', DOC_VERSION_COLUMNS)):
        existing = {c['name'] for c in inspector.get_columns(table)}
        for name, definition in definitions.items():
            if name not in existing:
                db.session.execute(db.text('ALTER TABLE {} ADD COLUMN {} {}'.format(table, name, definition)))
    for sql in (
        'CREATE INDEX IF NOT EXISTS ix_online_documents_editor_kind ON online_documents(editor_kind)',
        'CREATE INDEX IF NOT EXISTS ix_online_documents_file_ext ON online_documents(file_ext)',
        'CREATE INDEX IF NOT EXISTS ix_online_documents_document_key ON online_documents(document_key)',
        'CREATE INDEX IF NOT EXISTS ix_online_documents_last_editor_id ON online_documents(last_editor_id)',
        'CREATE INDEX IF NOT EXISTS ix_doc_versions_version_kind ON doc_versions(version_kind)'):
        db.session.execute(db.text(sql))
    db.session.execute(db.text("UPDATE online_documents SET editor_kind='legacy_html' WHERE editor_kind IS NULL OR editor_kind=''"))
    db.session.execute(db.text("UPDATE doc_versions SET version_kind='legacy_html' WHERE version_kind IS NULL OR version_kind=''"))
    db.session.commit()
