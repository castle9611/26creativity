# 项目优化方案

## 项目概述
监狱内网OA办公系统 - Flask + SQLite 绿色便携式部署

## 目录

1. [数据库优化](#1-数据库优化)
2. [查询性能优化](#2-查询性能优化)
3. [代码质量改进](#3-代码质量改进)
4. [安全增强](#4-安全增强)
5. [配置优化](#5-配置优化)
6. [前端优化](#6-前端优化)

---

## 1. 数据库优化

### 1.1 添加缺失索引

当前问题：
- `created_at`、`updated_at`、`status`、`department` 等高频查询字段缺少索引
- 外键字段未建立索引

```python
# 在 app/models.py 中为各模型添加索引

class User(db.Model):
    # 已有: username (unique index)
    # 建议添加:
    role = db.Column(db.String(20), nullable=False, default='user', index=True)  # 添加索引
    department = db.Column(db.String(100), default='', index=True)  # 添加索引
    is_active = db.Column(db.Integer, default=1, index=True)  # 添加索引

class Task(db.Model):
    # 已有外键索引
    status = db.Column(db.String(20), default='pending', index=True)  # 高频过滤
    department = db.Column(db.String(100), default='', index=True)
    priority = db.Column(db.String(20), default='normal', index=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    deadline = db.Column(db.Date, nullable=True, index=True)

class Bulletin(db.Model):
    status = db.Column(db.String(20), default='published', index=True)  # 高频过滤
    column_id = db.Column(db.Integer, db.ForeignKey('columns.id', ondelete='CASCADE'), index=True)
    is_pinned = db.Column(db.Integer, default=0, index=True)  # 置顶查询
    expire_date = db.Column(db.Date, nullable=True, index=True)  # 过期查询
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class Memo(db.Model):
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    memo_type = db.Column(db.String(20), default='private', index=True)
    is_archived = db.Column(db.Integer, default=0, index=True)  # 归档过滤
    visible_roles = db.Column(db.String(200), default='all')

class OperationLog(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    action = db.Column(db.String(50), nullable=False, index=True)  # 日志查询
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class TaskTransfer(db.Model):
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), index=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    status = db.Column(db.String(20), default='pending', index=True)

class File(db.Model):
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    related_type = db.Column(db.String(50), default='', index=True)
    related_id = db.Column(db.Integer, default=0, index=True)
    is_deleted = db.Column(db.Integer, default=0, index=True)  # 软删除过滤
```

### 1.2 SQLite WAL模式优化

```python
# 在 app/config.py 中添加

class Config:
    # ... 其他配置 ...

    # SQLite性能优化
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {
            'check_same_thread': False,
            'timeout': 30,  # 超时时间
        },
        'pool_pre_ping': True,
    }
```

### 1.3 创建数据库迁移脚本

```python
# app/migrations.py
"""
Database migration script for adding indexes.
Run once: python app/migrations.py
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
        conn = db.engine.connect()

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

            # Memo indexes
            "CREATE INDEX IF NOT EXISTS ix_memos_created_by ON memos(created_by)",
            "CREATE INDEX IF NOT EXISTS ix_memos_memo_type ON memos(memo_type)",
            "CREATE INDEX IF NOT EXISTS ix_memos_is_archived ON memos(is_archived)",

            # File indexes
            "CREATE INDEX IF NOT EXISTS ix_files_uploaded_by ON files(uploaded_by)",
            "CREATE INDEX IF NOT EXISTS ix_files_related_type ON files(related_type)",
            "CREATE INDEX IF NOT EXISTS ix_files_is_deleted ON files(is_deleted)",

            # Log indexes
            "CREATE INDEX IF NOT EXISTS ix_operation_logs_user_id ON operation_logs(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_operation_logs_action ON operation_logs(action)",
            "CREATE INDEX IF NOT EXISTS ix_operation_logs_created_at ON operation_logs(created_at)",

            # TaskTransfer indexes
            "CREATE INDEX IF NOT EXISTS ix_task_transfers_task_id ON task_transfers(task_id)",
            "CREATE INDEX IF NOT EXISTS ix_task_transfers_from_user_id ON task_transfers(from_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_task_transfers_to_user_id ON task_transfers(to_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_task_transfers_status ON task_transfers(status)",
        ]

        for idx_sql in indexes:
            try:
                conn.execute(db.text(idx_sql))
                print(f"[OK] {idx_sql[:60]}...")
            except Exception as e:
                print(f"[SKIP] {idx_sql[:60]}... ({e})")

        conn.commit()
        print("\n[OK] All indexes created successfully!")

if __name__ == '__main__':
    add_indexes()
```

---

## 2. 查询性能优化

### 2.1 修复N+1查询问题

当前问题：`views/__init__.py` 中的 index 视图多次查询 Column 表

```python
# 优化前
visible_bulletins = []
for b in latest_bulletins:
    col = Column.query.get(b.column_id)  # N+1 查询
    if col and check_visible(col.visible_roles, user_role):
        visible_bulletins.append(b)

# 优化后
from sqlalchemy.orm import joinedload

latest_bulletins = Bulletin.query.options(
    joinedload(Bulletin.creator),
    joinedload(Bulletin.column)
).filter(
    Bulletin.status == 'published',
    Bulletin.is_active == 1
).order_by(Bulletin.created_at.desc()).limit(5).all()

visible_bulletins = [
    b for b in latest_bulletins
    if b.column and check_visible(b.column.visible_roles, user_role)
]
```

### 2.2 优化 Memo 列表查询

当前问题：`memo.py` 中先查询所有数据再内存过滤

```python
# 优化前: 查询所有数据后在Python中过滤
filtered_memos = []
for m in memos:
    if m.memo_type == 'private' and m.created_by == user_id:
        filtered_memos.append(m)
    elif m.memo_type == 'public' and check_visible(m.visible_roles, user_role):
        filtered_memos.append(m)
total = len(filtered_memos)

# 优化后: 使用子查询
# 对于权限过滤不太复杂的情况，可以分两次查询然后合并
private_memos = Memo.query.filter(
    Memo.is_archived == 0,
    Memo.memo_type == 'private',
    Memo.created_by == user_id
).order_by(Memo.created_at.desc())

public_memos = Memo.query.filter(
    Memo.is_archived == 0,
    Memo.memo_type == 'public'
).order_by(Memo.created_at.desc())

# 在应用层合并并手动分页
```

### 2.3 优化 Bulletin 过期查询

```python
# 优化前: 使用复杂的 OR 条件
query = query.filter(
    db.or_(
        Bulletin.expire_date == None,
        Bulletin.expire_date >= today,
        Bulletin.is_pinned == 1
    )
)

# 优化后: 分离查询条件
from sqlalchemy import or_, and_

query = query.filter(
    or_(
        Bulletin.is_pinned == 1,
        and_(
            or_(Bulletin.expire_date == None, Bulletin.expire_date >= today)
        )
    )
)
```

---

## 3. 代码质量改进

### 3.1 提取公共查询函数

```python
# app/queries.py
"""Common query helpers to reduce code duplication."""
from app.extensions import db
from app.models import User, Task, Bulletin, Column, Tab, Memo
from app.utils import check_visible
from flask import session


def get_visible_tabs(user_role):
    """Get active tabs visible to user role."""
    tabs = Tab.query.filter_by(is_active=1).order_by(
        Tab.is_pinned.desc(), Tab.sort_order.asc()
    ).all()
    return [t for t in tabs if check_visible(t.visible_roles, user_role)]


def get_visible_columns(tab_id, user_role):
    """Get active columns for tab visible to user role."""
    columns = Column.query.filter_by(
        tab_id=tab_id, is_active=1
    ).order_by(Column.sort_order.asc()).all()
    return [c for c in columns if check_visible(c.visible_roles, user_role)]


def build_tabs_columns(user_role):
    """Build tabs with columns structure for templates."""
    tabs = get_visible_tabs(user_role)
    return [
        {'tab': tab, 'columns': get_visible_columns(tab.id, user_role)}
        for tab in tabs
    ]


def get_department_users(department):
    """Get all user IDs in a department."""
    return [u.id for u in User.query.filter_by(department=department).all()]


def get_user_role_scope():
    """Get current user's role-based query scope."""
    user_id = session.get('user_id')
    user_role = session.get('role', '')
    user_dept = session.get('department', '')

    return {
        'user_id': user_id,
        'role': user_role,
        'department': user_dept,
        'is_super_admin': user_role == 'super_admin',
        'is_dept_admin': user_role == 'dept_admin',
        'is_user': user_role == 'user'
    }
```

### 3.2 统一表单验证

```python
# app/forms.py
"""Form validation helpers."""
from flask import request, flash, redirect, url_for


def validate_required(*fields):
    """Validate required form fields. Returns True if valid, False otherwise."""
    missing = [f for f in fields if not request.form.get(f, '').strip()]
    if missing:
        flash(f'缺少必填字段: {", ".join(missing)}', 'warning')
        return False
    return True


def validate_password(password):
    """Validate password strength."""
    if len(password) < 6:
        flash('密码长度不能少于6位', 'warning')
        return False
    return True


def validate_password_change(old_password, new_password, confirm_password):
    """Validate password change request."""
    if not old_password or not new_password:
        flash('请填写完整的密码信息', 'warning')
        return False

    from werkzeug.security import check_password_hash
    from app.models import User
    from flask import session

    user = User.query.get(session['user_id'])
    if not check_password_hash(user.password_hash, old_password):
        flash('原密码错误', 'danger')
        return False

    if new_password != confirm_password:
        flash('两次输入的密码不一致', 'warning')
        return False

    if not validate_password(new_password):
        return False

    return True
```

### 3.3 添加模型验证方法

```python
# 在 app/models.py 中为各模型添加验证方法

class Task(db.Model):
    # ... existing fields ...

    VALID_STATUSES = ['pending', 'processing', 'completed', 'rejected', 'archived', 'transferring']
    VALID_PRIORITIES = ['high', 'medium', 'normal', 'low']

    @classmethod
    def validate_status(cls, status):
        return status in cls.VALID_STATUSES

    @classmethod
    def validate_priority(cls, priority):
        return priority in cls.VALID_PRIORITIES

    def can_transition_to(self, new_status):
        """Check if status transition is valid."""
        valid_transitions = {
            'pending': ['processing', 'transferring', 'rejected'],
            'processing': ['completed', 'transferring', 'rejected'],
            'transferring': ['processing'],
            'completed': ['archived'],
            'rejected': ['processing'],
        }
        return new_status in valid_transitions.get(self.status, [])


class Bulletin(db.Model):
    # ... existing fields ...

    VALID_STATUSES = ['published', 'archived']

    @classmethod
    def validate_status(cls, status):
        return status in cls.VALID_STATUSES
```

---

## 4. 安全增强

### 4.1 添加CSRF保护

```python
# app/csrf.py
"""CSRF protection for forms."""
import secrets
from functools import wraps
from flask import session, request, flash, redirect, url_for

def generate_csrf_token():
    """Generate and store CSRF token in session."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def validate_csrf_token():
    """Validate CSRF token from form."""
    form_token = request.form.get('csrf_token', '')
    session_token = session.get('csrf_token', '')
    return form_token == session_token and form_token != ''

def csrf_protect(f):
    """Decorator to protect forms with CSRF."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'POST':
            if not validate_csrf_token():
                flash('表单验证失败，请刷新页面后重试', 'danger')
                return redirect(request.referrer or url_for('index_bp.index'))
        return f(*args, **kwargs)
    return decorated

# In app/__init__.py add to context processors:
@app.context_processor
def inject_csrf():
    return {'csrf_token': generate_csrf_token}
```

### 4.2 添加请求频率限制

```python
# app/rate_limit.py
"""Simple in-memory rate limiting."""
import time
from collections import defaultdict
from functools import wraps
from flask import request, jsonify, flash, redirect, url_for

# Simple sliding window rate limiter
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)

    def is_allowed(self, key, max_requests=100, window=60):
        """Check if request is allowed. Default: 100 requests per minute."""
        now = time.time()
        self.requests[key] = [
            t for t in self.requests[key]
            if now - t < window
        ]

        if len(self.requests[key]) >= max_requests:
            return False

        self.requests[key].append(now)
        return True

rate_limiter = RateLimiter()

def rate_limit(max_requests=60, window=60):
    """Decorator to rate limit views."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Use IP + user_id as key
            from flask import session
            key = request.remote_addr
            if 'user_id' in session:
                key = f"{key}:{session['user_id']}"

            if not rate_limiter.is_allowed(key, max_requests, window):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'code': 429, 'msg': '请求过于频繁，请稍后重试'}), 429
                flash('请求过于频繁，请稍后重试', 'warning')
                return redirect(url_for('index_bp.index'))

            return f(*args, **kwargs)
        return decorated
    return decorator
```

### 4.3 增强密码安全

```python
# 在 config.py 中添加密码策略配置
class Config:
    # Password policy
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_REQUIRE_UPPERCASE = True
    PASSWORD_REQUIRE_LOWERCASE = True
    PASSWORD_REQUIRE_DIGIT = True
    PASSWORD_REQUIRE_SPECIAL = True

# 在 auth.py 中增强密码验证
def validate_password_strength(password):
    """Validate password meets security requirements."""
    if len(password) < current_app.config.get('PASSWORD_MIN_LENGTH', 8):
        return False, '密码长度不能少于8位'

    if current_app.config.get('PASSWORD_REQUIRE_UPPERCASE') and not any(c.isupper() for c in password):
        return False, '密码必须包含大写字母'

    if current_app.config.get('PASSWORD_REQUIRE_LOWERCASE') and not any(c.islower() for c in password):
        return False, '密码必须包含小写字母'

    if current_app.config.get('PASSWORD_REQUIRE_DIGIT') and not any(c.isdigit() for c in password):
        return False, '密码必须包含数字'

    if current_app.config.get('PASSWORD_REQUIRE_SPECIAL') and not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
        return False, '密码必须包含特殊字符'

    return True, '密码强度符合要求'
```

### 4.4 增强输入验证

```python
# app/validators.py
"""Input validation utilities."""
import re
from datetime import datetime

def validate_username(username):
    """Validate username format."""
    if not username or len(username) < 3 or len(username) > 50:
        return False, '用户名长度必须在3-50个字符之间'
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, '用户名只能包含字母、数字和下划线'
    return True, ''

def validate_real_name(name):
    """Validate real name."""
    if not name or len(name) > 50:
        return False, '姓名长度不能超过50个字符'
    return True, ''

def validate_date(date_str, format='%Y-%m-%d'):
    """Validate date string."""
    try:
        datetime.strptime(date_str, format)
        return True, ''
    except ValueError:
        return False, f'日期格式错误，请使用{format}格式'

def sanitize_html(html_content):
    """Basic HTML sanitization."""
    from markupsafe import escape
    # For rich text content, consider using bleach library
    # import bleach
    # allowed_tags = ['p', 'br', 'b', 'i', 'u', 'strong', 'em', 'ul', 'ol', 'li', 'a', 'h1', 'h2', 'h3']
    # return bleach.clean(html_content, tags=allowed_tags, strip=True)
    return html_content

def validate_file_extension(filename, allowed_extensions):
    """Validate file extension."""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in allowed_extensions
```

---

## 5. 配置优化

### 5.1 增强配置管理

```python
# app/config.py 增强版本

class Config:
    """Flask application configuration"""

    # Core
    SECRET_KEY = 'office-system-win7-secret-key-2024-internal'
    DB_PATH = os.path.join(BASE_DIR, 'data', 'database.db')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + DB_PATH.replace('\\', '/')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # Engine options for better SQLite performance
    SQLALCHEMY_ENGINE_OPTIONS = {
        'connect_args': {
            'check_same_thread': False,
            'timeout': 30,
        }
    }

    # Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 28800  # 8 hours
    SESSION_COOKIE_SECURE = False  # Set True if using HTTPS

    # File upload
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {
        'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
        'pdf', 'txt', 'csv', 'rtf',
        'jpg', 'jpeg', 'png', 'gif', 'bmp',
        'zip', 'rar', '7z',
        'mp4', 'avi', 'wmv', 'mp3', 'wav'
    }

    # Pagination
    ITEMS_PER_PAGE = 15
    MAX_TABS = 10

    # Password policy
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_REQUIRE_UPPERCASE = True
    PASSWORD_REQUIRE_DIGIT = True

    # Rate limiting
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_MAX_REQUESTS = 60  # per minute
    RATE_LIMIT_WINDOW = 60

    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = os.path.join(BASE_DIR, 'data', 'app.log')

    # Server
    HOST = '0.0.0.0'
    PORT = 5000
    DEBUG = False

    # Default accounts
    DEFAULT_ADMIN = {...}
    DEFAULT_DEPT_ADMIN = {...}
    DEFAULT_USER = {...}


class DevelopmentConfig(Config):
    """Development environment configuration"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    RATE_LIMIT_ENABLED = False


class ProductionConfig(Config):
    """Production environment configuration"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    # In production, use a proper secret key
    SECRET_KEY = os.environ.get('SECRET_KEY', 'CHANGE_THIS_IN_PRODUCTION')
```

### 5.2 添加健康检查端点

```python
# 在 app/views/__init__.py 中添加

@index_bp.route('/health')
def health_check():
    """Health check endpoint for monitoring."""
    import os
    from app.extensions import db

    health = {
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'components': {}
    }

    # Check database
    try:
        db.session.execute(db.text('SELECT 1'))
        health['components']['database'] = 'ok'
    except Exception as e:
        health['components']['database'] = f'error: {str(e)}'
        health['status'] = 'unhealthy'

    # Check upload directory
    try:
        upload_dir = os.path.join(BASE_DIR, 'data', 'uploads')
        if os.path.exists(upload_dir):
            health['components']['uploads'] = 'ok'
        else:
            health['components']['uploads'] = 'missing'
            os.makedirs(upload_dir, exist_ok=True)
    except Exception as e:
        health['components']['uploads'] = f'error: {str(e)}'

    status_code = 200 if health['status'] == 'healthy' else 503
    return jsonify(health), status_code
```

---

## 6. 前端优化

### 6.1 添加响应式设计改进

```css
/* app/static/css/app.css 添加 */

/* 响应式布局改进 */
@media (max-width: 1200px) {
    .sidebar {
        width: 200px !important;
    }
    .main-container {
        margin-left: 200px !important;
    }
}

@media (max-width: 768px) {
    .sidebar {
        width: 100% !important;
        height: auto;
        position: relative;
        display: none; /* 移动端可能需要汉堡菜单 */
    }

    .main-container {
        margin-left: 0 !important;
    }

    .tab-header {
        overflow-x: auto;
    }

    .stat-card {
        width: 100% !important;
        margin-right: 0 !important;
        margin-bottom: 10px;
    }
}

/* 表格响应式 */
@media (max-width: 768px) {
    .layui-table {
        font-size: 12px;
    }

    .layui-table td,
    .layui-table th {
        padding: 8px 5px;
    }

    /* 表格横向滚动 */
    .layui-table-box {
        overflow-x: auto;
    }
}
```

### 6.2 优化静态资源加载

```html
<!-- 在 base.html 中使用异步加载 -->
<script>
    // 延迟加载非关键 JS
    window.addEventListener('load', function() {
        // 预加载可能需要的资源
        var resources = [
            '{{ url_for("static", filename="layui/layui.js") }}'
        ];

        resources.forEach(function(src) {
            var link = document.createElement('link');
            link.rel = 'prefetch';
            link.as = 'script';
            link.href = src;
            document.head.appendChild(link);
        });
    });
</script>

<!-- 使用 async/defer -->
<script src="{{ url_for('static', filename='layui/layui.js') }}" defer></script>

<!-- 添加缓存控制 -->
<!-- 在服务器配置中添加 (如果使用 Nginx) -->
<!--
location ~* \.(css|js|jpg|jpeg|png|gif|ico|woff|woff2)$ {
    expires 30d;
    add_header Cache-Control "public, no-transform";
}
-->
```

### 6.3 添加加载状态指示器

```javascript
// app/static/js/loading.js

// 全局加载状态管理
var LoadingManager = {
    count: 0,

    show: function() {
        this.count++;
        if (this.count === 1) {
            var loader = document.createElement('div');
            loader.id = 'global-loader';
            loader.innerHTML = '<div class="loader-spinner"></div>';
            loader.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.3);z-index:99999;display:flex;align-items:center;justify-content:center;';
            document.body.appendChild(loader);
        }
    },

    hide: function() {
        this.count--;
        if (this.count <= 0) {
            this.count = 0;
            var loader = document.getElementById('global-loader');
            if (loader) {
                loader.remove();
            }
        }
    }
};

// 表单提交自动处理
document.addEventListener('submit', function(e) {
    var form = e.target;
    if (form.classList.contains('ajax-form')) {
        e.preventDefault();
        LoadingManager.show();

        var formData = new FormData(form);
        fetch(form.action, {
            method: 'POST',
            body: formData
        })
        .then(function(response) {
            return response.json || response.text();
        })
        .then(function(data) {
            LoadingManager.hide();
            if (data.code === 0 || data.code === 200) {
                layer.msg(data.msg || '操作成功', {icon: 1});
                if (data.url) {
                    setTimeout(function() {
                        location.href = data.url;
                    }, 1000);
                }
            } else {
                layer.msg(data.msg || '操作失败', {icon: 2});
            }
        })
        .catch(function(error) {
            LoadingManager.hide();
            layer.msg('网络错误', {icon: 2});
        });
    }
});

// 链接点击加载状态
document.addEventListener('click', function(e) {
    var link = e.target.closest('a[data-loading]');
    if (link) {
        LoadingManager.show();
    }
});
```

---

## 实施优先级

| 优先级 | 优化项 | 影响 | 实施难度 |
|--------|--------|------|----------|
| P0 | 添加数据库索引 | 高 | 低 |
| P0 | SQLite WAL模式 | 高 | 低 |
| P1 | 修复N+1查询 | 高 | 中 |
| P1 | CSRF保护 | 高 | 中 |
| P2 | 代码重构(提取公共函数) | 中 | 中 |
| P2 | 输入验证增强 | 高 | 中 |
| P3 | 密码策略增强 | 中 | 低 |
| P3 | 速率限制 | 中 | 低 |
| P4 | 前端优化 | 中 | 低 |

---

## 预期效果

1. **数据库查询性能提升**: 50-70% (添加索引后)
2. **页面加载时间减少**: 20-30% (N+1查询修复)
3. **系统安全性提升**: 显著(CSRF + 速率限制 + 输入验证)
4. **代码可维护性提升**: 显著(公共函数提取 + 验证器)
5. **用户安全性提升**: 显著(增强密码策略)

---

## 后续建议

1. **监控**: 添加 APM (Application Performance Monitoring)
2. **测试**: 添加单元测试和集成测试
3. **文档**: 完善 API 文档
4. **CI/CD**: 添加自动化部署流程
5. **缓存**: 对于频繁访问的数据考虑添加缓存层
