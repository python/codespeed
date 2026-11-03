import os
import sqlite3
import tempfile
from datetime import datetime, date

from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse

from django.db import connection

SIZE_LIMIT = 95 * 1024 * 1024  # 95 MB

# Schema for the exported SQLite file, in FK-safe creation order.
# Column names must match Django's generated PostgreSQL column names exactly.
_SCHEMA = """
PRAGMA foreign_keys = OFF;

CREATE TABLE codespeed_project (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    repo_type TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    repo_user TEXT NOT NULL,
    repo_pass TEXT NOT NULL,
    commit_browsing_url TEXT NOT NULL,
    track INTEGER NOT NULL,
    default_branch TEXT NOT NULL
);

CREATE TABLE codespeed_branch (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    project_id INTEGER NOT NULL,
    display_on_comparison_page INTEGER NOT NULL
);

CREATE TABLE codespeed_executable (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    project_id INTEGER NOT NULL
);

CREATE TABLE codespeed_environment (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    cpu TEXT NOT NULL,
    memory TEXT NOT NULL,
    os TEXT NOT NULL,
    kernel TEXT NOT NULL
);

CREATE TABLE codespeed_benchmark (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER,
    source TEXT NOT NULL,
    data_type TEXT NOT NULL,
    description TEXT NOT NULL,
    units_title TEXT NOT NULL,
    units TEXT NOT NULL,
    lessisbetter INTEGER NOT NULL,
    default_on_comparison INTEGER NOT NULL
);

CREATE TABLE codespeed_revision (
    id INTEGER PRIMARY KEY,
    commitid TEXT NOT NULL,
    tag TEXT NOT NULL,
    date TEXT,
    message TEXT NOT NULL,
    project_id INTEGER,
    author TEXT NOT NULL,
    branch_id INTEGER NOT NULL
);

CREATE TABLE codespeed_result (
    id INTEGER PRIMARY KEY,
    value REAL NOT NULL,
    std_dev REAL,
    val_min REAL,
    val_max REAL,
    q1 REAL,
    q3 REAL,
    suite_version TEXT NOT NULL,
    date TEXT,
    revision_id INTEGER NOT NULL,
    executable_id INTEGER NOT NULL,
    benchmark_id INTEGER NOT NULL,
    environment_id INTEGER NOT NULL
);
"""

_SMALL_TABLES = [
    'codespeed_project',
    'codespeed_branch',
    'codespeed_executable',
    'codespeed_environment',
    'codespeed_benchmark',
    'codespeed_revision',
]


def _conv(v):
    """Convert PostgreSQL Python types to SQLite-safe scalars."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _build_sqlite(path):
    lite = sqlite3.connect(path)
    try:
        lite.executescript(_SCHEMA)
        lite.commit()

        with connection.cursor() as pg:
            for table in _SMALL_TABLES:
                pg.execute(f'SELECT * FROM {table}')
                cols = [d[0] for d in pg.description]
                rows = [tuple(_conv(v) for v in row) for row in pg.fetchall()]
                if rows:
                    ph = ', '.join(['?'] * len(cols))
                    lite.executemany(
                        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({ph})",
                        rows,
                    )
            lite.commit()

            # Result table: newest-first, stop at size cap
            pg.execute(
                'SELECT * FROM codespeed_result ORDER BY date DESC NULLS LAST'
            )
            cols = [d[0] for d in pg.description]
            ph = ', '.join(['?'] * len(cols))
            insert_sql = (
                f"INSERT INTO codespeed_result ({', '.join(cols)}) VALUES ({ph})"
            )
            while True:
                batch = pg.fetchmany(5000)
                if not batch:
                    break
                lite.executemany(
                    insert_sql,
                    [tuple(_conv(v) for v in row) for row in batch],
                )
                lite.commit()
                if os.path.getsize(path) > SIZE_LIMIT:
                    break
    finally:
        lite.close()


@staff_member_required
def download_db(request):
    fd, path = tempfile.mkstemp(suffix='.sqlite3')
    os.close(fd)
    try:
        _build_sqlite(path)
        f = open(path, 'rb')
        today = datetime.today().strftime('%Y-%m-%d')
        response = FileResponse(
            f,
            as_attachment=True,
            filename=f'codespeed-{today}.sqlite3',
        )
        os.unlink(path)  # unlink after FileResponse reads the file size
        response.set_cookie(
            'codespeed_download_ready', '1',
            max_age=60, path='/', samesite='Lax',
        )
        return response
    except Exception:
        if os.path.exists(path):
            os.unlink(path)
        raise
