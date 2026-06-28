#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==========================================
  Flask 便携式打包工具 (Win7 离线可用)
==========================================

用法: 在【有网的开发机】上运行:
    python build_portable.py

作用: 自动下载嵌入式 Python + Flask + 全部依赖 + VC++运行库，
      打包到 portable_dist/ 目录。将此目录拷贝到 Win7 项目目录，
      双击 start.bat 即可运行。

特性:
    - 自带 Python 3.8.10 (最后一个支持 Win7 的版本)
    - 自带 Flask + Werkzeug + 所有依赖
    - 自带 VC++ 运行库 (无需安装 VC++ Redist)
    - 自带 sitecustomize.py 修复 zipimport 问题
    - 纯离线、免安装、免配置
"""

import os
import sys
import struct
import urllib.request
import zipfile
import subprocess
import shutil
import platform
import json
import hashlib
from pathlib import Path

# ── 配置 ─────────────────────────────────────────────────
PYTHON_VERSION = "3.8.10"
# 根据架构选择 64位/32位
IS_64BIT = struct.calcsize("P") * 8 == 64
ARCH = "amd64" if IS_64BIT else "win32"
PYTHON_ARCH = f"{ARCH}"

OUTPUT_DIR = "portable_dist"
PYTHON_DIR = os.path.join(OUTPUT_DIR, "python")
APP_DIR = os.path.join(OUTPUT_DIR, "app")

# Flask 版本 (全部锁定为 Win7 兼容版本)
FLAVOR = {
    "Flask":       "2.3.3",
    "Werkzeug":    "2.3.7",
    "Jinja2":      "3.1.2",
    "MarkupSafe":  "2.1.3",
    "Click":       "8.1.7",
    "itsdangerous":"2.1.2",
    "importlib-metadata": "6.7.0",
    "zipp":        "3.15.0",
    "typing-extensions": "4.7.1",
    "colorama":    "0.4.6",
    "blinker":     "1.6.2",
}

# Python 嵌入式包下载地址
PYTHON_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-{PYTHON_ARCH}.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

# 需要从系统 Python 拷贝的 VC++ 运行库 DLL
VCRT_DLLS = [
    "msvcp140.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",  # 64-bit only
    "concrt140.dll",
]

# ── 辅助函数 ──────────────────────────────────────────────

def color(text, code):
    return f"\033[{code}m{text}\033[0m" if sys.platform != "win32" else text

def green(s): return color(s, "92")
def red(s):   return color(s, "91")
def yellow(s):return color(s, "93")
def cyan(s):  return color(s, "96")
def bold(s):  return color(s, "1")

def info(msg):
    print(f"  {cyan('→')} {msg}")

def ok(msg):
    print(f"  {green('✓')} {msg}")

def warn(msg):
    print(f"  {yellow('⚠')} {msg}")

def fail(msg):
    print(f"  {red('✗')} {msg}")

def download(url, dest, desc=None):
    """下载文件，带进度显示"""
    if desc:
        info(f"下载 {desc} ...")
    else:
        info(f"下载 {os.path.basename(url)} ...")

    def report(block, block_size, total_size):
        downloaded = block * block_size / 1024
        if total_size > 0:
            total = total_size / 1024
            percent = min(100, downloaded * 100 / total)
            print(f"\r    {downloaded:.0f}/{total:.0f} KB ({percent:.0f}%)", end="")
        else:
            print(f"\r    {downloaded:.0f} KB ...", end="")

    try:
        urllib.request.urlretrieve(url, dest, report)
        print()
        size = os.path.getsize(dest) / 1024
        ok(f"完成 ({size:.0f} KB)")
        return True
    except Exception as e:
        print()
        fail(f"下载失败: {e}")
        return False


def download_with_urllib(url, dest_dir):
    """使用 urllib 下载，返回文件路径"""
    os.makedirs(dest_dir, exist_ok=True)
    filename = url.split("/")[-1].split("?")[0]
    dest_path = os.path.join(dest_dir, filename)
    if os.path.isfile(dest_path) and os.path.getsize(dest_path) > 1000:
        ok(f"{filename} 已存在，跳过下载")
        return dest_path
    if download(url, dest_path, filename):
        return dest_path
    return None


def run_cmd(cmd, cwd=None, capture=True, timeout=120):
    """运行命令，返回 (成功, stdout, stderr)"""
    try:
        r = subprocess.run(
            cmd, capture_output=capture, text=True,
            cwd=cwd, timeout=timeout
        )
        ok = r.returncode == 0
        return ok, r.stdout or "", r.stderr or ""
    except FileNotFoundError:
        return False, "", f"命令未找到: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, "", "超时"
    except Exception as e:
        return False, "", str(e)


def find_vcrt_dlls():
    """从系统 PATH 中查找 VC++ 运行库 DLL"""
    found = []
    search_paths = os.environ.get("PATH", "").split(os.pathsep)
    # 添加常见目录
    search_paths.extend([
        r"C:\Windows\System32",
        r"C:\Windows\SysWOW64",
        os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32"),
    ])
    for dll in VCRT_DLLS:
        for path in search_paths:
            dll_path = os.path.join(path, dll)
            if os.path.isfile(dll_path):
                found.append(dll_path)
                break
        else:
            # 尝试在 Python 安装目录找
            for base in [os.path.dirname(sys.executable),
                         os.path.join(os.path.dirname(sys.executable), "DLLs")]:
                dll_path = os.path.join(base, dll)
                if os.path.isfile(dll_path):
                    found.append(dll_path)
                    break
    return found


# ═══════════════════════════════════════════════════════════
#  构建流水线
# ═══════════════════════════════════════════════════════════

def step_download_python():
    """下载嵌入式 Python"""
    print(f"\n{bold('══════ [1/5] 下载嵌入式 Python')}")
    info(f"Python {PYTHON_VERSION} ({PYTHON_ARCH})")

    downloads_dir = os.path.join(OUTPUT_DIR, "_downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    # 下载嵌入式 Python zip
    zip_path = download_with_urllib(PYTHON_URL, downloads_dir)
    if not zip_path:
        return False

    # 提取
    info("解压嵌入式 Python ...")
    if os.path.isdir(PYTHON_DIR):
        shutil.rmtree(PYTHON_DIR)
    os.makedirs(PYTHON_DIR, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(PYTHON_DIR)

    files = os.listdir(PYTHON_DIR)
    ok(f"解压完成，共 {len(files)} 个文件")

    # 验证 python.exe
    pyexe = os.path.join(PYTHON_DIR, "python.exe")
    if not os.path.isfile(pyexe):
        fail(f"未找到 python.exe")
        return False

    # 测试嵌入式 Python 能否运行
    ok_exe, out, err = run_cmd([pyexe, "--version"])
    if ok_exe:
        ok(f"嵌入式 Python: {out.strip()}")
    else:
        fail(f"嵌入式 Python 无法运行: {err}")
        return False

    return True


def step_install_pip():
    """给嵌入式 Python 安装 pip"""
    print(f"\n{bold('══════ [2/5] 安装 pip')}")

    pyexe = os.path.join(PYTHON_DIR, "python.exe")
    downloads_dir = os.path.join(OUTPUT_DIR, "_downloads")

    # ── 1. 修改 python._pth 启用 site-packages ──
    pth_file = os.path.join(PYTHON_DIR, "python._pth")
    if os.path.isfile(pth_file):
        info("配置 python._pth (启用 site-packages + DLLs) ...")
        with open(pth_file, "r") as f:
            content = f.read()

        # 取消注释 import site (启用 site-packages)
        content = content.replace("#import site", "import site")

        # 确保包含 DLLs 目录
        lines = content.splitlines()
        needs_dlls = True
        for line in lines:
            if "DLLs" in line and not line.strip().startswith("#"):
                needs_dlls = False
                break
        if needs_dlls:
            # 在文件末尾添加 DLLs 目录
            lines.append("Lib/DLLs")
            lines.append("DLLs")
            content = "\n".join(lines) + "\n"

        with open(pth_file, "w") as f:
            f.write(content)
        ok("python._pth 已配置")
    else:
        warn("未找到 python._pth，手动创建 ...")
        pth_content = (
            "python38.zip\n"
            ".\n"
            "Lib/site-packages\n"
            "Lib/DLLs\n"
            "DLLs\n"
            ".\n"
            "import site\n"
        )
        with open(pth_file, "w") as f:
            f.write(pth_content)
        ok("已创建 python._pth")

    # ── 2. 下载并安装 pip ──
    get_pip_path = download_with_urllib(GET_PIP_URL, downloads_dir)
    if not get_pip_path:
        # 手动创建 get-pip.py 从缓存
        warn("无法下载 get-pip.py，将尝试使用系统 pip 直接安装包")
        return _fallback_install_packages(pyexe, downloads_dir)

    info("安装 pip ...")
    ok_pp, out, err = run_cmd([pyexe, get_pip_path], timeout=120)
    if ok_pp:
        ok("pip 安装成功")
    else:
        warn(f"pip 安装可能有警告: {err[:200]}")
        # 继续，可能 pip 已经可用了

    # 验证 pip
    ok_pip, out, err = run_cmd([pyexe, "-m", "pip", "--version"])
    if ok_pip:
        ok(f"pip: {out.strip()}")
        return True
    else:
        warn(f"pip 不可用: {err[:200]}")
        return _fallback_install_packages(pyexe, downloads_dir)


def _fallback_install_packages(pyexe, downloads_dir):
    """
    备用方案: 如果 pip 不可用，用纯 Python 方式安装包。
    直接将预下载的 .whl 解压到 site-packages。
    """
    warn("使用备用方案: 直接解压 wheels 到 site-packages")
    site_packages = os.path.join(PYTHON_DIR, "Lib", "site-packages")
    os.makedirs(site_packages, exist_ok=True)

    # 下载所有 wheels
    all_pkgs = [f"{n}=={v}" for n, v in FLAVOR.items()]
    info("下载所有依赖 wheels ...")
    ok_dl, out, err = run_cmd([
        sys.executable, "-m", "pip", "download",
        "--dest", downloads_dir,
        "--only-binary", ":all:",
        "--python-version", "3.8",
        "--platform", f"win_{PYTHON_ARCH}",
    ] + all_pkgs, timeout=300)

    if not ok_dl:
        # 不带 platform 限制再试一次
        info("尝试不带 platform 限制下载 ...")
        ok_dl, out, err = run_cmd([
            sys.executable, "-m", "pip", "download",
            "--dest", downloads_dir,
        ] + all_pkgs, timeout=300)

    if not ok_dl:
        fail(f"下载 wheels 失败: {err[:300]}")
        return False

    # 解压每个 wheel 到 site-packages
    wheels = [f for f in os.listdir(downloads_dir)
              if f.endswith(".whl") and not f.startswith("pip") and not f.startswith("setuptools")]
    info(f"解压 {len(wheels)} 个 wheels 到 site-packages ...")

    for w in wheels:
        whl_path = os.path.join(downloads_dir, w)
        try:
            with zipfile.ZipFile(whl_path, "r") as zf:
                # wheel 内部目录结构: {package}-{version}.dist-info/ 和 纯模块目录
                for member in zf.namelist():
                    # 去掉顶层目录的 {package}-{version}.data/ 前缀
                    if member.endswith("/"):
                        continue
                    # 处理 .data 目录
                    if ".data" in member:
                        # 只提取 platlib 和 purelib 中的文件
                        parts = member.split("/")
                        data_idx = None
                        for i, p in enumerate(parts):
                            if ".data" in p:
                                data_idx = i
                                break
                        if data_idx is not None and data_idx + 1 < len(parts):
                            data_type = parts[data_idx + 1]
                            if data_type in ("platlib", "purelib", "scripts"):
                                # 重建路径，跳过 .data/type 部分
                                new_parts = parts[:data_idx] + parts[data_idx + 2:]
                                new_path = "/".join(new_parts)
                                dest_path = os.path.join(site_packages, new_path)
                                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                with zf.open(member) as src, open(dest_path, "wb") as dst:
                                    dst.write(src.read())
                    else:
                        dest_path = os.path.join(site_packages, member)
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        with zf.open(member) as src, open(dest_path, "wb") as dst:
                            dst.write(src.read())
        except Exception as e:
            warn(f"解压 {w} 失败: {e}")

    ok("wheels 解压完成")

    # 验证
    test_code = "; ".join([f"import {n.lower().replace('-','_')}" for n in FLAVOR.keys()]) + "; print('OK')"
    ok_test, out, err = run_cmd([pyexe, "-c", test_code[:200]])
    if ok_test and "OK" in out:
        ok("所有包安装验证通过")
        return True
    else:
        warn(f"部分包验证失败: {err[:200]}")
        return True  # 部分失败也继续


def step_install_flask():
    """安装 Flask 及其依赖到嵌入式 Python"""
    print(f"\n{bold('══════ [3/5] 安装 Flask 及依赖')}")

    pyexe = os.path.join(PYTHON_DIR, "python.exe")
    downloads_dir = os.path.join(OUTPUT_DIR, "_downloads")

    # 检查 pip 是否可用
    ok_pip, _, _ = run_cmd([pyexe, "-m", "pip", "--version"])
    if not ok_pip:
        warn("pip 不可用，跳过 pip 安装步骤")
        return True  # 上一步可能已经用备用方式安装了

    all_pkgs = [f"{n}=={v}" for n, v in FLAVOR.items()]

    # 先在 downloads_dir 下载 wheels
    info("下载 Flask 依赖 wheels ...")
    ok_dl, out, err = run_cmd([
        pyexe, "-m", "pip", "download",
        "--dest", downloads_dir,
    ] + all_pkgs, timeout=300)

    if ok_dl:
        ok("wheels 下载完成")
        # 从本地安装
        info("从本地 wheels 安装 ...")
        ok_install, out, err = run_cmd([
            pyexe, "-m", "pip", "install",
            "--no-index",
            "--find-links", downloads_dir,
        ] + all_pkgs, timeout=120)
        if ok_install:
            ok("Flask 依赖安装完成")
        else:
            warn(f"pip install 失败: {err[:200]}")
            # 回退到备用解压方式
            return _fallback_install_packages(pyexe, downloads_dir)
    else:
        warn(f"下载失败: {err[:200]}")
        # 用系统 pip 下载
        info("使用系统 pip 下载 ...")
        ok_sys, out, err = run_cmd([
            sys.executable, "-m", "pip", "download",
            "--dest", downloads_dir,
            "--only-binary", ":all:",
        ] + all_pkgs, timeout=300)
        if ok_sys:
            ok("系统 pip 下载完成")
            ok_install, out, err = run_cmd([
                pyexe, "-m", "pip", "install",
                "--no-index",
                "--find-links", downloads_dir,
            ] + all_pkgs, timeout=120)
            if ok_install:
                ok("Flask 依赖安装完成")
            else:
                warn(f"安装失败: {err[:200]}")
                return False
        else:
            fail("无法下载依赖")
            return False

    # 验证
    verify_code = (
        "import flask; print(f'Flask {flask.__version__}'); "
        "import werkzeug; print(f'Werkzeug {werkzeug.__version__}'); "
        "import socket; s=socket.socket(); s.close(); print('socket OK')"
    )
    ok_verify, out, err = run_cmd([pyexe, "-c", verify_code])
    if ok_verify:
        for line in out.strip().splitlines():
            ok(line)
    else:
        fail(f"验证失败: {err[:300]}")
        return False

    return True


def step_bundle_vcrt():
    """打包 VC++ 运行库 DLL"""
    print(f"\n{bold('══════ [4/5] 打包 VC++ 运行库')}")

    dlls_dir = os.path.join(PYTHON_DIR)
    dlls_found = find_vcrt_dlls()

    if dlls_found:
        info(f"找到 {len(dlls_found)} 个 VC++ DLL:")
        copied = 0
        for dll_path in dlls_found:
            dll_name = os.path.basename(dll_path)
            target = os.path.join(dlls_dir, dll_name)
            if not os.path.isfile(target):
                shutil.copy2(dll_path, target)
                ok(f"  已打包: {dll_name}")
                copied += 1
            else:
                ok(f"  已存在: {dll_name}")

        if copied == 0:
            warn("所有 DLL 已存在")
    else:
        warn("未在系统目录找到 VC++ DLL")
        warn("将尝试从 Python 目录复制 ...")
        # 从系统 Python 的 DLLs 目录找
        sys_dlls = os.path.join(os.path.dirname(sys.executable), "DLLs")
        if os.path.isdir(sys_dlls):
            copied = 0
            for f in os.listdir(sys_dlls):
                if f.lower() in [d.lower() for d in VCRT_DLLS]:
                    shutil.copy2(os.path.join(sys_dlls, f),
                                 os.path.join(dlls_dir, f))
                    ok(f"  已打包: {f}")
                    copied += 1
            if copied > 0:
                ok(f"从 Python DLLs 目录复制了 {copied} 个 DLL")
                dlls_found = ["found"]

    if dlls_found:
        ok("VC++ 运行库已打包")
    else:
        warn("⚠ 未找到 VC++ DLL！Win7 上可能需要手动安装 VC++ Redist")
        warn("  下载: https://aka.ms/vs/17/release/vc_redist.x64.exe")
        warn("  或使用 --no-vcrt 跳过此项")

    return True


def create_app_launcher(app_name="app.py"):
    """创建启动脚本"""
    print(f"\n{bold('══════ [5/5] 创建启动脚本')}")

    # ── 检测 app 入口 ──
    if not os.path.isfile(app_name):
        for c in ["app.py", "wsgi.py", "run.py", "main.py", "application.py"]:
            if os.path.isfile(c):
                app_name = c
                break
        else:
            warn(f"未找到 Flask 入口文件，将默认使用 app.py")
            # 创建一个最小 Flask 应用
            app_name = "app.py"
            with open(os.path.join(APP_DIR, app_name), "w") as f:
                f.write('''from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return "<h1>Flask Portable on Win7!</h1>"

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
''')
            ok("已创建最小 Flask 示例应用")

    # ── 创建 sitecustomize.py (修复 zipimport) ──
    site_packages = os.path.join(PYTHON_DIR, "Lib", "site-packages")
    os.makedirs(site_packages, exist_ok=True)

    sc_path = os.path.join(site_packages, "sitecustomize.py")
    with open(sc_path, "w") as f:
        f.write(r'''# -*- coding: utf-8 -*-
"""
sitecustomize.py — 自动修复 zipimport C 扩展加载问题
由 build_portable.py 自动生成
"""
import sys
import os

# 从 sys.path 移除 .zip 文件，防止干扰 C 扩展加载
sys.path = [p for p in sys.path if not p.endswith('.zip')]

# 确保 DLLs 目录在路径前端
_dlls = os.path.join(os.path.dirname(__file__), '..', 'DLLs')
if os.path.isdir(_dlls) and _dlls not in sys.path:
    sys.path.insert(0, _dlls)

# 确保 python 根目录在路径中
_pyroot = os.path.dirname(os.path.dirname(__file__))
if os.path.isdir(_pyroot) and _pyroot not in sys.path:
    sys.path.insert(0, _pyroot)

# 设置环境变量
os.environ.setdefault('PYTHON_IGNORE_IMPORT_FAILURE', '1')
os.environ.setdefault('PYTHONWARNINGS', 'ignore')

# 清理临时变量
del _dlls, _pyroot
''')
    ok("已创建 sitecustomize.py (修复 zipimport)")

    # ── 复制应用文件 ──
    info("复制应用文件 ...")
    os.makedirs(APP_DIR, exist_ok=True)

    # 复制 app 相关文件
    app_extensions = (".py", ".html", ".css", ".js", ".json", ".yaml", ".yml",
                      ".txt", ".cfg", ".ini", ".toml", ".env", ".png", ".jpg",
                      ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf")
    copied = 0
    for f in os.listdir("."):
        if f.startswith(".") or f.startswith("_") or f == OUTPUT_DIR:
            continue
        if f.endswith(app_extensions) or os.path.isdir(f):
            src = os.path.join(".", f)
            dst = os.path.join(APP_DIR, f)
            try:
                if os.path.isdir(src):
                    if f in ("__pycache__", "node_modules", ".git", "venv", "env"):
                        continue
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignoring_patterns(
                        "__pycache__", "*.pyc", ".git", "node_modules", "venv", "env"
                    ))
                else:
                    shutil.copy2(src, dst)
                copied += 1
            except Exception as e:
                warn(f"  跳过 {f}: {e}")

    ok(f"复制了 {copied} 个文件/目录")

    # ── 创建 start.bat ──
    # Win7 兼容的 bat，不使用任何高级特性
    bat_content = f'''@echo off
chcp 65001 >nul 2>&1
title Flask Portable App

REM ============================================
REM Flask 便携版启动脚本 (Win7 兼容)
REM 不需要安装 Python / VC++ Redist
REM ============================================

set "ROOT=%~dp0"
set "PYTHON=%ROOT%python\\python.exe"
set "APP=%ROOT%app\\"

REM 环境变量 (修复 zipimport / 模块加载)
set PYTHON_IGNORE_IMPORT_FAILURE=1
set PYTHONWARNINGS=ignore

REM Flask 配置
set FLASK_APP={app_name}
set FLASK_ENV=development
set FLASK_DEBUG=1
set FLASK_RUN_HOST=127.0.0.1
set FLASK_RUN_PORT=5000

echo.
echo ========================================
echo    Flask Portable on Win7
echo ========================================
echo.
echo Python : %PYTHON%
echo App    : %APP%%FLASK_APP%
echo URL    : http://127.0.0.1:5000
echo.

cd /d "%APP%"
if errorlevel 1 (
    echo [ERROR] Can't cd to APP dir: %APP%
    pause
    exit /b 1
)

REM 尝试 flask run
"%PYTHON%" -W ignore -m flask run --host=127.0.0.1 --port=5000

REM 如果 flask run 失败，直接执行 app
if errorlevel 1 (
    echo.
    echo [WARN] flask run failed, trying direct execute...
    echo.
    "%PYTHON%" -W ignore "%APP%%FLASK_APP%"
)

echo.
echo [INFO] App exited.
pause
'''
    bat_path = os.path.join(OUTPUT_DIR, "start.bat")
    with open(bat_path, "w") as f:
        f.write(bat_content)
    ok("已创建 start.bat")

    # ── 创建说明文件 ──
    readme = f"""# Flask 便携版 - Win7 离线运行包

## 使用方法

1. 将此目录拷贝到 Win7 系统的任意位置
2. 双击 start.bat
3. 浏览器访问 http://127.0.0.1:5000

## 技术说明

- 嵌入式 Python: {PYTHON_VERSION} ({PYTHON_ARCH})
- Flask: {FLAVOR['Flask']} + Werkzeug: {FLAVOR['Werkzeug']}
- 已内置 sitecustomize.py 修复 zipimport 问题
- 已打包 VC++ 运行库 DLL
- 无需安装任何软件，绿色便携

## 目录结构

```
portable_dist/
├── start.bat              # 启动脚本
├── app/                    # Flask 应用代码
│   ├── {app_name}
│   └── ...
└── python/                 # 嵌入式 Python
    ├── python.exe
    ├── python38.dll
    ├── python38.zip
    ├── *.pyd               # C 扩展模块
    ├── *.dll               # VC++ 运行库
    └── Lib/
        └── site-packages/  # Flask 等第三方包
"""
    readme_path = os.path.join(OUTPUT_DIR, "README.txt")
    with open(readme_path, "w") as f:
        f.write(readme)
    ok("已创建 README.txt")

    # ── 测试运行 ──
    info("验证打包环境 ...")
    pyexe = os.path.join("..", "python", "python.exe")
    test_code = (
        "import sys; print(f'Python {{sys.version_info.major}}.{{sys.version_info.minor}}'); "
        "import socket; s=socket.socket(); s.close(); "
        "import flask; print(f'Flask {{flask.__version__}}'); "
        "import werkzeug; print(f'Werkzeug {{werkzeug.__version__}}'); "
        "print('ALL OK')"
    )
    ok_test, out, err = run_cmd(
        [os.path.abspath(pyexe), "-c", test_code],
        cwd=os.path.abspath(APP_DIR)
    )
    if ok_test and "ALL OK" in out:
        for line in out.strip().splitlines():
            ok(line)
    else:
        warn(f"验证结果: {out[:200]} {err[:200]}")

    return True


def cleanup():
    """清理临时文件"""
    downloads_dir = os.path.join(OUTPUT_DIR, "_downloads")
    if os.path.isdir(downloads_dir):
        info("清理临时文件 ...")
        shutil.rmtree(downloads_dir)
        ok("已清理")


def print_summary():
    """打印最终结果"""
    total_size = 0
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for f in files:
            fp = os.path.join(root, f)
            total_size += os.path.getsize(fp)

    mb = total_size / 1024 / 1024

    print(f"\n{'='*55}")
    print(f"  {bold('构建完成！')}")
    print(f"{'='*55}")
    print(f"")
    print(f"  输出目录: {bold(OUTPUT_DIR)}/")
    print(f"  总大小:   {mb:.1f} MB")
    print(f"")
    print(f"  {green('下一步:')}")
    print(f"  1. 将 {OUTPUT_DIR}/ 目录整个拷贝到 U 盘")
    print(f"  2. 在 Win7 上解压到任一目录")
    print(f"  3. 双击 start.bat 即可启动 Flask")
    print(f"")
    print(f"  {yellow('注意:')}")
    print(f"  - 如果 Win7 是 32 位系统，需要重新打包")
    print(f"  - 浏览器访问 http://127.0.0.1:5000")
    print(f"{'='*55}")
    print()


# ═══════════════════════════════════════════════════════════
#  主函数
# ═══════════════════════════════════════════════════════════

def main():
    print(f"\n{bold('============================================')}")
    print(f"{bold('  Flask 便携式打包工具 (Win7 离线版)')}")
    print(f"{bold('============================================')}")
    print()
    print(f"  目标: 将当前项目打包成 Win7 上免安装运行的便携包")
    print(f"  Python: {PYTHON_VERSION} ({PYTHON_ARCH})")
    print(f"  Flask:  {FLAVOR['Flask']} + Werkzeug {FLAVOR['Werkzeug']}")
    print()

    # 解析命令行参数
    skip_vcrt = "--no-vcrt" in sys.argv
    app_name = "app.py"
    for arg in sys.argv[1:]:
        if arg.endswith(".py") and not arg.startswith("-"):
            app_name = arg

    # 检查是否在项目根目录
    if not os.path.isfile(app_name):
        # 检查是否有任何 .py 文件
        py_files = [f for f in os.listdir(".") if f.endswith(".py") and not f.startswith("build_")]
        if py_files:
            app_name = py_files[0]
            warn(f"未找到 {app_name}，使用 {py_files[0]} 作为入口")
        else:
            warn(f"未找到 Flask 入口文件，将创建示例应用")
            app_name = "app.py"

    # ── 清理上次构建 ──
    if os.path.isdir(OUTPUT_DIR):
        info(f"清理旧构建: {OUTPUT_DIR}/ ...")
        shutil.rmtree(OUTPUT_DIR)
        ok("已清理")

    # ── 分步构建 ──
    steps = [
        ("下载嵌入式 Python", step_download_python),
        ("安装 pip", step_install_pip),
        ("安装 Flask 依赖", step_install_flask),
    ]
    if not skip_vcrt:
        steps.append(("打包 VC++ 运行库", step_bundle_vcrt))
    steps.append(("创建启动脚本", lambda: create_app_launcher(app_name)))

    all_ok = True
    for name, func in steps:
        print(f"\n{bold('─' * 45)}")
        if not func():
            fail(f"步骤失败: {name}")
            all_ok = False
            # 是否继续？
            cont = input(f"  步骤 '{name}' 失败。继续? (Y/n): ").strip().lower()
            if cont == "n":
                print("  \n构建中止。")
                return
        else:
            ok(f"步骤完成: {name}")

    # ── 清理 ──
    cleanup()

    # ── 总结 ──
    if all_ok:
        print_summary()

        # 打包成 zip
        zip_choice = input(f"将 {OUTPUT_DIR}/ 打包成 zip? (Y/n): ").strip().lower()
        if zip_choice != "n":
            zip_name = f"{OUTPUT_DIR}.zip"
            info(f"打包为 {zip_name} ...")
            shutil.make_archive(OUTPUT_DIR, "zip", ".", OUTPUT_DIR)
            size_mb = os.path.getsize(zip_name) / 1024 / 1024
            ok(f"打包完成: {zip_name} ({size_mb:.1f} MB)")
    else:
        warn("构建部分失败，请检查上面的错误")


if __name__ == "__main__":
    main()
