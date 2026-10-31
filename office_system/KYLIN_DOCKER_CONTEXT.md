# 麒麟 V10 ARM64 全量离线包（含 Python 3.8.10）

目标为银河麒麟高级服务器 V10、aarch64/arm64、glibc 2.28。包含精确版本 **CPython 3.8.10**，不替换服务器的 Python 3.7。

## 首次安装

解压到最终目录，例如 `/opt/oa`，进入 `office_system/` 执行：

```sh
sh start.sh
```

安装脚本用系统 `python3`（支持 Python 3.7）运行 `setup_runtime.py`，校验并展开 `runtime_packages/` 到 `python-linux/`，修正安装路径，然后通过包内 Python 3.8.10 和 pip 离线安装 `wheels/` 的应用依赖。全程无需网络或 Conda。

`start.sh` 首次启动自动调用离线安装脚本，依赖校验全部通过后才记录安装完成并启动应用。之后启动直接使用包内解释器和依赖。也可提前手动执行 `sh install_dependencies.sh`。

启动入口只接受包内 `python-linux/bin/python3.8`，不回退到系统 Python，也不接受外部 `PYTHON_EXE` 替换应用解释器。脚本清理外部 Python 环境变量，以 `-I` 隔离模式禁用用户包和外部 Python 搜索路径。安装时禁用在线索引、用户安装和 pip 缓存，并检查依赖完整性；启动前检查解释器路径、精确版本、依赖版本和导入来源。环境缺失时停止并报告，不借用电脑上的第三方包。

系统 Python 3.7 需有标准库 `bz2`。安装需要当前目录写权限，建议使用较短、不含空格的路径。安装后不要移动目录；更换位置时，在新位置重新解压原包并安装。

```sh
./python-linux/bin/python3.8 --version
./python-linux/bin/python3.8 health_check.py
```

运行时来自 conda-forge 的 Python 3.8.10 ARM64 构建及配套库。来源与 SHA256 见 `runtime_packages/manifest.json`；安装时保留上游许可证到 `python-linux/licenses/`。

已提供 OpenSSL、SQLite、libffi、zlib、xz、ncurses、readline、Tk/X11 和 GCC 运行库等。系统仍需提供 Linux 内核、ARM64 动态加载器及 glibc 系统库（包括 `libcrypt.so.1`、`libnsl.so.1`）；不替换系统 glibc。二进制检查记录见 `runtime_packages/BINARY_CHECK.json`。

## 包含和排除

包含最新代码、模板、离线前端资源、维护脚本、Python 3.8.10 本体、运行库以及全部应用 wheel。不含业务数据库、附件、头像、备份、日志和缓存，不含 Windows 二进制。首次启动会创建新数据库；迁移业务时请保留或挂载原数据。

## 后续 Dockerfile

选择 ARM64、glibc 基础镜像，提供 Python 3.7+ 标准库作为解包工具（含 bz2）。不使用 Alpine/musl。复制应用到最终工作目录后，构建时执行 `sh install_dependencies.sh`。

前台入口为 `sh run_foreground.sh`，默认使用包内 `python-linux/bin/python3.8`。暴露 TCP 5000，持久化 `data/`、`app/static/uploads/`、`app/static/avatars/`。离线构建前需准备基础镜像，本包不含镜像层。

## 验证范围

已校验下载哈希、ARM64 ELF 架构、系统库依赖、GLIBC 符号、路径修正逻辑和数据排除规则。运行时最高 GLIBC 符号为 2.17。Windows 构建机无法执行 ARM64 Linux 程序，尚未在麒麟服务器或 ARM64 Docker 内验证启动；首次安装会执行版本、SSL、SQLite、压缩库和 pip 自检，失败即停止。

视频转码为可选功能，需另备 Linux ARM64 FFmpeg。普通上传、展播和文档预览不依赖 FFmpeg。
