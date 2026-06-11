# 系统维护手册

## 1. 日常启动与停止

前台启动：

```batch
start.bat
```

后台启动：

```batch
start_hidden.bat
```

查看状态：

```batch
status.bat
```

停止服务：

```batch
stop.bat
```

## 2. 开机自启

启用当前用户登录后自动后台启动：

```batch
enable_autostart.bat
```

取消自启：

```batch
disable_autostart.bat
```

## 3. Win7 运行库

目标系统建议为 Windows 7 SP1 64 位。

如底层模块 `_socket`、`_ctypes`、`_sqlite3` 导入失败，请右键管理员运行：

```batch
install_win7_runtime.bat
```

安装后如提示重启，请先重启系统。

## 4. 数据和日志

- 数据库：`data/database.db`
- 上传文件：`data/uploads/`
- 后台运行日志：`logs/server.log`
- 后台错误日志：`logs/server-error.log`
- 上传文件会保留原始显示文件名和后缀；磁盘上的实际文件名使用 UUID，扩展名沿用原文件扩展名。
- 在线文档默认下载为 `.doc`，导出内容包含 Word/WPS 页面视图标记。
- 在线表格默认下载为 `.xls`，编辑页额外处理 WPS/Excel 复制出的制表符分隔内容，便于整块粘贴。
- 上传文件导入在线内容时使用 `app/importers.py`。DOCX/XLSX 通过标准库解析压缩 XML，CSV/TXT 通过编码兼容读取，不依赖 Office/WPS 或第三方库。

## 5. 备份与恢复

备份数据库：

```batch
python\python.exe backup.py backup
```

查看备份：

```batch
python\python.exe backup.py list
```

恢复数据库：

```batch
python\python.exe backup.py restore --file 备份文件名.db
```

## 6. 数据库迁移

日常启动会自动执行迁移检查。如需手动执行：

```batch
python\python.exe migrate.py
```

## 7. 生成离线发布包

包含当前数据库和上传文件：

```batch
python\python.exe make_release.py
```

生成全新数据包：

```batch
python\python.exe make_release.py --fresh-data
```

输出目录：

```text
..\release\office_system_win7_offline
..\release\office_system_win7_offline.zip
```

## 8. 目录维护约定

- 根目录只放运行入口、运维脚本、正式文档和核心目录。
- `app/` 存放业务代码、模板和静态资源。
- `python/` 存放便携 Python 和依赖，不要随意升级。
- `data/` 存放业务数据，迁移前务必备份。
- `runtime_install/` 存放 Win7 离线运行库安装器。
- `Deprecated/` 存放已废弃或临时开发资料，不进入发布包。

## 9. 故障排查

运行诊断：

```batch
diagnose.bat
```

若 5000 端口被占用，先运行：

```batch
stop.bat
```

若仍无法启动，查看：

```text
logs/server-error.log
```
