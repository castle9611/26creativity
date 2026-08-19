# -*- coding: utf-8 -*-
"""
Create separate Windows and Kylin ARM64 release directories.

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
WINDOWS_PACKAGE_NAME = os.path.join("windows", "office_system")
KYLIN_PACKAGE_NAME = os.path.join("kylin_arm64", "office_system")

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


def should_skip(src_path, rel_path, fresh_data, target):
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
    if target == "kylin-arm64":
        if normalized == "python" or normalized.startswith("python/"):
            return True
        if normalized == "runtime_install" or normalized.startswith("runtime_install/"):
            return True
        if normalized.endswith((".bat", ".cmd", ".vbs", ".exe", ".dll", ".pyd", ".msu")):
            return True
    elif normalized.endswith(".sh") or normalized == "requirements-kylin-arm64.txt":
        return True
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


def copy_tree(src_dir, dst_dir, fresh_data, target):
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
            if not should_skip(os.path.join(root, d), os.path.join(rel_root, d), fresh_data, target)
        ]

        for filename in files:
            src_path = os.path.join(root, filename)
            rel_path = os.path.join(rel_root, filename)

            if should_skip(src_path, rel_path, fresh_data, target):
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


def validate_package(package_dir, target):
    required = [
        os.path.join(package_dir, "run.py"),
        os.path.join(package_dir, "health_check.py"),
        os.path.join(package_dir, "app", "__init__.py"),
    ]
    if target == "windows":
        required.extend([
            os.path.join(package_dir, "start.bat"),
            os.path.join(package_dir, "stop.bat"),
            os.path.join(package_dir, "convert_video.bat"),
            os.path.join(package_dir, "python", "python.exe"),
            os.path.join(package_dir, "python", "python38.dll"),
            os.path.join(package_dir, "python", "_sqlite3.pyd"),
            os.path.join(package_dir, "python", "sqlite3.dll"),
            os.path.join(package_dir, "python", "vcruntime140.dll"),
        ])
    else:
        required.extend([
            os.path.join(package_dir, "start.sh"),
            os.path.join(package_dir, "stop.sh"),
            os.path.join(package_dir, "status.sh"),
            os.path.join(package_dir, "convert_video.sh"),
            os.path.join(package_dir, "requirements-kylin-arm64.txt"),
        ])
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
    parser = argparse.ArgumentParser(description="Build Windows and Kylin ARM64 release packages.")
    parser.add_argument("--fresh-data", action="store_true",
                        help="do not include current database.db or uploaded files")
    parser.add_argument("--no-zip", action="store_true",
                        help="only create release directory, do not create zip")
    parser.add_argument("--target", choices=("all", "windows", "kylin-arm64"), default="all")
    args = parser.parse_args()

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
    print("  Build Platform Release Packages")
    print("============================================")
    print("Source : " + BASE_DIR)
    print("Output : " + RELEASE_ROOT)
    print("Mode   : " + ("fresh first-run data" if args.fresh_data else "include current data"))

    if has_uncommitted:
        print("")
        print("[NOTE] Working directory has uncommitted changes (included in package):")
        changed_files = [line.strip() for line in git_status_output.splitlines() if line.strip()]
        for f in changed_files:
            print("  " + f)

    print("")

    if not os.path.isdir(RELEASE_ROOT):
        os.makedirs(RELEASE_ROOT)
    targets = ("windows", "kylin-arm64") if args.target == "all" else (args.target,)
    for target in targets:
        package_name = WINDOWS_PACKAGE_NAME if target == "windows" else KYLIN_PACKAGE_NAME
        package_dir = os.path.join(RELEASE_ROOT, package_name)
        zip_path = os.path.join(RELEASE_ROOT, target.replace("-", "_"), "office_system.zip")
        if os.path.isdir(package_dir):
            shutil.rmtree(package_dir)
        copied, skipped = copy_tree(BASE_DIR, package_dir, args.fresh_data, target)
        print("[OK] %s: copied %s files (%s skipped)" % (target, copied, skipped))
        if not validate_package(package_dir, target):
            return 1
        if target == "kylin-arm64":
            for script in ("start.sh", "stop.sh", "status.sh", "install_dependencies.sh", "convert_video.sh"):
                path = os.path.join(package_dir, script)
                if os.path.isfile(path):
                    os.chmod(path, 0o755)
        if not args.no_zip:
            make_zip(package_dir, zip_path)
            print("[OK] Zip created: " + zip_path)
        print("[OK] %s directory size: %.1f MB" % (target, dir_size(package_dir) / 1024.0 / 1024.0))
    print("")
    print("Next step: copy the release directory or zip to the target offline computer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
