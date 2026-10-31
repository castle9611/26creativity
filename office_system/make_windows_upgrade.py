# -*- coding: utf-8 -*-
"""Build a Windows 7 application upgrade without runtime or user data."""
import os
import shutil
import zipfile


BASE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(os.path.dirname(BASE), 'release', 'windows_upgrade')
OUT = os.path.join(OUT_ROOT, 'office_system')
FILES = ['run.py', 'wsgi.py', 'migrate.py', 'health_check.py', 'backup.py',
         'start.bat', 'start_hidden.bat', 'stop.bat', 'status.bat',
         'convert_video.bat', 'upgrade_windows.bat', 'WINDOWS_UPGRADE.md']
SKIP_DIRS = {'__pycache__', '.git', 'data', 'logs', 'python', 'test', 'tests',
             'Deprecated', '_deprecated', 'diagnose_output'}
SKIP_SUFFIXES = ('.pyc', '.pyo', '.log')


def copy_app():
    source = os.path.join(BASE, 'app')
    target = os.path.join(OUT, 'app')
    static_dir = os.path.normcase(os.path.join(source, 'static'))
    for root, dirs, files in os.walk(source):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not (
            os.path.normcase(root) == static_dir and name == 'uploads')]
        relative = os.path.relpath(root, source)
        destination = target if relative == '.' else os.path.join(target, relative)
        os.makedirs(destination, exist_ok=True)
        for name in files:
            if not name.lower().endswith(SKIP_SUFFIXES):
                shutil.copy2(os.path.join(root, name), os.path.join(destination, name))


def main():
    if os.path.isdir(OUT_ROOT):
        shutil.rmtree(OUT_ROOT)
    os.makedirs(OUT)
    copy_app()
    for name in FILES:
        shutil.copy2(os.path.join(BASE, name), os.path.join(OUT, name))
    manifest = []
    for root, dirs, files in os.walk(OUT):
        for name in files:
            manifest.append(os.path.relpath(os.path.join(root, name), OUT).replace('\\', '/'))
    manifest.sort()
    with open(os.path.join(OUT, 'PACKAGE_MANIFEST.txt'), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write('\n'.join(manifest) + '\n')
    zip_path = os.path.join(OUT_ROOT, 'office_system_windows_upgrade.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for root, dirs, files in os.walk(OUT):
            for name in files:
                path = os.path.join(root, name)
                archive.write(path, os.path.relpath(path, OUT_ROOT))
    print('[OK] Windows upgrade package: ' + zip_path)
    print('[OK] Files: {}'.format(len(manifest) + 1))


if __name__ == '__main__':
    main()
