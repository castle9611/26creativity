# -*- coding: utf-8 -*-
"""
Create a copy-and-run offline release package for other Windows computers.

Default (copies working directory as-is, including uncommitted changes):
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

# Directories to always exclude (relative to BASE_DIR)
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
    ".claude",
    "_deprecated",
    "portable_dist",
}

# Files to always exclude
EXCLUDED_FILES = {
    "get-pip.py",
}

# Within python/, exclude these DLLs (target Win7 must use install_win7_runtime.bat)
EXCLUDED_PYTHON_DLLS = {
    "ucrtbase.dll",
    "msvcp140.dll",
}

# File suffixes to exclude
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
}

# Untracked files (not in git but exist on disk) to always include
# (None means include all untracked, only add specific ones if needed)
ALWAYS_INCLUDE_UNTRACKED = {}  # e.g. {"sample_upload.png": True}


def should_skip(src_path, rel_path, fresh_data):
    """Return True if this file/dir should be excluded from the package."""
    name = os.path.basename(src_path)

    # Always skip these directory names
    if name in EXCLUDED_DIRS:
        return True

    # Always skip these file names
    if name in EXCLUDED_FILES:
        return True

    # Handle python/ directory specially
    normalized = rel_path.replace("\\", "/").lower()
    if normalized.startswith("python/"):
        lower_name = name.lower()
        # Skip API-MS-WIN-CRT-* DLLs (require target to have KB2999226)
        if lower_name.startswith("api-ms-win-crt-") and lower_name.endswith(".dll"):
            return True
        # Skip specific DLLs that need runtime installer
        if lower_name in EXCLUDED_PYTHON_DLLS:
            return True

    # Skip by suffix
    if os.path.isdir(src_path):
        return False
    ext = os.path.splitext(name)[1].lower()
    if ext in EXCLUDED_SUFFIXES:
        return True

    # Fresh-data mode: skip the database and user uploads
    if fresh_data:
        if normalized == "data/database.db":
            return True
        if normalized.startswith("data/uploads/") and name != ".gitkeep":
            return True

    return False


def copy_file_raw(src_path, dst_path):
    """Copy a single file preserving content exactly (binary-safe)."""
    dst_dir = os.path.dirname(dst_path)
    if not os.path.isdir(dst_dir):
        os.makedirs(dst_dir)

    with open(src_path, "rb") as f_in:
        data = f_in.read()
    with open(dst_path, "wb") as f_out:
        f_out.write(data)


def copy_tree(src_dir, dst_dir, fresh_data):
    """
    Walk src_dir and copy all files to dst_dir, respecting exclusions.
    Reads file content directly to avoid any git/checkout interference.
    """
    copied_files = 0
    skipped_files = 0

    for root, dirs, files in os.walk(src_dir):
        # Compute relative path of current directory
        rel_root = os.path.relpath(root, src_dir)
        if rel_root == ".":
            rel_root = ""

        # Filter subdirectories in-place (prevent os.walk from descending)
        dirs[:] = [
            d for d in dirs
            if not should_skip(os.path.join(root, d), os.path.join(rel_root, d), fresh_data)
        ]

        for filename in files:
            src_path = os.path.join(root, filename)
            rel_path = os.path.join(rel_root, filename)

            if should_skip(src_path, rel_path, fresh_data):
                skipped_files += 1
                continue

            dst_path = os.path.join(dst_dir, rel_path)
            copy_file_raw(src_path, dst_path)
            copied_files += 1

    # Always ensure data directories exist
    for folder in ["data", os.path.join("data", "uploads")]:
        path = os.path.join(dst_dir, folder)
        if not os.path.isdir(path):
            os.makedirs(path)

    return copied_files, skipped_files


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

    # Check for uncommitted changes (informational only)
    git_status_output = ""
    has_uncommitted = False
    try:
        import subprocess
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        git_status_output = result.stdout.strip()
        if git_status_output:
            has_uncommitted = True
    except Exception:
        pass

    print("============================================")
    print("  Build Win7 Offline Release Package")
    print("============================================")
    print("Source : " + BASE_DIR)
    print("Output : " + package_dir)
    print("Mode   : " + ("fresh first-run data" if args.fresh_data else "include current data"))

    if has_uncommitted:
        print("")
        print("[NOTE] Working directory has uncommitted changes (included in package):")
        changed_files = [line.strip() for line in git_status_output.splitlines() if line.strip()]
        for f in changed_files:
            print("  " + f)

    print("")

    if os.path.isdir(package_dir):
        shutil.rmtree(package_dir)
    if not os.path.isdir(RELEASE_ROOT):
        os.makedirs(RELEASE_ROOT)

    copied, skipped = copy_tree(BASE_DIR, package_dir, args.fresh_data)
    print("[OK] Copied %s files (%s skipped)" % (copied, skipped))
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
