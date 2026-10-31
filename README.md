# 26creativity · 内网 OA 办公系统

面向内网办公场景的轻量 OA 系统，主项目位于 [`office_system/`](office_system/)。提供信息公示、任务流转、工作备忘、文件管理和在线文档等功能，采用 Flask + Jinja2 + LayUI + SQLite，主要部署目标为 **Windows 7 SP1 64 位**。

完整离线交付包内置便携 Python 和依赖，解压后双击 `office_system/start.bat` 即可启动；日常使用不需要访问互联网，也不需要安装数据库、Docker 或系统 Python。

> **源码与交付包不同。** GitHub 源码不能代替完整离线包。运行前请确认 `office_system/python/python.exe` 和配套依赖齐全；缺少运行时的源码副本不能直接双击启动。业务数据库、上传文件和部署凭据不应作为源码同步。

## 功能

| 模块 | 主要用途 |
| --- | --- |
| 公开门户与信息公示 | 按分类、栏目展示信息，支持富文本、附件、置顶、有效期及公示投票 |
| 工作台 | 汇总待处理任务、最新公示、备忘和快捷入口 |
| 任务管理 | 创建与分派任务，跟踪处理进度，申请交接并由管理员审批 |
| 工作备忘 | 管理个人备忘和按角色可见的公共备忘，支持归档 |
| 文件管理 | 上传、下载和预览常见文件，并关联任务、公示或备忘 |
| 在线文档与表格 | 编辑文字材料和表格，导入常用格式，导出及管理版本 |
| 通讯录与统计 | 查询联系人，查看办公数据概况 |
| 管理后台 | 管理用户、注册审核、栏目、可见范围、界面设置及操作日志 |

系统使用超级管理员、部门管理员、普通用户三级角色。具体操作及权限以页面和[用户使用手册](office_system/USER_GUIDE.md)为准。

## 快速启动

### 1. 准备完整运行目录

取得完整 Windows 离线交付包并解压。至少确认以下内容存在：

```text
office_system/
├── python/
│   ├── python.exe
│   └── Lib/site-packages/
├── app/
├── start.bat
├── run.py
└── health_check.py
```

目标机器应为 Windows 7 SP1 64 位或经验证兼容的 Windows 环境。Win7 若缺少系统运行库，按[离线部署指南](office_system/DEPLOY_WIN7.md)和 `install_win7_runtime.bat` 提示处理。

### 2. 启动并访问

双击 `office_system/start.bat`，脚本会先检查运行环境。首次运行自动创建数据库和初始账号，已有数据库则执行增量迁移。

- 本机访问：`http://127.0.0.1:5000`
- 局域网访问：`http://服务器局域网IP:5000`，以启动窗口显示的地址为准。
- 其他电脑无法访问时，检查服务器地址、防火墙与 TCP 5000 端口。

建议使用目标操作系统支持的 Chromium 内核浏览器。业务前端按 ES5 / IE11 兼容约束维护，但部分样式和第三方编辑器仍需在实际浏览器中验证。

### 3. 首次登录

下列账号仅在初始化新数据库时创建，初始密码均为 `admin123`：

| 账号 | 角色 |
| --- | --- |
| `admin` | 超级管理员 |
| `dept_admin` | 部门管理员 |
| `user` | 普通用户 |

部署后立即修改默认密码，并按实际需要管理初始化账号。已有数据库中的账号和密码以现有数据为准。

## 日常维护

以下命令均在 **`office_system/` 目录**执行，使用项目内便携 Python。

| 操作 | 命令 |
| --- | --- |
| 前台启动 | `start.bat` |
| 后台启动 | `start_hidden.bat` |
| 查看状态 | `status.bat` |
| 停止服务 | `stop.bat` |
| 登录 Windows 后自动启动 | `enable_autostart.bat` |
| 取消自动启动 | `disable_autostart.bat` |
| 环境自检 | `python\python.exe health_check.py` |
| 手动迁移数据库 | `python\python.exe migrate.py` |
| 备份数据库 | `python\python.exe backup.py backup` |
| 查看数据库备份 | `python\python.exe backup.py list` |
| 恢复指定备份 | `python\python.exe backup.py restore --file <备份文件名.db>` |

迁移或恢复前先停止服务并备份。`backup.py` 仅备份数据库；完整灾备还应单独保存 `data/` 中的上传文件、在线文档及版本文件，以及部署专用配置。不要通过删除数据库来解决升级问题。

常用位置：

- `data/database.db`：业务数据库。
- `data/uploads/`：上传文件。
- `data/backups/`：数据库备份。
- `logs/`：后台服务运行日志。
- `app/config.py`：应用配置，默认监听 `0.0.0.0:5000`。

详见[系统维护手册](office_system/MAINTENANCE.md)。

## 制作离线交付包

在具备完整便携运行时的开发机上执行：

```batch
cd office_system
python\python.exe make_release.py --target windows --fresh-data
```

当前打包脚本输出：

```text
release/
└── windows/
    ├── office_system/      # 可复制到目标机器的完整运行目录
    └── office_system.zip   # 压缩交付包
```

`--fresh-data` 排除当前业务数据、上传文件和用户头像，适合新环境交付。**省略该参数会包含当前数据**，仅在明确需要迁移现有业务环境时使用。打包读取当前工作目录，也会包含未提交但未被打包规则排除的文件；交付前检查内容。

`--target` 还支持 `kylin-arm64` 和 `all`，默认值为 `all`。麒麟包需要独立的 Linux ARM64 运行时，不能复用 Windows Python；详见[麒麟 ARM64 部署说明](office_system/KYLIN_ARM64_DEPLOY.md)。部分旧文档仍使用历史发布目录名，实际输出以当前 `make_release.py` 为准。

## 代码结构与技术约束

```text
26creativity/
├── README.md
├── AGENTS.md                    # 仓库开发约束
├── CLAUDE.md                    # 架构与实现说明
└── office_system/
    ├── app/
    │   ├── __init__.py          # Flask 应用工厂
    │   ├── models.py           # 数据模型
    │   ├── views/              # 业务蓝图和路由
    │   ├── templates/          # Jinja2 页面
    │   └── static/             # 内置前端库、样式和图标
    ├── python/                 # Windows 便携运行时（部署资源）
    ├── data/                   # 本地业务数据
    ├── run.py                  # 初始化、迁移和服务启动
    ├── migrate.py              # 兼容既有数据库的迁移
    ├── backup.py               # 数据库备份与恢复
    ├── make_release.py         # 离线打包
    └── requirements.txt        # 固定版本依赖清单
```

核心版本为 Python 3.8.10 64 位、Flask 2.0.1、Flask-SQLAlchemy 2.5.1、SQLAlchemy 1.4.25、LayUI 2.9.10、KindEditor 4.1.11，表格编辑使用内置 x-spreadsheet。完整依赖见 [`requirements.txt`](office_system/requirements.txt)。

开发时遵守以下约束：

- 沿用 Flask 服务端渲染和 iframe 多标签页结构，不引入 SPA 或前端构建链。
- 前端使用 ES5、LayUI 内置 jQuery 和兼容布局，不依赖 CDN、`fetch()`、Flexbox 或 Grid。
- 使用项目便携 Python，不随意升级运行时或现有依赖。
- 数据库变化兼容已有 SQLite 数据；重要业务修改沿用现有权限、可见性和审计机制。
- 不覆盖业务数据，不修改第三方库、历史发布包和废弃目录。

修改 Python 后可用便携 Python 对变更文件执行 `-m py_compile`；修改路由或模板后启动应用访问相关页面。完整规范见 [`AGENTS.md`](AGENTS.md)。

## GitHub 同步范围

源码同步应包含应用代码、模板、自有及离线内置静态资源、启动和维护脚本、依赖清单、必要配置示例与文档。

以下内容应留在本地或通过离线交付流程单独分发：

- 业务数据库及备份、上传附件、用户头像、在线文档与版本数据。
- 音频、视频文件，无论存放在数据目录还是其他目录。
- 日志、诊断输出、Python 缓存及临时构建目录。
- 便携运行时、安装包、wheel 缓存及 `release/` 发布产物。
- 含部署凭据的 `nextcloud_config.bat`、本地环境文件。

`.gitignore` 只阻止新增未跟踪文件，不能移除已经跟踪的文件或历史提交中的数据。推送前必须检查待推送提交；需要清理历史时另行安排，不直接强制推送覆盖远端。

## 扩展部署与文档

基础 OA 可独立离线运行。仓库也提供 ONLYOFFICE、Nextcloud 和麒麟相关扩展，它们需要额外部署相应的内网服务或运行时，不属于基础启动的前置条件。

| 文档 | 内容 |
| --- | --- |
| [用户使用手册](office_system/USER_GUIDE.md) | 登录、业务操作及常见问题 |
| [系统维护手册](office_system/MAINTENANCE.md) | 启停、运行库、数据与备份 |
| [Windows 7 部署](office_system/DEPLOY_WIN7.md) | 离线环境准备与故障排查 |
| [Windows 升级](office_system/WINDOWS_UPGRADE.md) | 现有 Windows 环境升级 |
| [麒麟 ARM64 部署](office_system/KYLIN_ARM64_DEPLOY.md) | Linux ARM64 环境要求 |
| [ONLYOFFICE 部署](office_system/ONLYOFFICE_DEPLOY.md) | 可选文档服务配置 |
| [Nextcloud 配置](office_system/NEXTCLOUD_WINDOWS_SETUP.md) | 可选文件服务配置 |
| [项目交接](office_system/HANDOVER.md) | 模块、结构与运维参考 |
