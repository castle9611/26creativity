"""Build a code-only overlay without assuming a container path or entrypoint."""
import hashlib
from datetime import datetime
from pathlib import Path
import zipfile

BASE = Path(__file__).resolve().parent
EXCLUDED_DIRS = {'uploads', 'avatars', 'data', 'logs', '__pycache__',
                 'test', 'tests', '.git', 'Deprecated', '_deprecated'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.log', '.db', '.sqlite', '.sqlite3',
                     '.bak', '.tmp', '.exe', '.dll', '.pyd', '.bat', '.vbs'}


def main():
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output = BASE.parent / 'release' / ('docker_app_patch_' + stamp)
    output.mkdir(parents=True, exist_ok=False)
    files = []
    for path in sorted((BASE / 'app').rglob('*')):
        relative = path.relative_to(BASE)
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name.endswith(('-wal', '-shm')):
            continue
        # Preserve server-specific configuration and all existing entrypoints.
        if relative.as_posix() == 'app/config.py':
            continue
        files.append((path, 'office_system/' + relative.as_posix()))
    files.append((BASE / 'migrate.py', 'office_system/migrate.py'))
    files.append((BASE / 'DOCKER_PATCH_README.md', 'README.md'))
    manifest = []
    archive_path = output / ('office_system_docker_arm64_patch_' + stamp + '.zip')
    with zipfile.ZipFile(str(archive_path), 'x', zipfile.ZIP_DEFLATED) as archive:
        for source, name in files:
            data = source.read_bytes()
            if source.suffix == '.py':
                compile(data, name, 'exec')
            archive.writestr(name, data)
            manifest.append(hashlib.sha256(data).hexdigest() + '  ' + name)
        archive.writestr('SHA256SUMS.txt', '\n'.join(manifest) + '\n')
    with zipfile.ZipFile(str(archive_path)) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(files) + 1
        for name in archive.namelist():
            assert not set(name.split('/')) & EXCLUDED_DIRS, name
            assert not name.endswith(('.db', '.sqlite', '.sqlite3', '.log', '.pyc')), name
        for entry in manifest:
            digest, name = entry.split('  ', 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (output / (archive_path.name + '.sha256')).write_text(
        digest + '  ' + archive_path.name + '\n', encoding='ascii')
    print(str(archive_path))
    print('Files: {}; bytes: {}; SHA256: {}'.format(len(files) + 1, archive_path.stat().st_size, digest))
    print('Verified archive, exclusions, file hashes and Python syntax.')


if __name__ == '__main__':
    main()
