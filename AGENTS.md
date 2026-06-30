# AGENTS.md

本文件为本仓库内所有自动化编码代理的工作规范。作用域为仓库根目录及其所有子目录；若后续在子目录内出现更近的 `AGENTS.md`，以更近文件为准。

## 项目概览

这是一个纯离线内网 OA 办公系统，主项目位于 `office_system/`。目标部署环境是 Windows 7 SP1 64 位服务器，交付方式为绿色免安装包：解压后双击 `office_system/start.bat` 即可运行。

核心原则：

- 不依赖 Docker、外部网络服务、系统级 Python 或在线包管理。
- 不升级既有技术栈，除非用户明确要求并确认兼容性风险。
- 优先保持 Win7、低内存、内网离线和浏览器兼容性。
- 修改应贴合现有 Flask + Jinja2 + LayUI + SQLite 架构，不引入 SPA 或重型前端构建链。

## 目录结构

- `office_system/`：正式应用、运行脚本、维护脚本和业务数据。
- `office_system/app/`：Flask 应用代码、模板和静态资源。
- `office_system/app/views/`：蓝图路由模块。
- `office_system/app/templates/`：Jinja2 服务端模板。
- `office_system/app/static/`：LayUI、KindEditor、x-spreadsheet、全局 CSS 和图标资源。
- `office_system/data/`：SQLite 数据库、上传文件、备份数据。修改前注意保护用户数据。
- `office_system/python/`：便携 Python 3.8.10 和已安装依赖。不要随意改动或升级。
- `office_system/Deprecated/`、`_deprecated/`：废弃或历史资料，除非任务明确涉及，否则不要修改。
- `release/`：发布产物，通常不要手工编辑。

## 常用命令

所有应用命令默认从 `office_system/` 目录执行。

```batch
start.bat
python\python.exe run.py
python\python.exe migrate.py
python\python.exe health_check.py
python\python.exe backup.py backup
python\python.exe backup.py list
python\python.exe backup.py restore --file <filename.db>
python\python.exe make_release.py
python\python.exe make_release.py --fresh-data
stop.bat
status.bat
start_hidden.bat
```

代码级快速校验可使用：

```batch
python\python.exe -m py_compile run.py migrate.py app\__init__.py app\config.py app\database.py app\decorators.py app\models.py app\views\*.py
```

如需启动应用验证，优先使用项目内便携 Python，不要使用系统 Python。

## 技术栈约束

- Python 3.8.10 64 位便携版，路径为 `office_system/python/python.exe`。
- Flask 2.0.1、Flask-SQLAlchemy 2.5.1、SQLAlchemy 1.4.25。
- SQLite3 单文件数据库：`office_system/data/database.db`。
- 前端为服务端渲染 Jinja2 模板，不是 SPA。
- UI 使用 LayUI 2.9.10，富文本使用 KindEditor 4.1.11，在线表格使用 x-spreadsheet。
- 前端库均已离线内置，禁止为了常规功能引入 CDN 或在线依赖。

## 后端开发规范

- 使用现有 Flask app factory：`app/__init__.py:create_app()`。
- 新路由优先放入现有业务蓝图；新增蓝图必须在 `app/views/__init__.py` 中注册。
- 数据库模型集中在 `app/models.py`，共享 `app/extensions.py` 中的 `db`。
- 权限优先使用现有装饰器：`@login_required`、`@require_role(...)`、`@require_super_admin`、`@require_admin`。
- 操作审计使用 `app/utils.py:add_log()`，涉及增删改的重要业务操作应记录日志。
- 可见性控制使用 `app/utils.py:check_visible()`，不要复制粘贴新的角色解析逻辑。
- 查询列表必须分页，避免一次性加载大量记录。
- 文件上传沿用 `data/uploads/YYYY-MM/` + UUID 文件名模式，保留 `original_name` 用于显示。
- 数据库结构变化必须兼容已有 SQLite 数据库。优先扩展 `migrate.py` 或现有运行时补表逻辑，不要要求用户手动删库。
- 不要引入后台任务队列、定时器、外部数据库、缓存服务或需要额外安装的系统组件。

## 前端开发规范

- 保持 ES5 / IE11 兼容：使用 `var` 和 `function`。
- 禁止在业务模板中使用 `const`、`let`、箭头函数、模板字符串、`fetch()`、Promise、async/await。
- AJAX 使用 LayUI 内置 jQuery，即 `$.ajax()`。
- 布局不要依赖 CSS Grid 或 Flexbox；沿用现有 `float`、`display: table`、`inline-block`、`block` 和 `overflow` 等兼容写法。
- 页面仍以 iframe 多标签页方式组织，每个功能页保持可独立加载。
- 全局样式优先复用 `app/static/css/app.css`；模板内样式应保持小范围、页面级。
- UI 文案面向最终用户时使用中文；Python 代码中的注释、日志字符串、变量名和标识符使用英文。
- 图标优先使用 `app/static/icons.svg` 和 `_icon.html` partial，不要随意引入新的图标库。

## 数据与安全

- `office_system/data/database.db` 和 `office_system/data/uploads/` 是用户数据，修改或迁移前必须谨慎。
- 备份/恢复使用 `backup.py`，不要直接覆盖数据库，除非用户明确要求。
- 默认账号用于离线内网初始化，不要在普通改动中移除或改变其语义。
- `SECRET_KEY` 当前硬编码在配置中，这是该离线内网部署模式下的既有设计，不要因常规重构改成环境变量依赖。
- 不要向仓库加入真实敏感数据、外网地址、在线密钥或需要联网验证的逻辑。

## 修改边界

- 优先小范围修改与当前任务直接相关的文件。
- 不要重排大量代码、批量格式化、重命名公开字段或改动历史发布产物，除非任务需要。
- 不要修改 `office_system/python/`、第三方静态库、发布包或废弃目录，除非用户明确要求。
- 遇到已有未提交修改时，保留用户变更并在其基础上工作；不要回滚不属于自己的改动。
- Windows 批处理脚本中的路径应继续使用 `%~dp0` 和相对路径，保持可移动部署。

## 验证清单

根据改动范围选择最小但充分的验证：

- Python 代码改动：运行便携 Python 的 `py_compile`。
- 数据库/模型/迁移改动：运行 `python\python.exe migrate.py`，必要时再运行 `health_check.py`。
- 路由或模板改动：启动 `python\python.exe run.py` 后手动访问相关页面。
- 发布逻辑改动：运行 `python\python.exe make_release.py` 或至少检查排除规则。
- 前端兼容性改动：检查是否误用 ES6、Flexbox/Grid、外链资源或现代浏览器专属 API。

## 参考文档

- `CLAUDE.md`：当前最完整的项目架构和约束说明。
- `office_system/HANDOVER.md`：交接文档、模块说明和部署流程。
- `office_system/MAINTENANCE.md`：运维、备份、恢复和发布操作。
- `office_system/DEPLOY_WIN7.md`：Windows 7 离线部署细节。
- `office_system/USER_GUIDE.md`：面向用户的功能说明。
