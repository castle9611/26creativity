# 银河麒麟升级说明

本升级包只包含应用代码、页面、静态资源、迁移脚本和运行脚本，**不包含 `data/`、`app/static/uploads/`、`python/`、`logs/`、测试文件或 Windows 文件**。

1. 将压缩包解压到现有系统目录之外。
2. 执行 `chmod +x office_system/*.sh`。
3. 执行 `office_system/upgrade_kylin.sh /现有安装路径/office_system`。

升级脚本会依次停止服务、备份数据库、覆盖程序文件、运行兼容迁移并重新启动。现有数据库、上传文件、备份、日志和 Python 环境不会被覆盖。

如目标环境尚未安装新增依赖，请先把匹配银河麒麟 ARM64/Python 版本的 wheel 放入升级包的 `wheels/`，再在现有目录运行 `install_dependencies.sh`。
