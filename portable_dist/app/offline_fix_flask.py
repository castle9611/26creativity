#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
离线 Windows 7 Flask 环境修复脚本
=================================
适用场景: 项目从有网机器拷贝到 离线 Win7 系统后 Flask 无法启动

核心问题:
  1. Python 版本不兼容 (Win7 只能跑 Python ≤ 3.8)
  2. zipimport 导致 _socket.pyd 等 C 扩展加载失败
  3. Flask/Werkzeug 版本与 Python 版本不匹配
  4. 离线无法 pip install

使用方法:
  [在线机器] python offline_fix_flask.py --download   → 下载兼容 wheels
  [Win7机器]  python offline_fix_flask.py --install    → 从本地 wheels 安装修复
  [Win7机器]  python offline_fix_flask.py --diagnose   → 仅诊断
"""

import os
import sys
import struct
import subprocess
import platform
import shutil
import json
import hashlib

# ── 颜色输出 (兼容 Win7 CMD) ─────────────────────────────
try:
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
except Exception:
    RESET = RED = GREEN = YELLOW = CYAN = BOLD = ""

PASS = f"{GREEN}✓{RESET}"
WARN = f"{YELLOW}⚠{RESET}"
FAIL = f"{RED}✗{RESET}"
INFO = f"{CYAN}→{RESET}"

# ── 配置 ─────────────────────────────────────────────────
WHEELS_DIR = "flask_wheels"
DEPOT_FILE = "wheels_manifest.json"

# ── 工具函数 ──────────────────────────────────────────────

def run(cmd, capture=True, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""
    except FileNotFoundError:
        return -1, "", f"找不到命令: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", "执行超时"
    except Exception as e:
        return -3, "", str(e)

def get_installed_version(pkg):
    """获取已安装包版本"""
    code = (
        f"try:\n"
        f"  import importlib.metadata as m\n"
        f"  print(m.version('{pkg}'))\n"
        f"except:\n"
        f"  try:\n"
        f"    import pkg_resources as p\n"
        f"    print(p.get_distribution('{pkg}').version)\n"
        f"  except:\n"
        f"    print('')\n"
    )
    rc, out, _ = run([sys.executable, "-c", code])
    return out.strip() if rc == 0 else None

def pip_offline_install(wheel_path):
    """从本地 wheel 文件离线安装"""
    cmd = [sys.executable, "-m", "pip", "install",
           "--no-index", "--find-links", os.path.dirname(wheel_path),
           os.path.basename(wheel_path)]
    rc, out, err = run(cmd, capture=True, timeout=60)
    return rc, out, err


# ═══════════════════════════════════════════════════════════
#  ██ 诊断模块
# ═══════════════════════════════════════════════════════════

def diagnose_python():
    """诊断 Python 版本和基础环境"""
    print(f"\n{BOLD}══════ Python 环境诊断 ══════{RESET}")

    py_ver = sys.version_info
    py_str = f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}"
    bitness = struct.calcsize("P") * 8

    print(f"  Python:     {sys.version}")
    print(f"  架构:       {bitness}位")
    print(f"  路径:       {sys.executable}")
    print(f"  prefix:     {sys.prefix}")

    issues = []

    # --- Win7 检测 ---
    win_ver = platform.platform(terse=True)
    is_win7 = "Windows-7" in platform.platform() or "Windows 7" in platform.version() or "6.1" in platform.version()
    print(f"  系统:       {platform.platform()}")

    if is_win7:
        print(f"  {WARN} Windows 7 检测到")
        # Python 3.9+ 不支持 Win7
        if py_ver.major >= 3 and py_ver.minor >= 9:
            print(f"  {FAIL} Python {py_str} 不支持 Windows 7！最高支持 Python 3.8")
            issues.append("python_too_new_for_win7")
        else:
            print(f"  {PASS} Python {py_str} 兼容 Windows 7")
    else:
        print(f"  {INFO} 非 Windows 7 系统 (不在此脚本的离线 Win7 修复范围)")

    # --- 虚拟环境检测 ---
    in_venv = (hasattr(sys, "real_prefix") or
               (sys.base_prefix != sys.prefix))
    if in_venv:
        print(f"  {INFO} 在虚拟环境中运行: {sys.prefix}")
    else:
        print(f"  {INFO} 系统 Python (非虚拟环境)")

    # --- 关键 C 扩展检测 ---
    print(f"\n  {BOLD}C 扩展模块检测:{RESET}")
    c_ext_ok = True
    for mod in ["_socket", "ssl", "ctypes", "hashlib", "_ssl"]:
        rc, _, _ = run([sys.executable, "-c", f"import {mod}"])
        if rc == 0:
            print(f"  {PASS} {mod}")
        else:
            print(f"  {FAIL} {mod} —— 加载失败！这是 zipimport 的典型症状")
            c_ext_ok = False
            issues.append(f"{mod}_failed")

    # --- sys.path zip 检测 ---
    print(f"\n  {BOLD}sys.path 中的 .zip 文件:{RESET}")
    zip_paths = [p for p in sys.path if p.endswith(".zip") and os.path.isfile(p)]
    if zip_paths:
        for zp in zip_paths:
            print(f"  {WARN} {zp}")
            # 检查 zip 中是否有 _socket 等 C 扩展
            import zipfile
            try:
                with zipfile.ZipFile(zp) as zf:
                    names = zf.namelist()
                    c_ext_in_zip = [n for n in names if n.startswith("_") and n.endswith(".pyd")]
                    if c_ext_in_zip:
                        print(f"  {FAIL}   → 包含 C 扩展文件！会导致加载失败: {c_ext_in_zip[:5]}")
                        issues.append("c_ext_in_zip")
                        c_ext_ok = False
                    py_lib_in_zip = [n for n in names if n.startswith("socket") or n.startswith("ssl")]
                    if py_lib_in_zip:
                        print(f"  {FAIL}   → 包含 socket/ssl 模块文件")
                        issues.append("stdlib_in_zip")
            except Exception as e:
                print(f"  {FAIL}   无法读取 zip: {e}")
    else:
        print(f"  {PASS} 无可疑 zip 路径")

    return issues

def diagnose_flask():
    """诊断 Flask 依赖"""
    print(f"\n{BOLD}══════ Flask 依赖诊断 ══════{RESET}")
    issues = []

    pkgs = {
        "Flask":       None,
        "Werkzeug":    None,
        "Jinja2":      None,
        "MarkupSafe":  None,
        "itsdangerous": None,
        "Click":       None,
    }

    for name in pkgs:
        ver = get_installed_version(name)
        pkgs[name] = ver
        if ver:
            print(f"  {PASS} {name} == {ver}")
        else:
            print(f"  {WARN} {name} 未安装")
            issues.append(f"{name.lower()}_not_installed")

    # ── 版本兼容性检查 ──
    flask_v = pkgs.get("Flask")
    werk_v = pkgs.get("Werkzeug")

    if flask_v and werk_v:
        try:
            # 简单数字比较
            def parse_ver(v):
                parts = v.replace("-", ".").replace("rc", ".").replace("b", ".").split(".")
                nums = []
                for p in parts:
                    try:
                        nums.append(int(p))
                    except ValueError:
                        break
                return tuple(nums + [0, 0, 0][:3 - len(nums)])[:3]

            fv = parse_ver(flask_v)
            wv = parse_ver(werk_v)

            fmajor, fminor = fv[0], fv[1]
            wmajor, wminor = wv[0], wv[1]

            # Flask 3.x → Werkzeug 3.x
            # Flask 2.x → Werkzeug 2.x
            if fmajor != wmajor:
                print(f"  {FAIL} 主版本不匹配: Flask {fmajor}.x  ↔  Werkzeug {wmajor}.x")
                issues.append("major_version_mismatch")
            else:
                # 细粒度检查
                if fmajor >= 3 and fminor >= 1 and wv < (3, 1, 0):
                    print(f"  {FAIL} Flask {flask_v} 需要 Werkzeug >= 3.1，当前 {werk_v}")
                    issues.append("werkzeug_too_old")
                elif fmajor == 2 and fminor >= 3 and wv < (2, 3, 3):
                    print(f"  {FAIL} Flask {flask_v} 需要 Werkzeug >= 2.3.3，当前 {werk_v}")
                    issues.append("werkzeug_too_old")
                else:
                    print(f"  {PASS} Flask {flask_v} ↔ Werkzeug {werk_v} 版本兼容")

            # Python 版本兼容性 (Win7 上的 Python 可能较旧)
            py_minor = sys.version_info.minor
            if fmajor >= 3:
                min_py = 8 if fminor >= 1 else 9  # Flask 3.0+ needs Python 3.8+; Flask 3.1+ needs Python 3.9+
                if py_minor < min_py:
                    print(f"  {FAIL} Flask {flask_v} 需要 Python 3.{min_py}+，当前 Python 3.{py_minor}")
                    issues.append("python_too_old_for_flask")
                else:
                    print(f"  {PASS} Python 版本满足 Flask 需求")

        except Exception as e:
            print(f"  {WARN} 版本检查异常: {e}")

    return issues, pkgs


def diagnose_app():
    """找到并尝试加载 Flask 应用"""
    print(f"\n{BOLD}══════ 应用入口检测 ══════{RESET}")

    app_file = None
    for candidate in ["app.py", "wsgi.py", "application.py", "run.py", "main.py", "manage.py"]:
        if os.path.isfile(candidate):
            app_file = candidate
            break

    if not app_file:
        # 尝试 .flaskenv 或环境变量
        if "FLASK_APP" in os.environ:
            app_file = os.environ["FLASK_APP"]
            print(f"  {INFO} FLASK_APP = {app_file}")
        else:
            print(f"  {WARN} 未找到常见的 Flask 入口文件")
            # 找 .py 文件看看有没有 Flask 相关
            py_files = [f for f in os.listdir(".") if f.endswith(".py")]
            app_candidates = []
            for f in py_files:
                try:
                    with open(f, "rb") as fh:
                        head = fh.read(4096)
                        if b"Flask" in head or b"flask" in head:
                            app_candidates.append(f)
                except:
                    pass
            if app_candidates:
                print(f"  {INFO} 可能的 Flask 文件: {', '.join(app_candidates[:5])}")
                if not app_file:
                    app_file = app_candidates[0]

    if app_file:
        print(f"  {PASS} 找到入口: {app_file}")
        print(f"  {INFO} 尝试语法检查 ...")
        rc, _, err = run([sys.executable, "-m", "py_compile", app_file])
        if rc == 0:
            print(f"  {PASS} 语法检查通过")
        else:
            print(f"  {FAIL} 语法错误: {err[:300]}")
    else:
        print(f"  {WARN} 未找到应用入口文件")

    return app_file


# ═══════════════════════════════════════════════════════════
#  ██ 修复模块
# ═══════════════════════════════════════════════════════════

def fix_zipimport_win7():
    """
    Win7 上修复 zipimport 导致 C 扩展加载失败的问题。

    核心思路: Python 的 pythonXX.zip 中包含 .pyd 文件时，
    zipimport 会尝试从 zip 中加载 C 扩展，但 _socket.pyd 等
    文件实际上是放在 DLLs/ 目录下的，zip 中的记录会干扰加载路径。
    """
    print(f"\n{BOLD}══════ 修复 zipimport / socket 加载问题 ══════{RESET}")
    fixes_applied = []

    # ── 方案1: 设置 PYTHON_IGNORE_IMPORT_FAILURE ──
    print(f"  {INFO} 方案1: 设置环境变量 PYTHON_IGNORE_IMPORT_FAILURE=1")
    os.environ["PYTHON_IGNORE_IMPORT_FAILURE"] = "1"
    # 验证
    rc, out, _ = run([sys.executable, "-c", "import os; print(os.environ.get('PYTHON_IGNORE_IMPORT_FAILURE', 'NOT_SET'))"])
    if "1" in out:
        print(f"  {PASS} 已设置")
        fixes_applied.append("env_PYTHON_IGNORE_IMPORT_FAILURE")
    else:
        print(f"  {FAIL} 设置失败")

    # ── 方案2: 移除 sys.path 中的 zip，写入 sitecustomize.py ──
    print(f"  {INFO} 方案2: 创建 sitecustomize.py 从 sys.path 移除 zip")
    site_packages = None
    for p in sys.path:
        if "site-packages" in p and os.path.isdir(p):
            site_packages = p
            break

    if site_packages:
        site_customize = os.path.join(site_packages, "sitecustomize.py")
        sc_content = r'''# -*- coding: utf-8 -*-
"""
sitecustomize.py — 自动修复 zipimport 导致的 C 扩展加载问题。
由 offline_fix_flask.py 生成。
"""
import sys

# 从 sys.path 中移除 .zip 文件，防止 zipimport 干扰 C 扩展加载
_zip_paths = [p for p in sys.path if p.endswith('.zip')]
for _zp in _zip_paths:
    if _zp in sys.path:
        sys.path.remove(_zp)

# 设置环境变量，忽略 zip 中 C 扩展的导入失败
import os
os.environ.setdefault('PYTHON_IGNORE_IMPORT_FAILURE', '1')

# 确保 DLLs 目录在路径中
import sysconfig
_dlls = sysconfig.get_config_var('DLLDIR')
if _dlls and os.path.isdir(_dlls) and _dlls not in sys.path:
    sys.path.insert(0, _dlls)

# 清理
del _zip_paths, _zp, _dlls
'''
        try:
            if os.path.isfile(site_customize):
                print(f"  {WARN} sitecustomize.py 已存在，备份为 sitecustomize.py.bak")
                shutil.copy2(site_customize, site_customize + ".bak")
            with open(site_customize, "w", encoding="utf-8") as f:
                f.write(sc_content)
            print(f"  {PASS} 已创建 {site_customize}")
            fixes_applied.append("sitecustomize_created")
        except Exception as e:
            print(f"  {FAIL} 写入失败: {e}")
    else:
        print(f"  {FAIL} 未找到 site-packages 目录")

    # ── 方案3: 创建启动包装器（.bat / .ps1）──
    print(f"  {INFO} 方案3: 创建 Flask 启动包装脚本")

    # 找 app 入口
    app_file = None
    for c in ["app.py", "wsgi.py", "run.py", "main.py", "application.py"]:
        if os.path.isfile(c):
            app_file = c
            break
    app_name = app_file or "app.py"

    # .bat 包装器
    bat_content = f"""@echo off
chcp 65001 >nul
REM ================================
REM Flask 离线启动脚本 (Win7 兼容)
REM ================================

REM 1. 绕过 zipimport C 扩展加载问题
set PYTHON_IGNORE_IMPORT_FAILURE=1

REM 2. Flask 配置
set FLASK_APP={app_name}
set FLASK_ENV=development
set FLASK_DEBUG=1

REM 3. 跳过 Python 版本检查钩子
set PYTHONWARNINGS=ignore

echo [INFO] 启动 Flask 应用: %FLASK_APP%
echo [INFO] 环境: %FLASK_ENV%

REM 4. 启动
python -W ignore -m flask run --host=127.0.0.1 --port=5000

REM 如果上面的失败，尝试直接运行
if errorlevel 1 (
    echo [WARN] flask run 失败，尝试直接执行...
    python -W ignore {app_name}
    if errorlevel 1 (
        echo [FAIL] 启动失败
        pause
    )
)
pause
"""
    with open("start_flask_win7.bat", "w", encoding="gbk", errors="replace") as f:
        f.write(bat_content)
    print(f"  {PASS} 已创建 start_flask_win7.bat")

    # PowerShell 包装器
    ps_content = f"""# Flask 离线启动脚本 (Win7 PowerShell)
$env:PYTHON_IGNORE_IMPORT_FAILURE = "1"
$env:FLASK_APP = "{app_name}"
$env:FLASK_ENV = "development"
$env:FLASK_DEBUG = "1"

Write-Host "[INFO] 启动 Flask 应用: $env:FLASK_APP" -ForegroundColor Cyan

python -W ignore -m flask run --host=127.0.0.1 --port=5000
if ($LASTEXITCODE -ne 0) {{
    Write-Host "[WARN] flask run 失败，尝试直接执行..." -ForegroundColor Yellow
    python -W ignore {app_name}
}}
"""
    with open("start_flask_win7.ps1", "w", encoding="utf-8") as f:
        f.write(ps_content)
    print(f"  {PASS} 已创建 start_flask_win7.ps1")

    # ── 验证修复 ──
    print(f"\n  {INFO} 验证修复效果 ...")
    rc, out, err = run([
        sys.executable, "-c",
        "import socket; s=socket.socket(); s.close(); print('socket OK')"
    ])
    if rc == 0 and "OK" in out:
        print(f"  {PASS} socket 模块加载正常")
    else:
        print(f"  {FAIL} socket 模块仍然异常: {err[:200]}")

    # 验证 Flask 可导入
    rc, out, err = run([
        sys.executable, "-c",
        "import flask; print(f'Flask {flask.__version__}')"
    ])
    if rc == 0:
        print(f"  {PASS} {out.strip()}")
    else:
        print(f"  {FAIL} Flask 导入失败: {err[:200]}")

    return fixes_applied


# ═══════════════════════════════════════════════════════════
#  ██ 离线下载模块 (在有网机器上运行)
# ═══════════════════════════════════════════════════════════

def generate_download_script(python_ver, flask_ver=None, werk_ver=None):
    """
    生成适用于 Win7 + 指定 Python 版本的兼容版本清单。

    Python 版本 → Flask/Werkzeug 兼容矩阵:
      Python 3.8 → Flask 2.3.x, Werkzeug 2.3.x
      Python 3.7 → Flask 2.2.x, Werkzeug 2.2.x
      Python 3.6 → Flask 2.0.x, Werkzeug 2.0.x
      Python 3.5 → Flask 1.1.x, Werkzeug 1.0.x
    """
    py_major = python_ver[0]
    py_minor = python_ver[1]

    # 根据 Python 版本选择明确的兼容版本
    if py_major < 3 or (py_major == 3 and py_minor < 5):
        return None, "Python 版本过旧 (3.5+ 是 Flask 最低要求)"

    # 定义明确的版本锁定
    # 目标是: 最新且稳定的组合，同时兼容离线环境
    if py_minor >= 8:
        # Python 3.8+ → Flask 2.3.x (2.3.3 最后一个支持 3.8 的版本)
        pkgs = {
            "Flask":       "2.3.3",
            "Werkzeug":    "2.3.7",
            "Jinja2":      "3.1.2",
            "MarkupSafe":  "2.1.3",
            "itsdangerous":"2.1.2",
            "Click":       "8.1.7",
            "importlib-metadata": "6.7.0",
            "zipp":        "3.15.0",
            "typing-extensions": "4.7.1",
        }
    elif py_minor == 7:
        # Python 3.7 → Flask 2.2.x
        pkgs = {
            "Flask":       "2.2.5",
            "Werkzeug":    "2.2.3",
            "Jinja2":      "3.1.2",
            "MarkupSafe":  "2.1.3",
            "itsdangerous":"2.1.2",
            "Click":       "8.1.7",
            "importlib-metadata": "6.7.0",
            "zipp":        "3.15.0",
            "typing-extensions": "4.7.1",
        }
    elif py_minor == 6:
        # Python 3.6 → Flask 2.0.x
        pkgs = {
            "Flask":       "2.0.3",
            "Werkzeug":    "2.0.3",
            "Jinja2":      "3.0.3",
            "MarkupSafe":  "2.0.1",
            "itsdangerous":"2.0.1",
            "Click":       "8.0.4",
            "importlib-metadata": "4.12.0",
            "zipp":        "3.8.1",
            "typing-extensions": "4.3.0",
        }
    else:
        # Python 3.5 → Flask 1.1.x
        pkgs = {
            "Flask":       "1.1.4",
            "Werkzeug":    "1.0.1",
            "Jinja2":      "2.11.3",
            "MarkupSafe":  "1.1.1",
            "itsdangerous":"1.1.0",
            "Click":       "7.1.2",
        }

    return pkgs, None


def do_download():
    """在有网络的机器上下载兼容的 wheels"""
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  离线 Wheel 下载工具 (请在能联网的机器上运行){RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    # 检测当前 Python 版本
    py_ver = (sys.version_info.major, sys.version_info.minor)
    print(f"\n  当前 Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print(f"  系统: {platform.platform()}")

    # 询问目标 Python 版本
    target_py_str = input(f"\n  目标 Win7 机器的 Python 版本 (如 3.8, 3.7, 3.6) [当前 {py_ver[0]}.{py_ver[1]}]: ").strip()
    if target_py_str:
        try:
            parts = target_py_str.split(".")
            target_py = (int(parts[0]), int(parts[1]))
        except:
            target_py = py_ver
    else:
        target_py = py_ver

    # 选择 Flask 版本
    print(f"\n  推荐的 Flask 版本 (基于 Python {target_py[0]}.{target_py[1]}):")
    if target_py[1] >= 8:
        print(f"    [1] Flask 2.3.3 + Werkzeug 2.3.7  (推荐，最稳定)")
        print(f"    [2] Flask 3.0.x + Werkzeug 3.0.x  (需要 Python ≥ 3.8)")
        print(f"    [3] 自定义版本")
    elif target_py[1] == 7:
        print(f"    [1] Flask 2.2.5 + Werkzeug 2.2.3  (推荐)")
        print(f"    [2] Flask 2.3.3 + Werkzeug 2.3.7  (可能不兼容 Python 3.7)")
        print(f"    [3] 自定义版本")
    else:
        print(f"    [1] Flask 2.0.3 + Werkzeug 2.0.3  (推荐)")
        print(f"    [2] Flask 1.1.4 + Werkzeug 1.0.1  (老项目)")
        print(f"    [3] 自定义版本")

    choice = input(f"  请选择 [1]: ").strip() or "1"

    pkgs, err = generate_download_script(target_py)
    if not pkgs:
        print(f"  {FAIL} {err}")
        return

    if choice == "2":
        if target_py[1] >= 8:
            pkgs["Flask"] = "3.0.3"
            pkgs["Werkzeug"] = "3.0.1"
        elif target_py[1] == 7:
            pkgs["Flask"] = "2.3.3"
            pkgs["Werkzeug"] = "2.3.7"
        else:
            pkgs["Flask"] = "1.1.4"
            pkgs["Werkzeug"] = "1.0.1"
    elif choice == "3":
        pkgs["Flask"] = input("  Flask 版本: ").strip() or pkgs["Flask"]
        pkgs["Werkzeug"] = input("  Werkzeug 版本: ").strip() or pkgs["Werkzeug"]

    # 创建下载目录
    os.makedirs(WHEELS_DIR, exist_ok=True)

    # 开始下载
    print(f"\n  {INFO} 开始下载 wheels 到 {WHEELS_DIR}/ ...")
    print(f"  {INFO} 目标组合: Flask {pkgs['Flask']} + Werkzeug {pkgs['Werkzeug']}\n")

    all_ok = True
    wheel_map = {}
    for name, ver in pkgs.items():
        spec = f"{name}=={ver}"
        print(f"  → 正在下载 {spec} ...", end=" ", flush=True)
        cmd = [sys.executable, "-m", "pip", "download",
               "--only-binary=:all:",
               "--dest", WHEELS_DIR,
               spec]
        # Win7 使用 pywin32 等特殊 wheel，可能需要 --platform
        # 如果目标 Python 架构不同，添加 --platform 参数
        rc, out, err = run(cmd, capture=True, timeout=120)
        if rc == 0:
            # 找到下载的文件
            downloaded = [f for f in os.listdir(WHEELS_DIR) if f.lower().startswith(name.lower()) and f.endswith(".whl")]
            if downloaded:
                print(f"{PASS} {downloaded[0]}")
                wheel_map[name] = downloaded[0]
            else:
                print(f"{WARN} 可能已存在或下载了源码包")
                wheel_map[name] = f"{name}-{ver}"
        else:
            print(f"{FAIL}")
            print(f"    {err[:200]}")
            # 尝试不带 --only-binary (有些包可能只有源码)
            print(f"    尝试下载源码包 ...", end=" ", flush=True)
            cmd2 = [sys.executable, "-m", "pip", "download",
                    "--no-binary", name,
                    "--dest", WHEELS_DIR, spec]
            rc2, out2, err2 = run(cmd2, capture=True, timeout=120)
            if rc2 == 0:
                print(f"{PASS}")
            else:
                print(f"{FAIL}")
                all_ok = False

    # 保存清单
    manifest = {
        "python_version": f"{target_py[0]}.{target_py[1]}",
        "python_arch": f"{struct.calcsize('P') * 8}bit",
        "system": "Windows 7",
        "packages": pkgs,
        "wheel_files": wheel_map,
        "fix_notes": [
            "1. 将 flask_wheels/ 目录整个拷贝到 Win7 机器项目目录下",
            "2. 在 Win7 上运行: python offline_fix_flask.py --install",
            "3. 或手动: pip install --no-index --find-links flask_wheels Flask==<版本>",
            "4. 使用 start_flask_win7.bat 启动 Flask"
        ]
    }

    with open(os.path.join(WHEELS_DIR, DEPOT_FILE), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 同时也复制一份到项目根目录
    shutil.copy2(os.path.join(WHEELS_DIR, DEPOT_FILE), DEPOT_FILE)

    print(f"\n  {'='*50}")
    if all_ok:
        print(f"  {PASS} 所有 wheels 下载完成!")
    else:
        print(f"  {WARN} 部分下载失败，请检查上面的错误")

    print(f"\n  下一步:")
    print(f"  1. 将 {WHEELS_DIR}/ 目录整体拷贝到 U 盘")
    print(f"  2. 在 Win7 机器上解压到项目目录")
    print(f"  3. 运行: python offline_fix_flask.py --install")
    print(f"  {'='*50}")


def do_install():
    """在离线 Win7 机器上从本地 wheels 安装"""
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  离线安装 Flask 兼容依赖 (Win7){RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    # 寻找 wheels 目录
    wheels_dir = None
    for d in [WHEELS_DIR, os.path.join("..", WHEELS_DIR), "wheels", "downloads"]:
        if os.path.isdir(d):
            wheels = [f for f in os.listdir(d) if f.endswith(".whl")]
            if wheels:
                wheels_dir = d
                break

    # 尝试读取 manifest
    manifest = {}
    for mp in [os.path.join(wheels_dir or "", DEPOT_FILE), DEPOT_FILE]:
        if os.path.isfile(mp):
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except:
                pass

    # 没有 manifest？从目录扫描
    if not manifest and wheels_dir:
        print(f"  {WARN} 未找到 manifest 文件，从目录扫描 wheels ...")
        wheel_list = [f for f in os.listdir(wheels_dir) if f.endswith(".whl")]
        print(f"  找到 {len(wheel_list)} 个 wheel 文件")

        pkgs = {}
        for wf in wheel_list:
            # 解析 wheel 文件名: package-version-*.whl
            parts = wf.split("-")
            if len(parts) >= 2:
                pkgs[parts[0]] = parts[1]

        manifest = {
            "wheel_files": {p: wf for p, wf in zip(pkgs.keys(), wheel_list)},
            "packages": pkgs,
            "wheel_dir": wheels_dir,
        }

    if not wheels_dir:
        print(f"  {FAIL} 未找到 wheels 目录!")
        print(f"  请先在能联网的机器上运行:")
        print(f"    python offline_fix_flask.py --download")
        print(f"  然后将 {WHEELS_DIR}/ 目录拷贝到本机")
        return

    # 确定安装顺序（依赖顺序）
    install_order = [
        "MarkupSafe", "Jinja2", "Click", "itsdangerous",
        "Werkzeug", "Flask",
        "importlib-metadata", "zipp", "typing-extensions",
    ]

    print(f"\n  找到 wheels 目录: {os.path.abspath(wheels_dir)}")
    print(f"  安装顺序: {' → '.join(install_order)}\n")

    success = True
    for pkg in install_order:
        if pkg in manifest.get("wheel_files", {}):
            wheel_file = manifest["wheel_files"][pkg]
        else:
            # 从目录中查找
            wheel_file = None
            for f in os.listdir(wheels_dir):
                if f.lower().startswith(pkg.lower()) and f.endswith(".whl"):
                    wheel_file = f
                    break

        if not wheel_file:
            # 可能是源码包 .tar.gz
            src_file = None
            for f in os.listdir(wheels_dir):
                if f.lower().startswith(pkg.lower()) and (f.endswith(".tar.gz") or f.endswith(".zip")):
                    src_file = f
                    break
            if src_file:
                print(f"  → 安装 {pkg} (源码: {src_file}) ...", end=" ", flush=True)
                cmd = [sys.executable, "-m", "pip", "install",
                       "--no-index", "--find-links", wheels_dir,
                       src_file]
                rc, out, err = run(cmd, capture=True, timeout=60)
                if rc == 0:
                    ver = get_installed_version(pkg)
                    print(f"{PASS} {ver}")
                else:
                    print(f"{FAIL}")
                    print(f"    {err[:200]}")
                    success = False
            else:
                print(f"  {WARN} {pkg} 未找到安装文件")
                success = False
            continue

        wheel_path = os.path.join(wheels_dir, wheel_file)
        print(f"  → 安装 {pkg} ({wheel_file}) ...", end=" ", flush=True)
        rc, out, err = pip_offline_install(wheel_path)
        if rc == 0:
            ver = get_installed_version(pkg)
            print(f"{PASS} {ver}")
        else:
            print(f"{FAIL}")
            print(f"    {err[:200]}")
            success = False

    # 额外安装项目自身依赖
    req_files = ["requirements.txt", "requirements_win7.txt"]
    for rf in req_files:
        if os.path.isfile(rf):
            print(f"\n  → 安装 {rf} 中的依赖 ...")
            cmd = [sys.executable, "-m", "pip", "install",
                   "--no-index", "--find-links", wheels_dir,
                   "-r", rf]
            rc, out, err = run(cmd, capture=True, timeout=60)
            if rc == 0:
                print(f"  {PASS} {rf} 依赖安装完成")
            else:
                print(f"  {FAIL} 部分失败: {err[:200]}")

    # 最终验证
    print(f"\n  {'='*50}")
    print(f"  {BOLD}最终验证{RESET}")
    print(f"  {'='*50}")

    for mod_name in ["flask", "werkzeug", "jinja2", "markupsafe", "click", "itsdangerous"]:
        rc, out, _ = run([
            sys.executable, "-c",
            f"import {mod_name}; v = getattr({mod_name}, '__version__', '?'); print(v)"
        ])
        if rc == 0:
            print(f"  {PASS} {mod_name} == {out.strip()}")
        else:
            print(f"  {FAIL} {mod_name} 导入失败")
            success = False

    # 启动脚本
    print(f"\n  创建启动脚本 ...")
    fix_zipimport_win7()

    print(f"\n  {'='*50}")
    if success:
        print(f"  {PASS}{BOLD} 安装完成！请使用 start_flask_win7.bat 启动应用{RESET}")
    else:
        print(f"  {WARN} 部分安装失败，请检查错误信息")
    print(f"  {'='*50}")


# ═══════════════════════════════════════════════════════════
#  ██ 入口
# ═══════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print(f"{BOLD}Flask 离线 Win7 环境修复工具{RESET}")
        print(f"\n用法:")
        print(f"  [在线机器]  python {sys.argv[0]} --download")
        print(f"  [Win7 机器] python {sys.argv[0]} --install")
        print(f"  [任意机器]  python {sys.argv[0]} --diagnose")
        print(f"\n使用场景:")
        print(f"  1. 在能联网的机器上运行 --download 下载兼容 wheels")
        print(f"  2. 将 flask_wheels/ 目录拷贝到离线 Win7 机器")
        print(f"  3. 在 Win7 上运行 --install 安装并修复环境")
        print(f"  4. 使用 start_flask_win7.bat 启动应用")
        return

    mode = sys.argv[1].lower()

    if mode in ("--download", "-d", "download"):
        do_download()

    elif mode in ("--install", "-i", "install"):
        # 先诊断
        py_issues = diagnose_python()
        flask_issues, pkgs = diagnose_flask()

        if py_issues:
            print(f"\n  {WARN} 发现 {len(py_issues)} 个 Python 环境问题:")
            for iss in py_issues:
                extra = ""
                if "socket" in iss or "zip" in iss:
                    extra = " (sitecustomize.py 会自动修复此问题)"
                print(f"    - {iss}{extra}")

        # 执行安装
        do_install()

        # 执行 zipimport 修复
        fix_zipimport_win7()

        # 最终提示
        print(f"\n{BOLD}建议:{RESET}")
        print(f"  1. 使用 start_flask_win7.bat 启动应用")
        print(f"  2. 如果仍然报错，检查 app.py 中是否依赖了其他不在清单中的包")
        print(f"  3. 尝试: python -c \"import flask; print(flask.__version__)\"")

    elif mode in ("--diagnose", "--check", "-c", "diagnose"):
        py_issues = diagnose_python()
        flask_issues, pkgs = diagnose_flask()
        app_file = diagnose_app()

        # 汇总
        all_issues = py_issues + flask_issues
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}  诊断汇总{RESET}")
        print(f"{BOLD}{'='*60}{RESET}")
        if all_issues:
            print(f"  {WARN} 发现 {len(all_issues)} 个问题:")
            for iss in all_issues:
                print(f"    - {iss}")
            print(f"\n  运行修复: python {sys.argv[0]} --install")
        else:
            print(f"  {PASS} 环境正常，未发现问题")

        if app_file:
            print(f"\n  尝试启动: python -W ignore -m flask run")

    else:
        print(f"  {FAIL} 未知参数: {mode}")
        print(f"  用法: --download | --install | --diagnose")


if __name__ == "__main__":
    main()
