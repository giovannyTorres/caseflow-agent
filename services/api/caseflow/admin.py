"""Local operator account provisioning; no public registration endpoint."""
import argparse
import getpass
import secrets
from .config import settings
from .db import connection, migrate, password_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('username')
    parser.add_argument('--role', choices=['analyst', 'supervisor'], required=True)
    args = parser.parse_args()
    password = getpass.getpass('New account password (12+ characters): ')
    if len(password) < 12:
        parser.error('Use at least 12 characters')
    migrate()
    salt = secrets.token_hex(16)
    with connection() as conn:
        conn.execute('INSERT INTO users(username,mode,role,salt,password_hash) VALUES(%s,%s,%s,%s,%s)',
                     (args.username, settings.mode, args.role, salt, password_hash(password, salt)))
    print(f'Created {settings.mode} account {args.username}')

if __name__ == '__main__':
    main()
