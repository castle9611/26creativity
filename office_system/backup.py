# -*- coding: utf-8 -*-
"""
Database backup and restore utility.
"""
import os
import sys
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

DB_PATH = os.path.join(BASE_DIR, 'data', 'database.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'data', 'backups')


def backup():
    """Create a timestamped backup of the database."""
    if not os.path.exists(DB_PATH):
        print('[ERROR] Database file not found:', DB_PATH)
        return

    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = 'database_backup_{}.db'.format(timestamp)
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    shutil.copy2(DB_PATH, backup_path)
    print('[OK] Backup created:', backup_path)

    # Keep only last 10 backups
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')])
    while len(backups) > 10:
        old = backups.pop(0)
        os.remove(os.path.join(BACKUP_DIR, old))
        print('[INFO] Removed old backup:', old)


def restore(backup_filename):
    """Restore database from a backup file."""
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    if not os.path.exists(backup_path):
        print('[ERROR] Backup not found:', backup_path)
        return

    # Backup current DB before restore
    if os.path.exists(DB_PATH):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pre_restore = os.path.join(BACKUP_DIR, 'pre_restore_{}.db'.format(timestamp))
        shutil.copy2(DB_PATH, pre_restore)
        print('[INFO] Pre-restore backup saved:', pre_restore)

    shutil.copy2(backup_path, DB_PATH)
    print('[OK] Database restored from:', backup_path)


def list_backups():
    """List available backups."""
    if not os.path.exists(BACKUP_DIR):
        print('[INFO] No backups found')
        return []

    backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')],
        reverse=True
    )
    if backups:
        print('Available backups:')
        for b in backups:
            full_path = os.path.join(BACKUP_DIR, b)
            size = os.path.getsize(full_path)
            print('  {}  ({:.1f} KB)'.format(b, size / 1024.0))
    else:
        print('[INFO] No backups found')
    return backups


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Database backup utility')
    parser.add_argument('action', choices=['backup', 'restore', 'list'],
                        help='Action to perform')
    parser.add_argument('--file', help='Backup filename for restore')

    args = parser.parse_args()

    if args.action == 'backup':
        backup()
    elif args.action == 'restore':
        if not args.file:
            list_backups()
            print('\nUsage: python backup.py restore --file <filename>')
        else:
            restore(args.file)
    elif args.action == 'list':
        list_backups()
