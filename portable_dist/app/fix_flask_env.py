#!/usr/bin/env python3
"""
Flask 环境修复脚本
自动诊断并修复：
1. Werkzeug/Flask 依赖版本不兼容
2. socket 模块 zipimport 加载异常
"""

import subprocess
import sys
import os
import shutil
import tempfile
import zipfile
import importlib
import pkg_resources
from packaging.version import Version, InvalidVersion

# ── 颜色输出 ──────────────────────────────────────────────
RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"

def ok(msg):
    print(f"  {GREEN}✓{RESET} {msg}")

def warn(msg):
    print(f"  {YELLOW}⚠{RESET} {msg}")

def fail(msg):
    print(f"  {RED}✗{RESET} {msg}")

def info(msg):
    print(f"  {CYAN}→{RESET} {msg}")

# ── 工具函数 ──────────────────────────────────────────────

def run(cmd, capture=False):
    """运行命令，返回 (returncode, stdout, stderr)"""
    try:
        r = subprocess.run(cmd, capture_output=capture, text=True, timeout=120)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", "Command timed out"

def pip_install(*pkgs, upgrade=False):
    """pip 安装包，自动加 --user 如果非 venv"""
    cmd = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        cmd.append("--upgrade")
    # 检测是否在 venv 中
    if not hasattr(sys, "real_prefix") and sys.base_prefix == sys.prefix:
        cmd.append("--user")
    cmd.extend(pkgs)
    rc, out, err = run(cmd, capture=True)
    return rc, out, err

def get_installed_version(pkg_name):
    """读取已安装包的版本"""
    try:
        return pkg_resources.get_distribution(pkg_name).version
    except pkg_resources.DistributionNotFound:
        return None

# ── 诊断阶段 ──────────────────────────────────────────────

def diagnose_socket():
    """诊断 socket 模块是否能正常加载"""
    print(f"\n{BOLD}1. 诊断 socket 模块加载{RESET}")
    issues = []

    # 1a. 基本 import
    info("检查 import socket ...")
    rc, out, err = run([sys.executable, "-c", "import socket; print(socket.__file__)"], capture=True)
    if rc != 0:
        fail(f"socket import 失败: {err}")
        issues.append("socket_import_failed")
    else:
        ok(f"socket 来自: {out.strip()}")
        # 检查是否是 zip
        sock_path = out.strip()
        if sock_path.endswith(".zip") or ".zip" in sock_path:
            fail("socket 模块来自 zip 文件，这是已知的 zipimport 问题来源")
            issues.append("socket_from_zip")
        else:
            ok("socket 模块来自正常文件路径")

    # 1b. 尝试实际创建 socket
    info("测试 socket.socket() 创建 ...")
    test_code = """
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.close()
    print("OK")
except Exception as e:
    print(f"FAIL: {e}")
"""
    rc, out, err = run([sys.executable, "-c", test_code], capture=True)
    if "OK" in out:
        ok("socket 创建成功")
    else:
        fail(f"socket 创建失败: {out.strip()}{err}")
        issues.append("socket_create_failed")

    # 1c. 检查 Python zip 路径问题
    info("检查 sys.path 中的 .zip 文件 ...")
    check_zips = [p for p in sys.path if p.endswith(".zip")]
    if check_zips:
        warn(f"发现 zip 路径 (可能影响 socket 等 C 扩展模块):")
        for zp in check_zips:
            warn(f"    {zp}")
            # 尝试修复: 检查 zip 中是否包含 socket 相关文件
            if os.path.isfile(zp):
                try:
                    with zipfile.ZipFile(zp) as zf:
                        socket_in_zip = [n for n in zf.namelist() if "socket" in n]
                        if socket_in_zip:
                            fail(f"    → 该 zip 包含 socket 相关文件: {socket_in_zip}")
                            issues.append("zip_contains_socket")
                except Exception:
                    pass
    else:
        ok("sys.path 中没有 .zip 文件")

    return issues


def diagnose_flask():
    """诊断 Flask 与 Werkzeug 版本兼容性"""
    print(f"\n{BOLD}2. 诊断 Flask / Werkzeug 版本兼容性{RESET}")
    issues = []

    flask_ver = get_installed_version("Flask")
    werkzeug_ver = get_installed_version("Werkzeug")

    if flask_ver:
        ok(f"Flask 已安装: {flask_ver}")
    else:
        warn("Flask 未安装，将安装最新兼容版本")
        issues.append("flask_not_installed")

    if werkzeug_ver:
        ok(f"Werkzeug 已安装: {werkzeug_ver}")
    else:
        warn("Werkzeug 未安装，将安装")
        issues.append("werkzeug_not_installed")

    if flask_ver and werkzeug_ver:
        # 版本兼容性矩阵（核心规则）
        try:
            fv = Version(flask_ver.split("+")[0].split(".dev")[0])
            wv = Version(werkzeug_ver.split("+")[0].split(".dev")[0])
        except InvalidVersion:
            warn(f"无法解析版本号，将重新安装兼容版本")
            issues.append("version_unparseable")
            return issues

        # Flask 2.x ↔ Werkzeug 2.x
        # Flask 3.x ↔ Werkzeug 3.x
        flask_major = fv.major
        werkzeug_major = wv.major

        # Flask 3.1+ 需要 Werkzeug >= 3.1
        # Flask 3.0 需要 Werkzeug >= 3.0, < 4
        # Flask 2.3 需要 Werkzeug >= 2.3.3, < 3
        # Flask 2.2 需要 Werkzeug >= 2.2.2, < 3

        if flask_major != werkzeug_major:
            fail(f"大版本不匹配: Flask {flask_major}.x ↔ Werkzeug {werkzeug_major}.x")
            issues.append("major_version_mismatch")
        elif flask_major == 3 and werkzeug_major == 3:
            # Flask 3.x 的详细兼容检查
            if fv >= Version("3.1") and wv < Version("3.1"):
                fail(f"Flask {fv} 需要 Werkzeug >= 3.1，当前 {wv}")
                issues.append("werkzeug_too_old")
            else:
                ok(f"Flask {fv} ↔ Werkzeug {wv} 版本兼容")
        elif flask_major == 2 and werkzeug_major == 2:
            if fv >= Version("2.3") and wv < Version("2.3.3"):
                fail(f"Flask {fv} 需要 Werkzeug >= 2.3.3，当前 {wv}")
                issues.append("werkzeug_too_old")
            else:
                ok(f"Flask {fv} ↔ Werkzeug {wv} 版本兼容")
        else:
            ok(f"Flask {fv} ↔ Werkzeug {wv} (未做深入检查)")

    # 尝试启动 Flask 应用（如果存在）
    app_file = None
    for candidate in ["app.py", "wsgi.py", "application.py", "manage.py", "run.py"]:
        if os.path.isfile(candidate):
            app_file = candidate
            break
    if app_file:
        info(f"尝试加载应用模块 {app_file} ...")
        rc, out, err = run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, '.'); exec(open('{app_file}').read())"],
            capture=True, timeout=10
        )
        if rc != 0:
            fail(f"应用加载失败: {err[:500]}")
            issues.append("app_load_failed")
        else:
            ok("应用模块加载成功")

    return issues


def diagnose_python():
    """诊断 Python 运行环境"""
    print(f"\n{BOLD}3. 诊断 Python 运行环境{RESET}")
    issues = []

    info(f"Python: {sys.version}")
    info(f"可执行路径: {sys.executable}")
    info(f"sys.prefix: {sys.prefix}")

    # 检查是否在 venv
    in_venv = hasattr(sys, "real_prefix") or sys.base_prefix != sys.prefix
    if in_venv:
        ok("在虚拟环境中运行")
    else:
        warn("在系统 Python 中运行 (将使用 --user 安装)")

    # 检查 pip
    rc, out, err = run([sys.executable, "-m", "pip", "--version"], capture=True)
    if rc == 0:
        ok(f"pip: {out.strip()}")
    else:
        fail(f"pip 不可用: {err}")
        issues.append("pip_unavailable")

    # 检查关键 C 扩展模块
    for mod in ["ctypes", "_socket", "ssl", "hashlib"]:
        rc, _, _ = run([sys.executable, "-c", f"import {mod}"], capture=True)
        if rc == 0:
            ok(f"{mod} 模块正常")
        else:
            fail(f"{mod} 模块加载失败")
            issues.append(f"{mod}_failed")

    return issues


# ── 修复阶段 ──────────────────────────────────────────────

def fix_zipimport_issue():
    """修复 zipimport 导致的 socket 加载问题"""
    print(f"\n{BOLD}修复 zipimport / socket 问题{RESET}")

    # 方案1: 设置环境变量
    info("方案1: 设置 PYTHON_IGNORE_IMPORT_FAILURE=1 ...")
    # 这个变量只影响部分场景，不太可靠

    # 方案2: 修复 .pth 文件和 zip 路径优先级
    info("方案2: 检查并清理可能导致 socket 问题的 zip 路径 ...")
    site_packages = None
    for p in sys.path:
        if "site-packages" in p and os.path.isdir(p):
            site_packages = p
            break

    if site_packages:
        ok(f"找到 site-packages: {site_packages}")
        # 检查 easy-install.pth 或类似文件中是否有 zip 引用
        pth_files = [f for f in os.listdir(site_packages) if f.endswith(".pth")]
        for pth in pth_files:
            pth_path = os.path.join(site_packages, pth)
            with open(pth_path) as f:
                content = f.read()
            zips_in_pth = [l.strip() for l in content.splitlines()
                           if l.strip().endswith(".zip")]
            if zips_in_pth:
                warn(f"在 {pth} 中发现 zip 引用: {zips_in_pth}")
                # 尝试修复：将 .pth 中的 zip 路径移到末尾
                # (通常 zip 中的同名模块会覆盖文件系统模块)
    else:
        warn("未找到 site-packages 目录")

    # 方案3: 最直接 — 确保 _socket.pyd 存在于 site-packages 或 DLLs 中
    info("方案3: 确保 _socket C 扩展可用 ...")
    python_dir = os.path.dirname(sys.executable)
    dlls_dir = os.path.join(python_dir, "DLLs")
    for check_dir in [dlls_dir, python_dir, site_packages] if site_packages else [dlls_dir, python_dir]:
        if check_dir and os.path.isdir(check_dir):
            socket_dlls = [f for f in os.listdir(check_dir) if "_socket" in f.lower()]
            if socket_dlls:
                ok(f"在 {check_dir} 中找到 _socket 扩展: {socket_dlls}")
                break
            else:
                warn(f"在 {check_dir} 中未找到 _socket 扩展")

    # 方案4: 重新安装 Python 的标准库 zip 中可能缺失的部分
    info("方案4: 检查 Python 标准库完整性 ...")
    test_mods = [
        "socket", "ctypes", "struct", "fcntl",
        "select", "selectors", "ssl", "hashlib"
    ]
    missing = []
    for mod in test_mods:
        rc, _, _ = run([sys.executable, "-c", f"import {mod}"], capture=True)
        if rc != 0:
            missing.append(mod)
    if missing:
        fail(f"以下标准库模块无法导入: {', '.join(missing)}")
        info("建议: 重新安装 Python 或使用 --no-zipimport 重新编译")
        info("临时绕过: 尝试使用 PYTHON_IGNORE_IMPORT_FAILURE=1")
        return False
    else:
        ok("所有关键标准库模块均可导入")
        return True


def fix_flask_deps(target_flask_version=None):
    """安装兼容的 Flask 和 Werkzeug 版本"""
    print(f"\n{BOLD}修复 Flask / Werkzeug 依赖{RESET}")

    flask_ver = get_installed_version("Flask")
    werkzeug_ver = get_installed_version("Werkzeug")

    # 确定目标版本
    if target_flask_version:
        flask_target = target_flask_version
    elif flask_ver:
        flask_target = flask_ver
    else:
        flask_target = "3.1.1"  # 最新的稳定 Flask

    try:
        fv = Version(flask_target.split("+")[0].split(".dev")[0])
    except InvalidVersion:
        warn(f"无法解析 Flask 版本 {flask_target}，使用最新版")
        fv = Version("3.1.1")

    # 根据 Flask 版本确定 Werkzeug 兼容版本
    flask_major = fv.major
    flask_minor = fv.minor

    # Flask 3.1+ → Werkzeug 3.1+
    # Flask 3.0 → Werkzeug 3.0 (but < 4)
    # Flask 2.3 → Werkzeug 2.3.3+ (but < 3)
    # Flask 2.2 → Werkzeug 2.2.2+ (but < 3)

    if flask_major >= 3:
        if flask_minor >= 1:
            werkzeug_spec = ">=3.1,<4"
        else:
            werkzeug_spec = ">=3.0,<4"
    elif flask_major >= 2:
        if flask_minor >= 3:
            werkzeug_spec = ">=2.3.3,<3"
        else:
            werkzeug_spec = ">=2.2.2,<3"
    else:
        # Flask 1.x — 太老了
        werkzeug_spec = ">=0.15,<2"

    # 还需要其他兼容依赖
    deps = {
        "flask": f"Flask=={flask_target}" if not flask_target.startswith((">=", "==", ">", "<")) else flask_target,
        "werkzeug": f"Werkzeug{werkzeug_spec}",
        "jinja2": "Jinja2>=3.0",
        "markupsafe": "MarkupSafe>=2.0",
        "click": "Click>=8.0",
        "itsdangerous": "itsdangerous>=2.0",
    }

    info(f"目标: Flask {flask_target}, Werkzeug {werkzeug_spec}")
    info("开始安装兼容依赖 ...")

    for name, spec in deps.items():
        info(f"安装 {name} {spec} ...")
        rc, out, err = pip_install(spec, upgrade=True)
        if rc != 0:
            fail(f"{name} 安装失败: {err[:300]}")
        else:
            new_ver = get_installed_version(name.capitalize() if name != "werkzeug" else "Werkzeug")
            ok(f"{name} {new_ver}")

    # 最终验证
    info("\n验证安装结果 ...")
    rc, out, err = run([
        sys.executable, "-c",
        "import flask; print(f'Flask {flask.__version__}'); "
        "import werkzeug; print(f'Werkzeug {werkzeug.__version__}')"
    ], capture=True)
    if rc == 0:
        ok(f"安装验证通过:\n{out.strip()}")
        return True
    else:
        fail(f"安装验证失败: {err[:500]}")
        return False


def fix_python_path():
    """修复 PYTHONPATH 和 sys.path 优先级问题"""
    print(f"\n{BOLD}修复路径优先级问题{RESET}")

    # 确保当前目录在路径中
    cwd = os.getcwd()
    if cwd not in sys.path:
        info(f"添加 {cwd} 到 PYTHONPATH")
        # 写入 .pth 文件
        site_packages = None
        for p in sys.path:
            if "site-packages" in p and os.path.isdir(p):
                site_packages = p
                break
        if site_packages:
            pth_file = os.path.join(site_packages, "fix_flask_env.pth")
            with open(pth_file, "w") as f:
                f.write(cwd + "\n")
            ok(f"已创建 {pth_file}")
        else:
            warn("未找到 site-packages，请手动设置: "
                 f"$env:PYTHONPATH = \"{cwd};$env:PYTHONPATH\"")

    # 检查是否有多个 Python 版本冲突
    info("检查 Python 解释器一致性 ...")
    py_version = sys.version[:5]

    # 检查 PATH 中的 python 与当前是否一致
    if os.name == "nt":
        where_cmd = ["where", "python"]
    else:
        where_cmd = ["which", "python3", "python"]

    rc, out, err = run(where_cmd, capture=True)
    if rc == 0:
        python_in_path = out.strip().splitlines()
        current_py = sys.executable.lower()
        other_pythons = [p for p in python_in_path if p.lower() != current_py]
        if other_pythons:
            warn(f"PATH 中发现其他 Python: {other_pythons}")
            warn("确保运行脚本时使用的是正确的 Python")
            for op in other_pythons:
                rc2, out2, _ = run([op, "--version"], capture=True)
                if rc2 == 0:
                    warn(f"  {op} → {out2.strip()}")
    else:
        ok("Python 路径一致")


# ── 生成启动脚本 ──────────────────────────────────────────

def generate_launcher():
    """生成修复后的环境变量启动脚本"""
    print(f"\n{BOLD}生成启动辅助脚本{RESET}")

    # Windows batch
    bat_content = """@echo off
REM Flask 修复环境启动脚本
REM 设置关键环境变量来缓解 zipimport/socket 问题

set PYTHON_IGNORE_IMPORT_FAILURE=1
set FLASK_ENV=development
set FLASK_APP=app.py

echo [INFO] 已设置 PYTHON_IGNORE_IMPORT_FAILURE=1
echo [INFO] 启动 Flask 应用...

python -m flask run --host=0.0.0.0 --port=5000
if errorlevel 1 (
    echo [ERROR] Flask 启动失败，尝试用 python app.py 直接运行...
    python app.py
)
"""
    bat_path = "run_flask_fix.bat"
    with open(bat_path, "w") as f:
        f.write(bat_content)
    ok(f"生成 Windows 启动脚本: {bat_path}")

    # PowerShell
    ps_content = """# Flask 修复环境启动脚本
$env:PYTHON_IGNORE_IMPORT_FAILURE = "1"
$env:FLASK_ENV = "development"
$env:FLASK_APP = "app.py"

Write-Host "[INFO] 已设置 PYTHON_IGNORE_IMPORT_FAILURE=1" -ForegroundColor Cyan
Write-Host "[INFO] 启动 Flask 应用..." -ForegroundColor Cyan

try {
    python -m flask run --host=0.0.0.0 --port=5000
} catch {
    Write-Host "[ERROR] Flask 启动失败，尝试直接运行 app.py..." -ForegroundColor Red
    python app.py
}
"""
    ps_path = "run_flask_fix.ps1"
    with open(ps_path, "w") as f:
        f.write(ps_content)
    ok(f"生成 PowerShell 启动脚本: {ps_path}")

    # Shell (Linux/Mac)
    sh_content = """#!/bin/sh
# Flask 修复环境启动脚本
export PYTHON_IGNORE_IMPORT_FAILURE=1
export FLASK_ENV=development
export FLASK_APP=app.py

echo "[INFO] 已设置 PYTHON_IGNORE_IMPORT_FAILURE=1"
echo "[INFO] 启动 Flask 应用..."

python3 -m flask run --host=0.0.0.0 --port=5000 ||
python app.py
"""
    sh_path = "run_flask_fix.sh"
    with open(sh_path, "w") as f:
        f.write(sh_content)
    os.chmod(sh_path, 0o755)
    ok(f"生成 Shell 启动脚本: {sh_path}")


# ── 主流程 ──────────────────────────────────────────────

def main():
    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}   Flask 环境修复工具{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    all_issues = []

    # ── 阶段1: 诊断 ──
    print(f"\n{BOLD}{'─'*40}{RESET}")
    print(f"{BOLD}   诊断阶段{RESET}")
    print(f"{BOLD}{'─'*40}{RESET}")

    py_issues = diagnose_python()
    all_issues.extend(py_issues)

    sock_issues = diagnose_socket()
    all_issues.extend(sock_issues)

    flask_issues = diagnose_flask()
    all_issues.extend(flask_issues)

    # ── 汇总 ──
    print(f"\n{BOLD}{'─'*40}{RESET}")
    print(f"{BOLD}   诊断结果汇总{RESET}")
    print(f"{BOLD}{'─'*40}{RESET}")

    if all_issues:
        warn(f"发现 {len(all_issues)} 个问题:")
        for iss in all_issues:
            warn(f"  - {iss}")
    else:
        ok("未发现明显问题，环境正常！")
        print(f"\n如果仍然无法启动，请手动运行:")
        print(f"  pip install --upgrade flask werkzeug")
        print(f"  set PYTHON_IGNORE_IMPORT_FAILURE=1")
        print(f"  python app.py")
        return

    # ── 阶段2: 修复 ──
    print(f"\n{BOLD}{'─'*40}{RESET}")
    print(f"{BOLD}   修复阶段{RESET}")
    print(f"{BOLD}{'─'*40}{RESET}")

    socket_fixed = fix_zipimport_issue()
    deps_fixed = fix_flask_deps()

    fix_python_path()

    # ── 阶段3: 最终验证 ──
    print(f"\n{BOLD}{'─'*40}{RESET}")
    print(f"{BOLD}   最终验证{RESET}")
    print(f"{BOLD}{'─'*40}{RESET}")

    info("重新检查 socket 模块 ...")
    rc, out, err = run([sys.executable, "-c", "import socket; s=socket.socket(); s.close(); print('OK')"], capture=True)
    if rc == 0 and "OK" in out:
        ok("socket 模块正常")
    else:
        fail(f"socket 仍然异常: {err[:300]}")
        warn("可能需要重新安装 Python")

    info("重新检查 Flask 应用 ...")
    app_file = None
    for candidate in ["app.py", "wsgi.py", "application.py", "manage.py", "run.py"]:
        if os.path.isfile(candidate):
            app_file = candidate
            break
    if app_file:
        rc, out, err = run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, '.'); exec(open('{app_file}').read())"],
            capture=True, timeout=10
        )
        if rc == 0:
            ok(f"{app_file} 加载成功")
        else:
            fail(f"{app_file} 加载失败: {err[:300]}")

    # ── 生成启动脚本 ──
    generate_launcher()

    # ── 最终建议 ──
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}   修复完成{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    print(f"\n如果问题已解决，运行应用:")
    print(f"  run_flask_fix.bat        (Windows CMD)")
    print(f"  .\\run_flask_fix.ps1      (PowerShell)")
    print(f"  bash run_flask_fix.sh    (Linux/Mac)")
    print(f"\n或手动:")
    print(f"  set PYTHON_IGNORE_IMPORT_FAILURE=1")
    print(f"  python app.py")
    print(f"\n如果仍然失败，请尝试:")
    print(f"  1. 重新安装 Python (保留已有包):")
    print(f"     winget install Python.Python.3.12")
    print(f"  2. 使用虚拟环境隔离:")
    print(f"     python -m venv venv")
    print(f"     venv\\Scripts\\activate")
    print(f"     pip install flask==3.1.1 werkzeug==3.1.3")
    print(f"     python app.py")


if __name__ == "__main__":
    main()
