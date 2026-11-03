"""
Import a codespeed SQLite snapshot into the running database.

Rows that already exist (by primary key or unique constraint) are silently
skipped, so the command is safe to re-run and merges cleanly into existing
data.

Usage:
    python manage.py import_sqlite_dump codespeed-YYYY-MM-DD.sqlite3
"""
import sqlite3
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

# Columns that are stored as 0/1 integers in SQLite but need Python bools
# for PostgreSQL's boolean type.
_BOOL_COLS = {
    'codespeed_project':   {'track'},
    'codespeed_branch':    {'display_on_comparison_page'},
    'codespeed_benchmark': {'lessisbetter', 'default_on_comparison'},
}

# Columns stored as ISO strings in SQLite that must become datetime objects
# for PostgreSQL's timestamp type.
_DT_COLS = {
    'codespeed_revision': {'date'},
    'codespeed_result':   {'date'},
}

# Insertion order respects FK dependencies.
_TABLES = [
    'codespeed_project',
    'codespeed_branch',
    'codespeed_executable',
    'codespeed_environment',
    'codespeed_benchmark',
    'codespeed_revision',
    'codespeed_result',
]


def _adapt(value, col, bool_cols, dt_cols):
    if value is None:
        return None
    if col in bool_cols:
        return bool(value)
    if col in dt_cols and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


class Command(BaseCommand):
    help = 'Import a SQLite snapshot into the running PostgreSQL database'

    def add_arguments(self, parser):
        parser.add_argument('sqlite_file', help='Path to the SQLite dump file')

    def handle(self, *args, **options):
        sqlite_file = options['sqlite_file']
        try:
            src = sqlite3.connect(sqlite_file)
        except Exception as e:
            raise CommandError(f'Cannot open {sqlite_file}: {e}')

        src.row_factory = sqlite3.Row

        with transaction.atomic(), connection.cursor() as cur:
            for table in _TABLES:
                bool_cols = _BOOL_COLS.get(table, set())
                dt_cols = _DT_COLS.get(table, set())

                rows = src.execute(f'SELECT * FROM {table}').fetchall()
                if not rows:
                    self.stdout.write(f'  {table}: 0 rows')
                    continue

                cols = list(rows[0].keys())
                col_list = ', '.join(cols)
                placeholders = ', '.join(['%s'] * len(cols))
                sql = (
                    f'INSERT INTO {table} ({col_list}) '
                    f'VALUES ({placeholders}) '
                    f'ON CONFLICT DO NOTHING'
                )
                data = [
                    tuple(_adapt(row[c], c, bool_cols, dt_cols) for c in cols)
                    for row in rows
                ]
                cur.executemany(sql, data)
                self.stdout.write(f'  {table}: {len(data)} rows')

        src.close()
        self.stdout.write(self.style.SUCCESS('Import complete'))
