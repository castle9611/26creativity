"""Fail before startup if Python or installed dependencies are outside the bundle."""
import importlib
import importlib.metadata
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def within(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([path, root]) == root


def check():
    prefix = os.path.join(BASE_DIR, 'python-linux')
    if sys.version_info[:3] != (3, 8, 10) or not within(sys.executable, prefix):
        raise RuntimeError('Use the bundled Python 3.8.10 only')
    if not sys.flags.isolated:
        raise RuntimeError('Run the bundled interpreter with -I')
    with open(os.path.join(prefix, '.oa-runtime-ready')) as handle:
        if handle.read() != prefix:
            raise RuntimeError('Install directory changed. Re-extract and install in the final location.')
    if any(not within(path, prefix) for path in sys.path if path):
        raise RuntimeError('Python search path contains an external directory: ' + repr(sys.path))
    with open(os.path.join(BASE_DIR, 'requirements-kylin-arm64.txt')) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            name, required = line.split('==')
            package = importlib.metadata.distribution(name)
            if package.version != required or not within(str(package.locate_file('')), prefix):
                raise RuntimeError('Dependency is missing, external or has wrong version: ' + name)
    for package in importlib.metadata.distributions():
        if not within(str(package.locate_file('')), prefix):
            raise RuntimeError('Found an external installed package: ' + package.metadata['Name'])
    for name in ('ssl', 'sqlite3', 'bz2', 'lzma', 'ctypes', 'flask', 'flask_sqlalchemy',
                 'sqlalchemy', 'greenlet', 'lxml.etree', 'PIL._imaging', 'docx',
                 'openpyxl', 'pptx', 'pypdf', 'xlrd', 'requests', 'jwt'):
        module = importlib.import_module(name)
        if getattr(module, '__file__', None) and not within(module.__file__, prefix):
            raise RuntimeError('Imported an external dependency: ' + name)
    print('[OK] Python 3.8.10 and application dependencies are inside python-linux.')


if __name__ == '__main__':
    check()
