# -*- coding: utf-8 -*-
"""
Data models (Flask-SQLAlchemy ORM).
All models map to SQLite database tables.
"""
from app.extensions import db
from datetime import datetime


class User(db.Model):
    """User accounts table."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    real_name = db.Column(db.String(50), default='')
    role = db.Column(db.String(20), nullable=False, default='user', index=True)
    department = db.Column(db.String(100), default='', index=True)
    avatar = db.Column(db.String(500), default='')  # URL or path to custom avatar image
    is_active = db.Column(db.Integer, default=1, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'real_name': self.real_name,
            'role': self.role,
            'department': self.department,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }


class LoginLog(db.Model):
    """Login audit log."""
    __tablename__ = 'login_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    ip_address = db.Column(db.String(45), default='', index=True)
    login_time = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', backref=db.backref('login_logs', lazy='dynamic'))


class Tab(db.Model):
    """Tab labels - can be bulletin categories or direct link shortcuts."""
    __tablename__ = 'tabs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    tab_type = db.Column(db.String(20), default='bulletin')  # 'bulletin' or 'link'
    icon = db.Column(db.String(50), default='📁')  # emoji icon
    url = db.Column(db.String(500), default='')  # for link type tabs
    parent_id = db.Column(db.Integer, db.ForeignKey('tabs.id'), nullable=True)  # for grouping
    sort_order = db.Column(db.Integer, default=0, index=True)
    is_pinned = db.Column(db.Integer, default=0, index=True)
    is_active = db.Column(db.Integer, default=1, index=True)
    visible_roles = db.Column(db.String(200), default='all')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('tabs', lazy='dynamic'))
    children = db.relationship('Tab', backref=db.backref('parent', remote_side=[id]),
                              lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'tab_type': self.tab_type,
            'icon': self.icon,
            'url': self.url,
            'parent_id': self.parent_id,
            'sort_order': self.sort_order,
            'is_pinned': self.is_pinned,
            'is_active': self.is_active,
            'visible_roles': self.visible_roles,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }


class Column(db.Model):
    """Columns under each business category. Each category can have many columns."""
    __tablename__ = 'columns'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    category_id = db.Column(db.Integer, db.ForeignKey('bulletin_categories.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    sort_order = db.Column(db.Integer, default=0, index=True)
    is_active = db.Column(db.Integer, default=1, index=True)
    visible_roles = db.Column(db.String(200), default='all')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('columns', lazy='dynamic'))
    category = db.relationship('BulletinCategory', back_populates='column_items')
    bulletins = db.relationship('Bulletin', backref='column', lazy='dynamic',
                               cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'category_id': self.category_id,
            'name': self.name,
            'description': self.description,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'visible_roles': self.visible_roles,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }


class Bulletin(db.Model):
    """Bulletin / notice / announcement content."""
    __tablename__ = 'bulletins'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    column_id = db.Column(db.Integer, db.ForeignKey('columns.id', ondelete='SET NULL'),
                          nullable=True, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('bulletin_categories.id', ondelete='SET NULL'),
                            nullable=True, index=True)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, default='')
    nextcloud_url = db.Column(db.String(2000), default='')
    attachments = db.Column(db.Text, default='[]')
    is_pinned = db.Column(db.Integer, default=0, index=True)
    is_active = db.Column(db.Integer, default=1, index=True)
    expire_date = db.Column(db.Date, nullable=True, index=True)
    status = db.Column(db.String(20), default='published', index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('bulletins', lazy='dynamic'))
    files = db.relationship('BulletinAttachment', backref='bulletin', lazy='dynamic',
                           cascade='all, delete-orphan')
    category = db.relationship('BulletinCategory', backref=db.backref('bulletins', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'column_id': self.column_id,
            'title': self.title,
            'content': self.content,
            'nextcloud_url': self.nextcloud_url,
            'attachments': self.attachments,
            'is_pinned': self.is_pinned,
            'is_active': self.is_active,
            'expire_date': self.expire_date.strftime('%Y-%m-%d') if self.expire_date else '',
            'status': self.status,
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else ''
        }


class BulletinAttachment(db.Model):
    """Bulletin attachment files."""
    __tablename__ = 'bulletin_attachments'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bulletin_id = db.Column(db.Integer, db.ForeignKey('bulletins.id', ondelete='CASCADE'),
                            nullable=False, index=True)
    filename = db.Column(db.String(500), nullable=False)
    original_name = db.Column(db.String(500), nullable=False)
    file_path = db.Column(db.String(1000), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    file_type = db.Column(db.String(100), default='')
    category_id = db.Column(db.Integer, db.ForeignKey('bulletin_categories.id'), nullable=True, index=True)
    column_id = db.Column(db.Integer, db.ForeignKey('columns.id', ondelete='SET NULL'), nullable=True, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploader = db.relationship('User', backref=db.backref('bulletin_attachments', lazy='dynamic'))


class Task(db.Model):
    """Task / project management."""
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, default='')
    nextcloud_url = db.Column(db.String(2000), default='')
    priority = db.Column(db.String(20), default='normal', index=True)
    department = db.Column(db.String(100), default='', index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('bulletin_categories.id'), nullable=True, index=True)
    column_id = db.Column(db.Integer, db.ForeignKey('columns.id', ondelete='SET NULL'), nullable=True, index=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    deadline = db.Column(db.Date, nullable=True, index=True)
    attachments = db.Column(db.Text, default='[]')
    progress = db.Column(db.Integer, default=0, index=True)
    status = db.Column(db.String(20), default='pending', index=True)
    reminder_seen_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignee = db.relationship('User', foreign_keys=[assignee_id],
                                backref=db.backref('assigned_tasks', lazy='dynamic'))
    creator = db.relationship('User', foreign_keys=[creator_id],
                               backref=db.backref('created_tasks', lazy='dynamic'))
    category = db.relationship('BulletinCategory', backref=db.backref('tasks', lazy='dynamic'))
    assignee_links = db.relationship('TaskAssignee', back_populates='task',
                                     lazy='dynamic', cascade='all, delete-orphan')

    @property
    def assignee_ids(self):
        ids = [link.user_id for link in self.assignee_links.all()]
        if not ids and self.assignee_id:
            ids = [self.assignee_id]
        return ids

    @property
    def assignees(self):
        users = [link.user for link in self.assignee_links.all() if link.user]
        if not users and self.assignee:
            users = [self.assignee]
        return users

    @property
    def assignee_names(self):
        names = [(user.real_name or user.username) for user in self.assignees]
        return '、'.join(names) if names else '未指定'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'nextcloud_url': self.nextcloud_url,
            'priority': self.priority,
            'department': self.department,
            'category_id': self.category_id,
            'assignee_id': self.assignee_id,
            'assignee_ids': self.assignee_ids,
            'creator_id': self.creator_id,
            'deadline': self.deadline.strftime('%Y-%m-%d') if self.deadline else '',
            'attachments': self.attachments,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else ''
        }


class TaskAssignee(db.Model):
    """Many-to-many task assignees."""
    __tablename__ = 'task_assignees'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('task_id', 'user_id', name='uq_task_assignee'),)

    task = db.relationship('Task', back_populates='assignee_links')
    user = db.relationship('User', backref=db.backref('task_assignments', lazy='dynamic'))


class TaskTransfer(db.Model):
    """Task transfer / handover records."""
    __tablename__ = 'task_transfers'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    reason = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='pending', index=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    review_comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    task = db.relationship('Task', backref=db.backref('transfers', lazy='dynamic'))
    from_user = db.relationship('User', foreign_keys=[from_user_id],
                                 backref=db.backref('transfers_from', lazy='dynamic'))
    to_user = db.relationship('User', foreign_keys=[to_user_id],
                               backref=db.backref('transfers_to', lazy='dynamic'))
    reviewer = db.relationship('User', foreign_keys=[reviewed_by],
                                backref=db.backref('transfers_reviewed', lazy='dynamic'))


class ReadRecord(db.Model):
    """Read/unread tracking for tasks and bulletins."""
    __tablename__ = 'read_records'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    target_type = db.Column(db.String(30), nullable=False, index=True)
    target_id = db.Column(db.Integer, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    read_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', backref=db.backref('read_records', lazy='dynamic'))


class Comment(db.Model):
    """Comments for tasks and bulletins with threaded replies."""
    __tablename__ = 'comments'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    target_type = db.Column(db.String(30), nullable=False, index=True)
    target_id = db.Column(db.Integer, nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=True, index=True)
    content = db.Column(db.Text, nullable=False)
    likes = db.Column(db.Integer, default=0)
    dislikes = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    is_deleted = db.Column(db.Integer, default=0, index=True)

    creator = db.relationship('User', backref=db.backref('comments', lazy='dynamic'))
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]),
                              lazy='dynamic', cascade='all, delete-orphan')


class CommentVote(db.Model):
    """Tracks who liked/disliked which comment (prevents double-voting)."""
    __tablename__ = 'comment_votes'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    vote = db.Column(db.Integer, default=1)  # 1 = like, -1 = dislike
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('comment_id', 'user_id', name='uq_comment_vote'),)

    comment = db.relationship('Comment', backref=db.backref('votes', lazy='dynamic', cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('comment_votes', lazy='dynamic'))


class OperationLog(db.Model):
    """Universal operation audit log."""
    __tablename__ = 'operation_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    action = db.Column(db.String(50), nullable=False, index=True)
    target_type = db.Column(db.String(50), default='', index=True)
    target_id = db.Column(db.Integer, default=0)
    content = db.Column(db.Text, default='')
    ip_address = db.Column(db.String(45), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', backref=db.backref('operation_logs', lazy='dynamic'))


class QuickLink(db.Model):
    """Configurable quick links for the public portal and user workbench."""
    __tablename__ = 'quick_links'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    scope = db.Column(db.String(20), default='user', index=True)  # public or user
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    url = db.Column(db.String(1000), nullable=False)
    icon = db.Column(db.String(50), default='gen-link')
    sort_order = db.Column(db.Integer, default=0, index=True)
    is_active = db.Column(db.Integer, default=1, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = db.relationship('User', foreign_keys=[user_id],
                            backref=db.backref('quick_links', lazy='dynamic'))
    creator = db.relationship('User', foreign_keys=[created_by])

    def to_dict(self):
        return {
            'id': self.id,
            'scope': self.scope,
            'user_id': self.user_id,
            'name': self.name,
            'url': self.url,
            'icon': self.icon,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else ''
        }


class Memo(db.Model):
    """Personal and public memos."""
    __tablename__ = 'memos'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, default='')
    nextcloud_url = db.Column(db.String(2000), default='')
    memo_type = db.Column(db.String(20), default='private', index=True)
    group_id = db.Column(db.Integer, db.ForeignKey('memo_groups.id'), nullable=True, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('bulletin_categories.id'), nullable=True, index=True)
    column_id = db.Column(db.Integer, db.ForeignKey('columns.id', ondelete='SET NULL'), nullable=True, index=True)
    visible_roles = db.Column(db.String(200), default='all')
    is_archived = db.Column(db.Integer, default=0, index=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('memos', lazy='dynamic'))
    group = db.relationship('MemoGroup', back_populates='memos')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'nextcloud_url': self.nextcloud_url,
            'memo_type': self.memo_type,
            'group_id': self.group_id,
            'visible_roles': self.visible_roles,
            'is_archived': self.is_archived,
            'expires_at': self.expires_at.strftime('%Y-%m-%d %H:%M:%S') if self.expires_at else '',
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else ''
        }


class MemoGroup(db.Model):
    """User-defined memo grouping."""
    __tablename__ = 'memo_groups'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    memo_type = db.Column(db.String(20), default='private', index=True)
    sort_order = db.Column(db.Integer, default=0, index=True)
    is_active = db.Column(db.Integer, default=1, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('memo_groups', lazy='dynamic'))
    memos = db.relationship('Memo', back_populates='group', lazy='dynamic')


class File(db.Model):
    """Uploaded files metadata."""
    __tablename__ = 'files'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    filename = db.Column(db.String(500), nullable=False)
    original_name = db.Column(db.String(500), nullable=False)
    file_path = db.Column(db.String(1000), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    file_type = db.Column(db.String(100), default='')
    category_id = db.Column(db.Integer, db.ForeignKey('bulletin_categories.id'), nullable=True, index=True)
    column_id = db.Column(db.Integer, db.ForeignKey('columns.id', ondelete='SET NULL'), nullable=True, index=True)
    related_type = db.Column(db.String(50), default='', index=True)
    related_id = db.Column(db.Integer, default=0, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    is_deleted = db.Column(db.Integer, default=0, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploader = db.relationship('User', backref=db.backref('files', lazy='dynamic'))
    category = db.relationship('BulletinCategory', backref=db.backref('files', lazy='dynamic'))
    relation_links = db.relationship('FileRelation', back_populates='file',
                                     lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'original_name': self.original_name,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'file_type': self.file_type,
            'category_id': self.category_id,
            'column_id': self.column_id,
            'related_type': self.related_type,
            'related_id': self.related_id,
            'uploaded_by': self.uploaded_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }


class FileSearchText(db.Model):
    """Offline extracted file text; rebuilt independently of business data."""
    __tablename__ = 'file_search_text'

    file_id = db.Column(db.Integer, db.ForeignKey('files.id', ondelete='CASCADE'), primary_key=True)
    content = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='pending', index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)


class FileRelation(db.Model):
    """Many-to-many style links from uploaded files to business records."""
    __tablename__ = 'file_relations'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    file_id = db.Column(db.Integer, db.ForeignKey('files.id', ondelete='CASCADE'), nullable=False, index=True)
    target_type = db.Column(db.String(50), nullable=False, index=True)
    target_id = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('file_id', 'target_type', 'target_id',
                                          name='uq_file_relation'),)

    file = db.relationship('File', back_populates='relation_links')


class SharedFolder(db.Model):
    """SMB shared folder shortcuts configuration."""
    __tablename__ = 'shared_folders'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    folder_path = db.Column(db.String(1000), nullable=False)
    sort_order = db.Column(db.Integer, default=0, index=True)
    is_active = db.Column(db.Integer, default=1, index=True)
    visible_roles = db.Column(db.String(200), default='all')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('shared_folders', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'folder_path': self.folder_path,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'visible_roles': self.visible_roles
        }


class SystemConfig(db.Model):
    """Key-value system configuration store."""
    __tablename__ = 'system_config'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    config_key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    config_value = db.Column(db.Text, default='')
    description = db.Column(db.String(500), default='')


class CloudAttachment(db.Model):
    """Nextcloud mirror/link for attachments owned by OA business records."""
    __tablename__ = 'cloud_attachments'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    target_type = db.Column(db.String(30), nullable=False, index=True)
    target_id = db.Column(db.Integer, nullable=False, index=True)
    original_name = db.Column(db.String(500), nullable=False)
    local_path = db.Column(db.String(1000), default='')
    cloud_path = db.Column(db.String(1000), default='')
    cloud_file_id = db.Column(db.String(100), default='', index=True)
    cloud_url = db.Column(db.String(1000), default='')
    sync_status = db.Column(db.String(20), default='pending', index=True)
    sync_error = db.Column(db.String(1000), default='')
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('bulletin_categories.id'), nullable=True, index=True)
    column_id = db.Column(db.Integer, db.ForeignKey('columns.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    synced_at = db.Column(db.DateTime)

    __table_args__ = (db.UniqueConstraint('target_type', 'target_id', 'local_path',
                                          name='uq_cloud_attachment_local'),)

    uploader = db.relationship('User', backref=db.backref('cloud_attachments', lazy='dynamic'))
    category = db.relationship('BulletinCategory', foreign_keys=[category_id])
    column = db.relationship('Column', foreign_keys=[column_id])


class BulletinCategory(db.Model):
    """Shared business category for tasks and bulletins."""
    __tablename__ = 'bulletin_categories'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    icon = db.Column(db.String(50), default='📁')
    color = db.Column(db.String(20), default='#10b981')
    tab_id = db.Column(db.Integer, db.ForeignKey('tabs.id', ondelete='SET NULL'), nullable=True)
    sort_order = db.Column(db.Integer, default=0, index=True)
    is_active = db.Column(db.Integer, default=1, index=True)
    visible_roles = db.Column(db.String(200), default='all')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('bulletin_categories', lazy='dynamic'))
    tab = db.relationship('Tab', backref=db.backref('bulletin_categories', lazy='dynamic'))
    column_items = db.relationship('Column', back_populates='category', lazy='dynamic',
                                 cascade='all, delete-orphan', passive_deletes=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'icon': self.icon,
            'color': self.color,
            'tab_id': self.tab_id,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
            'visible_roles': self.visible_roles,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }


class OnlineDocument(db.Model):
    """Online rich-text documents with permission control."""
    __tablename__ = 'online_documents'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, default='')
    doc_type = db.Column(db.String(20), default='rich')  # 'rich' or 'plain'
    status = db.Column(db.String(20), default='draft', index=True)  # draft, published, archived
    view_roles = db.Column(db.String(200), default='all')
    edit_roles = db.Column(db.String(200), default='["super_admin","dept_admin"]')
    is_active = db.Column(db.Integer, default=1, index=True)
    related_type = db.Column(db.String(50), default='', index=True)
    related_id = db.Column(db.Integer, default=0, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    editor_kind = db.Column(db.String(20), default='legacy_html', nullable=False, index=True)
    office_type = db.Column(db.String(10), default='')
    file_ext = db.Column(db.String(10), default='', index=True)
    original_filename = db.Column(db.String(500), default='')
    stored_filename = db.Column(db.String(100), default='')
    storage_relpath = db.Column(db.String(1000), default='')
    mime_type = db.Column(db.String(150), default='')
    file_size = db.Column(db.Integer, default=0)
    file_version = db.Column(db.Integer, default=1, nullable=False)
    document_key = db.Column(db.String(100), default='', index=True)
    checksum = db.Column(db.String(64), default='')
    last_editor_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    last_saved_at = db.Column(db.DateTime)

    creator = db.relationship('User', foreign_keys=[created_by], backref=db.backref('online_documents', lazy='dynamic'))
    last_editor = db.relationship('User', foreign_keys=[last_editor_id])

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content[:200] + '...' if self.content and len(self.content) > 200 else (self.content or ''),
            'doc_type': self.doc_type,
            'status': self.status,
            'view_roles': self.view_roles,
            'edit_roles': self.edit_roles,
            'related_type': self.related_type,
            'related_id': self.related_id,
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else ''
            , 'editor_kind': self.editor_kind or 'legacy_html', 'office_type': self.office_type,
            'file_ext': self.file_ext, 'file_size': self.file_size
        }


class Spreadsheet(db.Model):
    """Online spreadsheets with permission control (x-spreadsheet based)."""
    __tablename__ = 'spreadsheets'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(500), nullable=False)
    sheet_data = db.Column(db.Text, default='')  # JSON string of x-spreadsheet data
    status = db.Column(db.String(20), default='draft', index=True)
    view_roles = db.Column(db.String(200), default='all')
    edit_roles = db.Column(db.String(200), default='["super_admin","dept_admin"]')
    is_active = db.Column(db.Integer, default=1, index=True)
    related_type = db.Column(db.String(50), default='', index=True)
    related_id = db.Column(db.Integer, default=0, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('spreadsheets', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'view_roles': self.view_roles,
            'edit_roles': self.edit_roles,
            'related_type': self.related_type,
            'related_id': self.related_id,
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else ''
        }


# ==================== Model Validators ====================

class TaskValidator:
    """Task model validation helpers."""

    VALID_STATUSES = ['pending', 'processing', 'completed', 'rejected', 'archived', 'transferring']
    VALID_PRIORITIES = ['high', 'medium', 'normal', 'low']

    # Status transition rules
    STATUS_TRANSITIONS = {
        'pending': ['processing', 'transferring', 'rejected'],
        'processing': ['completed', 'transferring', 'rejected'],
        'transferring': ['processing'],
        'completed': ['archived'],
        'rejected': ['processing'],
    }

    @classmethod
    def validate_status(cls, status):
        """Check if status is valid."""
        return status in cls.VALID_STATUSES

    @classmethod
    def validate_priority(cls, priority):
        """Check if priority is valid."""
        return priority in cls.VALID_PRIORITIES

    @classmethod
    def can_transition(cls, from_status, to_status):
        """Check if status transition is valid."""
        allowed = cls.STATUS_TRANSITIONS.get(from_status, [])
        return to_status in allowed


class BulletinValidator:
    """Bulletin model validation helpers."""

    VALID_STATUSES = ['published', 'archived']

    @classmethod
    def validate_status(cls, status):
        """Check if status is valid."""
        return status in cls.VALID_STATUSES


class DocVersion(db.Model):
    """Version history for online documents."""
    __tablename__ = 'doc_versions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    doc_id = db.Column(db.Integer, db.ForeignKey('online_documents.id', ondelete='CASCADE'), nullable=False, index=True)
    content = db.Column(db.Text, default='')
    title = db.Column(db.String(500), default='')
    version_num = db.Column(db.Integer, nullable=False)
    change_summary = db.Column(db.String(500), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    storage_relpath = db.Column(db.String(1000), default='')
    file_size = db.Column(db.Integer, default=0)
    checksum = db.Column(db.String(64), default='')
    version_kind = db.Column(db.String(20), default='legacy_html', nullable=False, index=True)

    document = db.relationship('OnlineDocument', backref=db.backref('versions', lazy='dynamic', cascade='all, delete-orphan'))
    creator = db.relationship('User', backref=db.backref('doc_versions', lazy='dynamic'))


class SheetVersion(db.Model):
    """Version history for spreadsheets."""
    __tablename__ = 'sheet_versions'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sheet_id = db.Column(db.Integer, db.ForeignKey('spreadsheets.id', ondelete='CASCADE'), nullable=False, index=True)
    sheet_data = db.Column(db.Text, default='')
    name = db.Column(db.String(500), default='')
    version_num = db.Column(db.Integer, nullable=False)
    change_summary = db.Column(db.String(500), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    spreadsheet = db.relationship('Spreadsheet', backref=db.backref('versions', lazy='dynamic', cascade='all, delete-orphan'))
    creator = db.relationship('User', backref=db.backref('sheet_versions', lazy='dynamic'))


class MemoValidator:
    """Memo model validation helpers."""

    VALID_TYPES = ['private', 'public']

    @classmethod
    def validate_type(cls, memo_type):
        """Check if memo type is valid."""
        return memo_type in cls.VALID_TYPES


class TaskTransferValidator:
    """TaskTransfer model validation helpers."""

    VALID_STATUSES = ['pending', 'approved', 'rejected']

    @classmethod
    def validate_status(cls, status):
        """Check if status is valid."""
        return status in cls.VALID_STATUSES
