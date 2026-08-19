# 银河麒麟 ARM64 部署说明

此目录只适用于 `aarch64/arm64` Linux。Windows 便携 Python 二进制不会打入该版本。

## 离线准备

1. 在一台与目标银河麒麟版本一致、可联网的 ARM64 机器上，准备 Python 3.8（建议使用系统同版本 Python）。
2. 把本文件 `requirements-kylin-arm64.txt` 的 ARM64 依赖 wheel 下载到 `wheels/`。
3. 将整个目录复制到离线服务器，执行 `chmod +x *.sh`，然后运行 `./install_dependencies.sh`。
4. 执行 `./start.sh`。浏览器访问 `http://服务器IP:5000`。

应用数据位于 `data/`。升级或迁移前请先使用 `backup.py` 备份数据库。

注意：ARM64 Python、wheel 与银河麒麟的 glibc/系统 ABI 必须匹配，因此不能在 Windows x64 构建机上安全生成通用原生运行时。

## 视频兼容格式转换

预览失败的视频可转换为浏览器兼容性较好的 MP4（H.264 + AAC）：

```bash
./convert_video.sh /path/to/video.mov
./convert_video.sh /path/to/video-directory
```

转换结果写入源文件旁的 `converted/`，不会覆盖原文件。脚本优先使用
`tools/ffmpeg/ffmpeg`，也可使用系统 `PATH` 中的 FFmpeg。离线部署时放入的 FFmpeg
必须是与银河麒麟系统兼容的 ARM64 版本，并包含 `libx264` 和 AAC 编码器。
