# -*- coding: utf-8 -*-
"""
Offline deployment self-check for Windows and Linux ARM64 packages.
"""
import os
import platform
import subprocess
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WINDOWS = os.name == "nt"
PYTHON_DIR = os.path.join(BASE_DIR, "python")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if IS_WINDOWS:
    os.environ["PATH"] = PYTHON_DIR + os.pathsep + os.path.join(PYTHON_DIR, "DLLs") + os.pathsep + os.environ.get("PATH", "")
os.environ["PYTHONPATH"] = BASE_DIR
os.environ["PYTHONIOENCODING"] = "utf-8:backslashreplace"
COMMON_REQUIRED_FILES = [
    "run.py",
    os.path.join("app", "__init__.py"),
    os.path.join("app", "config.py"),
]
WINDOWS_REQUIRED_FILES = [
    os.path.join("python", "python.exe"),
    os.path.join("python", "python38.dll"),
    os.path.join("python", "python38.zip"),
    os.path.join("python", "vcruntime140.dll"),
    os.path.join("python", "sqlite3.dll"),
    os.path.join("python", "libffi-7.dll"),
    os.path.join("python", "_ctypes.pyd"),
    os.path.join("python", "_sqlite3.pyd"),
    os.path.join("python", "_socket.pyd"),
]
LOW_LEVEL_IMPORTS = [
    ("_socket", "Python socket extension"),
    ("socket", "Python socket module"),
    ("_sqlite3", "Python SQLite extension"),
    ("sqlite3", "Python SQLite module"),
]
REQUIRED_IMPORTS = [
    ("flask", "Flask"),
    ("flask_sqlalchemy", "Flask-SQLAlchemy"),
    ("sqlalchemy", "SQLAlchemy"),
    ("jinja2", "Jinja2"),
    ("werkzeug", "Werkzeug"),
    ("click", "Click"),
    ("itsdangerous", "itsdangerous"),
    ("markupsafe", "MarkupSafe"),
]


def ok(message):
    print("[OK] " + message)


def warn(message):
    print("[WARN] " + message)


def fail(message):
    print("[FAIL] " + message)


def safe_print(text=""):
    if not isinstance(text, str):
        text = str(text)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        sys.stdout.buffer.write((text + "\n").encode(encoding, "backslashreplace"))
        sys.stdout.buffer.flush()
    except Exception:
        print(text.encode("ascii", "backslashreplace").decode("ascii"))


def check_file(path):
    full_path = os.path.join(BASE_DIR, path)
    if os.path.exists(full_path):
        ok(path)
        return True
    fail(path + " not found")
    return False


def check_import(module_name, label):
    try:
        module = __import__(module_name)
        version = getattr(module, "__version__", "")
        ok(label + ((" " + version) if version else ""))
        return True
    except BaseException as exc:
        fail(label + " import failed: " + repr(exc))
        return False


def check_import_child(module_name, label):
    out_file = os.path.join(BASE_DIR, "diagnose_output", "health_" + module_name.replace(".", "_") + ".txt")
    out_dir = os.path.dirname(out_file)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    script_file = os.path.join(out_dir, "health_" + module_name.replace(".", "_") + ".py")
    with open(script_file, "w") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write("import " + module_name + "\n")
        f.write("print('OK')\n")
    try:
        with open(out_file, "wb") as output_stream:
            completed = subprocess.run(
                [sys.executable, script_file],
                stdout=output_stream,
                stderr=subprocess.STDOUT,
            )
        rc = completed.returncode
    except Exception as exc:
        fail(label + " child process failed to start: " + repr(exc))
        return False
    try:
        with open(out_file, "r") as f:
            output = f.read().strip()
    except Exception:
        output = ""
    if rc == 0:
        ok(label)
        return True
    fail(label + " import failed in child process, exit=" + str(rc))
    if output:
        safe_print(output)
    return False


def check_port(port):
    try:
        import socket
    except Exception as exc:
        fail("socket module failed: " + repr(exc))
        return False

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        if result == 0:
            warn("Port %s is already in use. stop.bat can release the old service." % port)
        else:
            ok("Port %s is available" % port)
        return True
    finally:
        sock.close()


def main():
    print("============================================")
    print("  Offline Package Self Check")
    print("============================================")
    print("Base dir : " + BASE_DIR)
    print("Python   : " + sys.executable)
    print("Version  : " + sys.version.replace("\n", " "))
    print("OS       : " + platform.platform())
    print("")

    success = True

    print("[1/7] Required files")
    required_files = COMMON_REQUIRED_FILES + (WINDOWS_REQUIRED_FILES if IS_WINDOWS else [])
    for path in required_files:
        success = check_file(path) and success

    print("")
    print("[2/7] Low-level Python extensions")
    low_level_success = True
    for module_name, label in LOW_LEVEL_IMPORTS:
        low_level_success = check_import_child(module_name, label) and low_level_success
    success = low_level_success and success
    if not low_level_success:
        print("")
        if IS_WINDOWS:
            fail("Low-level runtime failed. Run: python\\python.exe runtime_diagnose.py")
        return 1

    print("")
    print("[3/7] Python packages")
    for module_name, label in REQUIRED_IMPORTS:
        success = check_import(module_name, label) and success

    print("")
    print("[4/7] SQLite")
    try:
        import sqlite3
        ok("sqlite3 " + sqlite3.sqlite_version)
    except Exception as exc:
        fail("sqlite3 failed: " + repr(exc))
        success = False

    print("")
    print("[5/7] Writable data directories")
    for folder in [os.path.join(BASE_DIR, "data"), os.path.join(BASE_DIR, "data", "uploads")]:
        try:
            if not os.path.isdir(folder):
                os.makedirs(folder)
            test_file = os.path.join(folder, ".write_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            ok(os.path.relpath(folder, BASE_DIR) + " writable")
        except Exception as exc:
            fail(os.path.relpath(folder, BASE_DIR) + " not writable: " + str(exc))
            success = False

    print("")
    print("[6/7] Flask application")
    try:
        from app import create_app
        app = create_app()
        client = app.test_client()
        response = client.get("/login")
        if response.status_code == 200:
            ok("Flask app loaded and /login returned 200")
        else:
            fail("Flask app loaded but /login returned %s" % response.status_code)
            success = False
    except BaseException as exc:
        fail("Flask app load failed: " + repr(exc))
        success = False

    print("")
    print("[7/7] Network port")
    success = check_port(5000) and success

    print("")
    if success:
        command = "start.bat" if IS_WINDOWS else "./start.sh"
        ok("Self check passed. You can start the system with " + command + ".")
        return 0

    fail("Self check failed. Please fix the items above before deployment.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
