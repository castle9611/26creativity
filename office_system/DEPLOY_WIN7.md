# Windows 7 离线部署指南

本项目已经按“拷贝到其他电脑即可运行”的方式整理：内置 Python 3.8.10 64 位、Flask 依赖、SQLite、启动脚本和自检脚本。目标电脑不需要安装 Python，也不需要联网下载依赖。

## 推荐交付方式

在当前开发机进入 `office_system` 目录，运行：

```batch
python\python.exe make_release.py
```

生成结果：

```text
release\
├── office_system_win7_offline\      # 可直接复制到目标电脑
└── office_system_win7_offline.zip   # 可直接拷贝/解压到目标电脑
```

如果希望目标电脑首次启动时创建全新数据库，不带当前 `database.db` 和上传文件：

```batch
python\python.exe make_release.py --fresh-data
```

## 目标电脑部署步骤

1. 将 `office_system_win7_offline` 文件夹或 zip 拷贝到目标 Windows 7 64 位电脑。
2. 解压到任意英文或中文路径均可，例如 `D:\office_system_win7_offline`。
3. 双击 `start.bat`。
4. 浏览器访问 `http://127.0.0.1:5000`，局域网其他电脑访问启动窗口显示的 `LAN` 地址。

如果自检失败在 `_socket`、`socket`、`_ctypes`、`ctypes`、`_sqlite3`、`sqlite3` 等底层模块，请先在目标 Win7 上右键管理员运行：

```batch
install_win7_runtime.bat
```

安装完成后如提示重启，请先重启，再运行 `start.bat`。

默认账号：

```text
admin / admin123
```

## 一键脚本说明

| 文件 | 用途 |
| --- | --- |
| `start.bat` | 启动前自动自检、停止旧服务、创建数据目录、打开浏览器并启动系统 |
| `start_hidden.bat` | 后台启动服务，窗口会自动关闭，日志写入 `logs\` |
| `stop.bat` | 停止当前目录对应的服务，不再依赖本机固定路径 |
| `status.bat` | 查看 5000 端口是否正在监听 |
| `enable_autostart.bat` | 为当前 Windows 用户启用开机/登录后自动后台启动 |
| `disable_autostart.bat` | 取消开机/登录后自动启动 |
| `health_check.py` | 目标机离线自检，检查 Python、依赖、SQLite、写入权限和端口 |
| `make_release.py` | 在开发机生成干净的可迁移发布目录和 zip |
| `install_win7_runtime.bat` | 在目标 Win7 上离线安装 KB2999226 和 VC++ 2015 x64 运行库 |
| `diagnose.bat` | 低层运行库诊断脚本 |

## 目录结构

```text
office_system_win7_offline/
├── python/                 # 便携 Python 3.8.10 64 位，含依赖
├── app/                    # 应用代码、模板、静态资源
├── data/                   # SQLite 数据库和上传文件
├── start.bat               # 一键启动
├── stop.bat                # 停止服务
├── run.py                  # 应用入口，负责初始化/迁移数据库
├── health_check.py         # 离线自检
└── requirements.txt        # 锁定依赖清单
```

## 已内置依赖

```text
Python==3.8.10 amd64
Flask==2.0.1
Flask-SQLAlchemy==2.5.1
Werkzeug==2.0.1
Jinja2==3.0.1
SQLAlchemy==1.4.25
MarkupSafe==2.0.1
itsdangerous==2.0.1
click==8.0.1
SQLite3 内置
```

## 兼容性和系统补丁

目标系统建议为 Windows 7 SP1 64 位。

本包不再把 `ucrtbase.dll` / `api-ms-win-crt-*.dll` 放进 `python\` 目录，因为部分 Win7 会优先加载这些本地 DLL 并报 `DLL load failed: 参数错误`。目标 Win7 应使用系统级运行库。若底层模块导入失败，请运行 `install_win7_runtime.bat`。该脚本会离线安装：

- `Windows6.1-KB2999226-x64.msu`
- `vc_redist.x64.exe`

可能出现的问题：

| 问题 | 处理方式 |
| --- | --- |
| `python.exe 无法启动` | 安装 Windows 7 SP1 和 KB2999226 Universal C Runtime |
| `丢失 VCRUNTIME140.dll` | 确认 `python\` 目录完整，或安装 VC++ 2015-2022 x64 运行库 |
| `_socket` / `_ctypes` / `_sqlite3` 导入失败 | 右键管理员运行 `install_win7_runtime.bat`，重启后再试 |
| `不是有效的 Win32 应用程序` | 目标系统不是 64 位，需重新准备 32 位版本 |
| 浏览器打不开 | 先看启动窗口是否显示服务地址，再检查防火墙或 5000 端口占用 |

## 验证命令

在目标电脑上可手动运行：

```batch
python\python.exe health_check.py
```

全部显示 `[OK]` 后，再运行：

```batch
start.bat
```

## 后台运行和开机自启

后台启动：

```batch
start_hidden.bat
```

停止后台服务：

```batch
stop.bat
```

查看运行状态：

```batch
status.bat
```

启用当前用户登录后自动后台启动：

```batch
enable_autostart.bat
```

取消自动启动：

```batch
disable_autostart.bat
```

日志位置：

```text
logs\server.log
logs\server-error.log
```

## 数据说明

默认发布包会包含当前 `data/database.db` 和上传文件，适合把现有项目完整迁移到另一台电脑。

如果要部署一套新系统，请使用：

```batch
python\python.exe make_release.py --fresh-data
```

新系统首次启动会自动创建数据库、默认账号和基础数据。
