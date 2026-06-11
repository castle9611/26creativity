# -*- coding: utf-8 -*-
"""
Pure-Python runtime diagnostics for old Windows 7 targets.
This script intentionally avoids ctypes/socket/sqlite3 at top level.
Run with: python\python.exe runtime_diagnose.py
"""
import os
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_DIR = os.path.join(BASE_DIR, "python")
PYTHON_EXE = os.path.join(PYTHON_DIR, "python.exe")
OUT_DIR = os.path.join(BASE_DIR, "diagnose_output")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.environ["PATH"] = PYTHON_DIR + os.pathsep + os.path.join(PYTHON_DIR, "DLLs") + os.pathsep + os.environ.get("PATH", "")
os.environ["PYTHONPATH"] = BASE_DIR
os.environ["PYTHONIOENCODING"] = "utf-8:backslashreplace"


def safe_print(text=""):
    """Print safely on old Win7 consoles with fragile encodings."""
    if not isinstance(text, str):
        text = str(text)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    data = (text + "\n").encode(encoding, "backslashreplace")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    except Exception:
        sys.stdout.write((text + "\n").encode("ascii", "backslashreplace").decode("ascii"))
        sys.stdout.flush()


def q(path):
    return '"' + path + '"'


def cmd_wrap(command):
    return '"' + command + '"'


def section(title):
    safe_print("")
    safe_print("==== " + title + " ====")


def ensure_out_dir():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)


def run_child(name, code):
    ensure_out_dir()
    out_file = os.path.join(OUT_DIR, name + ".txt")
    script_file = os.path.join(OUT_DIR, name + ".py")
    with open(script_file, "w") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write(code)
        f.write("\n")
    cmd = cmd_wrap(q(PYTHON_EXE) + " " + q(script_file) + " > " + q(out_file) + " 2>&1")
    rc = os.system(cmd)
    if rc == 0:
        safe_print("[OK] " + name)
    else:
        safe_print("[FAIL] " + name + " exit=" + str(rc))
    try:
        with open(out_file, "r") as f:
            content = f.read().strip()
        if content:
            safe_print(content)
    except Exception as exc:
        safe_print("Cannot read output: " + repr(exc))
    return rc == 0


def main():
    safe_print("Base dir : " + BASE_DIR)
    safe_print("Python   : " + sys.executable)
    safe_print("Version  : " + sys.version.replace("\n", " "))
    safe_print("PATH head: " + os.environ.get("PATH", "")[:500])

    section("Required files")
    for filename in [
        "python.exe",
        "python38.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "libffi-7.dll",
        "sqlite3.dll",
        "_ctypes.pyd",
        "_socket.pyd",
        "_sqlite3.pyd",
    ]:
        path = os.path.join(PYTHON_DIR, filename)
        if os.path.exists(path):
            safe_print("[OK] exists " + filename + " (%s bytes)" % os.path.getsize(path))
        else:
            safe_print("[FAIL] missing " + filename)

    section("App-local CRT api-set files")
    api_files = [f for f in os.listdir(PYTHON_DIR) if f.lower().startswith("api-ms-win-crt-") and f.lower().endswith(".dll")]
    safe_print("api-ms-win-crt dll count: " + str(len(api_files)))
    for filename in sorted(api_files):
        safe_print("  " + filename)
    if api_files or os.path.exists(os.path.join(PYTHON_DIR, "ucrtbase.dll")):
        safe_print("[WARN] App-local UCRT files exist. On Win7 this can cause DLL load failed: parameter incorrect.")
        safe_print("[WARN] Use the latest package and run install_win7_runtime.bat as Administrator instead.")
    else:
        safe_print("[OK] No app-local UCRT files. System runtime will be used.")

    section("Child process import tests")
    tests = [
        ("import_ctypes", "import ctypes; print('ctypes OK')"),
        ("import__ctypes", "import _ctypes; print('_ctypes OK')"),
        ("import_socket", "import socket; print('socket OK')"),
        ("import__socket", "import _socket; print('_socket OK')"),
        ("import_sqlite3", "import sqlite3; print('sqlite3 OK', sqlite3.sqlite_version)"),
        ("import__sqlite3", "import _sqlite3; print('_sqlite3 OK')"),
        ("import_flask", "import flask; print('flask OK', flask.__version__)"),
        ("import_sqlalchemy", "import sqlalchemy; print('sqlalchemy OK', sqlalchemy.__version__)"),
    ]
    all_ok = True
    for name, code in tests:
        all_ok = run_child(name, code) and all_ok

    section("Raw extension dependency imports")
    raw_tests = [
        ("raw_socket_verbose", "import importlib, traceback\ntry:\n importlib.import_module('_socket'); print('OK')\nexcept BaseException:\n traceback.print_exc(); raise"),
        ("raw_ctypes_verbose", "import importlib, traceback\ntry:\n importlib.import_module('_ctypes'); print('OK')\nexcept BaseException:\n traceback.print_exc(); raise"),
        ("raw_sqlite_verbose", "import importlib, traceback\ntry:\n importlib.import_module('_sqlite3'); print('OK')\nexcept BaseException:\n traceback.print_exc(); raise"),
    ]
    for name, code in raw_tests:
        all_ok = run_child(name, code) and all_ok

    safe_print("")
    if all_ok:
        safe_print("[OK] Runtime diagnostics passed.")
    else:
        safe_print("[FAIL] Runtime diagnostics found errors.")
        safe_print("Please send the FAIL lines and the text under them.")
        safe_print("Detailed files are in: " + OUT_DIR)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
