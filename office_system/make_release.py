# -*- coding: utf-8 -*-
"""
Create a copy-and-run offline release package for other Windows computers.

Default:
    python\python.exe make_release.py

Clean first-run package without current database/uploads:
    python\python.exe make_release.py --fresh-data
"""
import argparse
import os
import shutil
import sys
import zipfile


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
RELEASE_ROOT = os.path.join(ROOT_DIR, "release")
PACKAGE_NAME = "office_system_win7_offline"

EXCLUDED_DIRS = {
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "tmp_wheels",
    "tmp_wheels2",
    "Deprecated",
    "logs",
    "diagnose_output",
}
EXCLUDED_FILES = {
    "get-pip.py",
}
EXCLUDED_APPLOCAL_RUNTIME_DLLS = {
    "ucrtbase.dll",
    "msvcp140.dll",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
}


def should_skip(src_path, rel_path, fresh_data):
    name = os.path.basename(src_path)
    if name in EXCLUDED_DIRS or name in EXCLUDED_FILES:
        return True
    lower_name = name.lower()
    if rel_path.replace("\\", "/").lower().startswith("python/"):
        if lower_name.startswith("api-ms-win-crt-") and lower_name.endswith(".dll"):
            return True
        if lower_name in EXCLUDED_APPLOCAL_RUNTIME_DLLS:
            return True
    if os.path.isdir(src_path):
        return False
    if os.path.splitext(name)[1].lower() in EXCLUDED_SUFFIXES:
        return True
    if fresh_data:
        normalized = rel_path.replace("\\", "/").lower()
        if normalized == "data/database.db":
            return True
        if normalized.startswith("data/uploads/") and not normalized.endswith(".gitkeep"):
            return True
    return False


def copy_tree(src_dir, dst_dir, fresh_data):
    copied_files = 0
    for root, dirs, files in os.walk(src_dir):
        rel_root = os.path.relpath(root, src_dir)
        if rel_root == ".":
            rel_root = ""

        dirs[:] = [
            d for d in dirs
            if not should_skip(os.path.join(root, d), os.path.join(rel_root, d), fresh_data)
        ]

        for filename in files:
            src_path = os.path.join(root, filename)
            rel_path = os.path.join(rel_root, filename)
            if should_skip(src_path, rel_path, fresh_data):
                continue
            dst_path = os.path.join(dst_dir, rel_path)
            parent = os.path.dirname(dst_path)
            if not os.path.isdir(parent):
                os.makedirs(parent)
            shutil.copy2(src_path, dst_path)
            copied_files += 1

    for folder in ["data", os.path.join("data", "uploads")]:
        path = os.path.join(dst_dir, folder)
        if not os.path.isdir(path):
            os.makedirs(path)

    return copied_files


def validate_package(package_dir):
    required = [
        os.path.join(package_dir, "start.bat"),
        os.path.join(package_dir, "stop.bat"),
        os.path.join(package_dir, "run.py"),
        os.path.join(package_dir, "health_check.py"),
        os.path.join(package_dir, "python", "python.exe"),
        os.path.join(package_dir, "python", "python38.dll"),
        os.path.join(package_dir, "python", "_sqlite3.pyd"),
        os.path.join(package_dir, "python", "sqlite3.dll"),
        os.path.join(package_dir, "python", "vcruntime140.dll"),
        os.path.join(package_dir, "python", "Lib", "site-packages", "flask"),
        os.path.join(package_dir, "python", "Lib", "site-packages", "sqlalchemy"),
        os.path.join(package_dir, "app", "__init__.py"),
    ]
    missing = [path for path in required if not os.path.exists(path)]
    if missing:
        print("[FAIL] Missing required files:")
        for path in missing:
            print("  " + os.path.relpath(path, package_dir))
        return False
    return True

def make_zip(package_dir, zip_path):
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(package_dir):
            for filename in files:
                full_path = os.path.join(root, filename)
                arcname = os.path.relpath(full_path, os.path.dirname(package_dir))
                zf.write(full_path, arcname)


def dir_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for filename in files:
            total += os.path.getsize(os.path.join(root, filename))
    return total


def main():
    parser = argparse.ArgumentParser(description="Build Win7 offline release package.")
    parser.add_argument("--fresh-data", action="store_true",
                        help="do not include current database.db or uploaded files")
    parser.add_argument("--no-zip", action="store_true",
                        help="only create release directory, do not create zip")
    args = parser.parse_args()

    package_dir = os.path.join(RELEASE_ROOT, PACKAGE_NAME)
    zip_path = package_dir + ".zip"

    print("============================================")
    print("  Build Win7 Offline Release Package")
    print("============================================")
    print("Source : " + BASE_DIR)
    print("Output : " + package_dir)
    print("Mode   : " + ("fresh first-run data" if args.fresh_data else "include current data"))
    print("")

    if os.path.isdir(package_dir):
        shutil.rmtree(package_dir)
    if not os.path.isdir(RELEASE_ROOT):
        os.makedirs(RELEASE_ROOT)

    copied = copy_tree(BASE_DIR, package_dir, args.fresh_data)
    print("[OK] Copied %s files" % copied)
    print("[OK] App-local UCRT DLLs excluded; target Win7 must use install_win7_runtime.bat")

    if not validate_package(package_dir):
        return 1
    print("[OK] Package validation passed")

    if not args.no_zip:
        make_zip(package_dir, zip_path)
        print("[OK] Zip created: " + zip_path)
        print("[OK] Zip size: %.1f MB" % (os.path.getsize(zip_path) / 1024.0 / 1024.0))

    print("[OK] Directory size: %.1f MB" % (dir_size(package_dir) / 1024.0 / 1024.0))
    print("")
    print("Next step: copy the release directory or zip to the target offline computer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
