"""Install the bundled CPython 3.8.10 using only Python 3.7 standard library."""
import hashlib
import copy
import json
import os
import platform
import re
import shlex
import subprocess
import tarfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def replace_prefix(data, old, new, binary):
    if not binary:
        return data.replace(old, new)
    if len(new) > len(old):
        raise ValueError('Install path is too long for the bundled binary')
    pattern = rb'[^\x00]*' + re.escape(old) + rb'[^\x00]*\x00'
    def replace(match):
        original = match.group()
        changed = original.replace(old, new)
        return changed + b'\x00' * (len(original) - len(changed))
    return re.sub(pattern, replace, data)


def safe_path(root, name):
    path = os.path.abspath(os.path.join(root, name))
    if os.path.commonpath([root, path]) != root:
        raise ValueError('Archive path escapes runtime directory: ' + name)
    return path


def runtime_path(name, noarch):
    if noarch:
        if name == 'site-packages' or name.startswith('site-packages/'):
            return 'lib/python3.8/' + name
        if name.startswith('python-scripts/'):
            return 'bin/' + name[len('python-scripts/'):]
    return name


def install():
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
        raise RuntimeError('Run this installer on Linux ARM64 only')
    folder = os.path.join(BASE_DIR, 'runtime_packages')
    prefix = os.path.join(BASE_DIR, 'python-linux')
    marker = os.path.join(prefix, '.oa-runtime-ready')
    if os.path.isfile(marker):
        with open(marker) as handle:
            if handle.read() != prefix:
                raise RuntimeError('Runtime was moved. Re-extract the package in its final location.')
    else:
        if os.path.exists(prefix):
            raise RuntimeError('python-linux already exists without a completed-install marker. '
                               'Use a newly extracted package directory to retry.')
        with open(os.path.join(folder, 'manifest.json')) as handle:
            packages = json.load(handle)
        # Verify every input before writing the runtime.
        for package in packages:
            with open(safe_path(folder, package['file']), 'rb') as handle:
                if hashlib.sha256(handle.read()).hexdigest() != package['sha256']:
                    raise RuntimeError('Runtime checksum mismatch: ' + package['file'])
        os.makedirs(prefix)
        for package in packages:
            with tarfile.open(os.path.join(folder, package['file']), 'r:bz2') as archive:
                try:
                    noarch_info = json.load(archive.extractfile('info/link.json')).get('noarch', {})
                except KeyError:
                    noarch_info = {}
                noarch = noarch_info.get('type') == 'python'
                for original in archive.getmembers():
                    member = copy.copy(original)
                    member.name = runtime_path(member.name, noarch)
                    if member.islnk():
                        member.linkname = runtime_path(member.linkname, noarch)
                    safe_path(prefix, member.name)
                    if member.name.startswith('info/') or member.name == 'info':
                        continue
                    if member.issym():
                        safe_path(prefix, os.path.join(os.path.dirname(member.name), member.linkname))
                    if member.islnk():
                        safe_path(prefix, member.linkname)
                    if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                        raise ValueError('Unsupported archive entry: ' + member.name)
                    archive.extract(member, prefix)
                try:
                    records = json.load(archive.extractfile('info/paths.json'))['paths']
                    records = [(p['_path'], p.get('prefix_placeholder'), p.get('file_mode')) for p in records]
                except KeyError:
                    try:
                        lines = archive.extractfile('info/has_prefix').read().decode().splitlines()
                    except KeyError:
                        lines = []
                    records = []
                    for line in lines:
                        parts = shlex.split(line)
                        records.append((parts[2], parts[0], parts[1]))
                for name, placeholder, mode in records:
                    if not placeholder:
                        continue
                    path = safe_path(prefix, runtime_path(name, noarch))
                    with open(path, 'rb') as handle:
                        data = handle.read()
                    changed = replace_prefix(data, placeholder.encode(), prefix.encode(), mode == 'binary')
                    with open(path, 'wb') as handle:
                        handle.write(changed)
                for entry in noarch_info.get('entry_points', []):
                    command, target = entry.split('=', 1)
                    module, function = target.strip().split(':', 1)
                    script = safe_path(prefix, 'bin/' + command.strip())
                    with open(script, 'w') as handle:
                        handle.write('#!%s/bin/python3.8\nfrom %s import %s\n'
                                     'if __name__ == "__main__":\n    import sys\n    sys.exit(%s())\n'
                                     % (prefix, module, function, function))
                    os.chmod(script, 0o755)
                # Preserve each upstream license instead of merging conflicting info directories.
                for member in archive.getmembers():
                    if member.isfile() and member.name.startswith('info/licenses/'):
                        destination = safe_path(prefix, 'licenses/' + package['name'] + '/' + member.name[14:])
                        os.makedirs(os.path.dirname(destination), exist_ok=True)
                        with open(destination, 'wb') as handle:
                            handle.write(archive.extractfile(member).read())
        with open(marker, 'w') as handle:
            handle.write(prefix)
    executable = os.path.join(prefix, 'bin', 'python3.8')
    subprocess.run([executable, '-I', '-c',
                    'import sys,ssl,sqlite3,zlib,bz2,lzma,ctypes,readline; '
                    'assert sys.version_info[:3] == (3,8,10); print(sys.version); '
                    'print(ssl.OPENSSL_VERSION); print("SQLite",sqlite3.sqlite_version)'], check=True)
    subprocess.run([executable, '-I', '-m', 'pip', '--version'], check=True)
    print('[OK] Bundled Python 3.8.10 is ready.')


if __name__ == '__main__':
    install()
