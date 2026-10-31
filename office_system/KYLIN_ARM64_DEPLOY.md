# 银河麒麟 ARM64 部署说明

此目录只适用于 `aarch64/arm64` Linux。Windows 便携 Python 二进制不会打入该版本。

## 离线准备

1. 全量运行时包内置 Python 3.8.10 和依赖，服务器 Python 3.7 仅用于解包安装。
2. 在最终路径解压，确认存在 `runtime_packages/` 和 `wheels/`，详见 `KYLIN_DOCKER_CONTEXT.md`。
3. 执行 `sh start.sh`，首次自动将 Python 和依赖离线安装到 `python-linux/`，无需 Conda 或联网。
4. 浏览器访问 `http://服务器IP:5000`。

应用数据位于 `data/`。升级或迁移前请先使用 `backup.py` 备份数据库。

## 首页背景与本机不一致

首页配色保存在各部署环境自己的数据库中。本机选了“深蓝门户”，而麒麟环境使用新数据库或保留了“清爽浅色”设置时，中间区域背景会不同，与 CPU 架构无关。

使用超级管理员进入“UI 设置 → 首页配色方案”，选择“深蓝门户”并保存。新版在缺少配色配置时默认使用深蓝门户，但会保留已明确保存的浅色选择。首页背景由服务端设置，采用纯色兼容样式，不依赖浏览器本地主题记录。

更新应用后重启服务，并按 Ctrl+F5 刷新浏览器；无需删除或覆盖业务数据库。

注意：运行时为 Linux ARM64，已检查二进制依赖，仍需目标机验证。不要复制 Windows Python 或要求 GLIBC_2.29 的旧解释器。

## 视频兼容格式转换

预览失败的视频可转换为浏览器兼容性较好的 MP4（H.264 + AAC）：

```bash
./convert_video.sh /path/to/video.mov
./convert_video.sh /path/to/video-directory
```

转换结果写入源文件旁的 `converted/`，不会覆盖原文件。脚本优先使用
`tools/ffmpeg/ffmpeg`，也可使用系统 `PATH` 中的 FFmpeg。离线部署时放入的 FFmpeg
必须是与银河麒麟系统兼容的 ARM64 版本，并包含 `libx264` 和 AAC 编码器。
