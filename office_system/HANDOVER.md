# 监狱内网办公系统 — 项目交接文档

## 项目概述

为监狱系统开发的纯内网办公管理系统，适配 Windows 7 64位服务器，完全离线运行，绿色免安装。

- **启动方式**：双击 `start.bat`
- **访问地址**：`http://127.0.0.1:5000`
- **默认账号**：`admin` / `admin123`（超级管理员）

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 后端 | Python（便携版） | 3.8.10 64位 |
| 框架 | Flask | 2.0.1 |
| ORM | Flask-SQLAlchemy | 2.5.1 |
| 数据库 | SQLite3 | 单文件 `data/database.db` |
| 前端UI | LayUI | 2.9.10 |
| 富文本 | KindEditor | 4.1.11 |
| 表格 | x-spreadsheet | master |

## 离线部署说明

> 详见 `DEPLOY_WIN7.md` 完整部署指南

### 快速检查清单

部署前确认以下文件存在：

- [ ] `python/python.exe` - Python 解释器
- [ ] `python/python38.dll` - Python 运行时
- [ ] `python/Lib/site-packages/flask/` - Flask 框架
- [ ] `python/Lib/site-packages/sqlalchemy/` - SQLAlchemy ORM
- [ ] `start.bat` - 启动脚本
- [ ] `run.py` - 应用入口

### 首次部署步骤

1. 在开发机运行 `python\python.exe make_release.py`
2. 将生成的 `release\office_system_win7_offline` 或 zip 拷贝到 Win7 服务器
3. 在目标电脑双击 `start.bat`
4. 启动脚本会自动运行 `health_check.py` 自检并打开浏览器
5. 访问 `http://127.0.0.1:5000` 或启动窗口显示的局域网地址

### 常见问题

| 问题 | 解决方案 |
|------|----------|
| "不是有效的 Win32 应用程序" | 确认使用 **amd64** (64位) Python |
| "丢失 VCRUNTIME140.dll" | 安装 VC++ 2015-2022 运行时 |
| "python.exe 无法启动" | 安装 KB2999226 (Universal C Runtime) |

## 兼容性说明

| 特性 | 兼容性 | 说明 |
|------|--------|------|
| ES5 JavaScript | ✅ 完美 | 主代码使用 `var` + `function` |
| ES6 (`const`/`let`/`fetch`) | ⚠️ 部分 | 仅 2 个设置页面使用，已改用 ES5 |
| CSS 变量 (`--var`) | ⚠️ 现代浏览器 | IE11 不支持，建议使用 Chrome/Edge |
| CSS `rgb()/rgba()` | ✅ 完美 | 内部使用 rgb 颜色格式 |
| iframe 多标签页 | ✅ 完美 | 低内存占用，无需 SPA |
| SQLite | ✅ 完美 | 内嵌数据库，无需安装 |

**浏览器推荐**：Chrome、Edge、360安全浏览器（Chrome内核）

## 项目结构

```
office_system/
├── python/                  # 便携 Python 3.8.10 64位（含全部依赖）
├── app/
│   ├── __init__.py          # Flask 应用工厂
│   ├── config.py            # 全局配置（硬编码）
│   ├── extensions.py        # db = SQLAlchemy()
│   ├── models.py            # 12 个数据模型
│   ├── decorators.py        # 权限装饰器（三级角色）
│   ├── utils.py             # 日志、IP、分页工具
│   ├── database.py          # 建表 + 种子数据
│   ├── views/
│   │   ├── __init__.py      # 蓝图注册 + 首页路由
│   │   ├── auth.py          # 登录/登出/改密
│   │   ├── admin.py         # 用户/Tab/栏目/共享/日志/配置
│   │   ├── tasks.py         # 任务 CRUD + 流转审批
│   │   ├── bulletin.py      # 公示 Tab+栏目+内容
│   │   ├── memo.py          # 个人/公共备忘
│   │   └── files.py         # 文件上传/下载
│   ├── templates/           # 26 个 Jinja2 模板
│   └── static/
│       ├── layui/           # LayUI 2.9.10
│       ├── kindeditor/      # KindEditor 4.1.11
│       ├── x-spreadsheet/   # 在线表格
│       └── css/app.css      # 全局样式（~200行）
├── data/
│   ├── database.db          # SQLite 数据库（自动创建）
│   └── uploads/             # 上传文件（按月份分目录）
├── start.bat                # 一键启动脚本
├── run.py                   # Python 入口
├── backup.py                # 数据库备份/恢复
├── requirements.txt         # 依赖清单
├── USER_GUIDE.md            # 用户使用手册
├── MAINTENANCE.md           # 系统维护手册
└── Deprecated/              # 已废弃/临时开发资料，不进入发布包
```

当前根目录已按运行和维护用途整理：正式运行脚本、核心代码、数据目录和正式文档保留在根目录；旧检查脚本、wheel 缓存、临时诊断输出和旧分析报告已移入 `Deprecated/`。`make_release.py` 默认排除 `Deprecated/`、`logs/`、`diagnose_output/`。

## 数据库设计（12 张表）

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `users` | 用户账号 | username, password_hash, role, department, is_active |
| `login_logs` | 登录审计 | user_id, ip_address, login_time |
| `tabs` | 公示分类标签 | name, sort_order, is_pinned, visible_roles |
| `columns` | 公示栏目 | tab_id, name, sort_order, visible_roles |
| `bulletins` | 公示内容 | column_id, title, content, is_pinned, expire_date, status |
| `tasks` | 工作任务 | title, content, priority, assignee_id, deadline, status |
| `task_transfers` | 任务流转 | task_id, from_user_id, to_user_id, status, reviewed_by |
| `operation_logs` | 操作审计 | user_id, action, target_type, content, ip_address |
| `memos` | 工作备忘 | title, content, memo_type, visible_roles, is_archived |
| `files` | 文件管理 | filename, original_name, file_path, related_type |
| `shared_folders` | 共享文件夹 | name, folder_path, visible_roles |
| `system_config` | 系统配置 | config_key, config_value |

## 权限体系（三级角色）

| 角色 | 默认账号 | 权限范围 |
|------|---------|---------|
| **超级管理员** | admin / admin123 | 全部功能：用户管理、Tab/栏目配置、系统设置、所有数据 |
| **监区管理员** | dept_admin / admin123 | 本部门任务管理、公示发布管理、文件管理、审批流转、**Tab/栏目管理** |
| **普通民警** | user / admin123 | 查看公示、处理任务、个人备忘、文件上传下载 |

权限检查通过 `@login_required` + `@require_role('dept_admin')` 装饰器实现，超管自动拥有所有权限。

## 功能模块

### 1. 工作台（首页）
- 待处理任务数 / 我的备忘数 / 最新公示数
- 最新公示列表 + 快捷入口（创建任务、新建备忘、文件管理）
- 共享文件夹入口

### 2. 任务管理
- **创建**：标题、内容、优先级、部门、负责人、截止日期
- **状态流转**：待接收 → 处理中 → 已完成 / 待交接
- **交接审批**：负责人发起 → 监区管理员审批（通过/驳回）
- **筛选**：按状态、优先级、部门、负责人、关键词、日期范围
- **操作日志**：每步状态变更自动记录

### 3. 信息公示系统
- **三级结构**：Tab（标签）→ 栏目 → 内容
- **默认Tab**：监狱通知、监区动态、科室专栏、工作台账
- **Tab类型**：
  - `bulletin` - 顶层标签，显示为一个分组标题
  - `bulletin_child` - 子分类，属于某个顶层标签
  - `link` - 快捷入口，直接跳转链接
- **后台管理**：
  - 超级管理员和部门管理员均可管理 Tab 和栏目
  - 可新增/编辑/删除 Tab 和栏目
  - 支持设置可见角色（全部/管理员/仅超管）
- **侧边栏动态显示**：Tab 和栏目从数据库加载，自动按层级展示
- **置顶 + 有效期**：内容可置顶，过期自动隐藏
- **搜索**：按关键词、日期范围、栏目筛选

### 4. 工作备忘
- **个人备忘**：仅自己可见
- **公共备忘**：按角色设置可见范围
- 支持新建、编辑、归档、删除

### 5. 文件管理
- 上传/下载/删除
- 支持关联任务、公示或备忘
- 单文件限制 50MB，扩展名白名单
- 部门管理员只能看到本部门文件

### 6. 系统管理（仅超级管理员）
- **用户管理**：创建/编辑/启用禁用/删除
- **Tab标签管理**：排序/置顶/启用/可见角色
- **栏目管理**：每个Tab下创建栏目
- **共享文件夹**：配置SMB路径，file://协议打开
- **操作日志**：全量审计查询
- **系统配置**：参数设置

### 7. 帮助指南
- 角色权限说明
- 各模块操作指引

## 默认种子数据

首次启动自动创建：
- 3 个用户（admin / dept_admin / user）
- 4 个 Tab（监狱通知、监区动态、科室专栏、工作台账）
- 19 个栏目（各监区+科室）
- 19 条示例公示内容

如需重置数据，删除 `data/database.db` 后重启即可（首次启动自动创建全套数据）。日常启动会自动检测并运行 `migrate.py` 补全新字段/新表，**不会丢失现有数据**。也可手动运行 `python\python.exe migrate.py` 单独执行迁移。

## 部署说明

项目已经内置 Python 3.8.10 64 位和全部 Python 依赖。标准交付流程是运行 `make_release.py` 生成离线发布包，然后将发布包复制到目标电脑。

```batch
python\python.exe make_release.py
```

如需目标电脑首次启动时创建全新数据库：

```batch
python\python.exe make_release.py --fresh-data
```

**纯离线部署**：目标服务器无需安装 Python、pip、Flask 或数据库服务。

## 运维命令

```batch
# 启动
双击 start.bat

# 备份数据库
python\python.exe backup.py backup

# 恢复数据库
python\python.exe backup.py restore --file database_backup_20260101_120000.db

# 查看备份列表
python\python.exe backup.py list
```

## 关键设计决策

1. **iframe 多标签页**：每个功能页独立加载，页面间隔离，低内存占用
2. **服务端渲染**：Jinja2 模板，避免前端 SPA，兼容 IE11
3. **ES5 语法**：全部 JS 使用 var/function，无箭头函数/模板字符串/Promise
4. **SQLite WAL 模式**：提升并发性能
5. **CSS 集中管理**：`app.css` 统一全局样式，模板仅引用此文件
6. **操作日志**：所有增删改操作通过 `add_log()` 自动记录
7. **权限双重检查**：页面级（装饰器）+ 数据级（查询过滤）
8. **动态侧边栏**：Tab 和栏目通过 `app.before_request` 从数据库加载，支持实时修改

## 最近更新（2026-06-06）

### Tab 标签管理增强
- **权限下放**：部门管理员现可管理 Tab 和栏目（原来仅超级管理员可操作）
- **新增装饰器** `require_admin`：允许 super_admin 和 dept_admin 访问
- **Tab 类型扩展**：
  - `bulletin` - 顶层标签（分组标题）
  - `bulletin_child` - 子分类（属于顶层标签）
  - `link` - 快捷入口
- **侧边栏动态显示**：通过 `app.before_request` 和 `app.context_processor` 全局加载

### 相关文件
- `app/decorators.py` - 新增 `require_admin` 装饰器
- `app/views/__init__.py` - 添加 before_request 和 context_processor
- `app/views/admin.py` - Tab/栏目管理权限改为 require_admin
- `app/templates/base.html` - 动态显示 tabs
- `app/templates/admin/tabs.html` - 支持子分类类型
- `app/static/css/app.css` - 新增 `.nav-subsection` 样式

## 文件清单

| 类型 | 数量 | 说明 |
|------|------|------|
| Python 后端 | 11 个 | config, models, views×7, decorators, utils, database |
| HTML 模板 | 26 个 | base, login, index, help, profile, admin×6, tasks×4, bulletin×6, memo×2, files×1, errors×3 |
| 静态资源 | 3 个库 | LayUI, KindEditor, x-spreadsheet |
| 数据库表 | 12 张 | 见上方表结构 |
| API 路由 | 40+ 条 | 覆盖全部 CRUD 操作 |
