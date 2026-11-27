"""Fixtures and helpers of the database tests (issues #8, #9, #11, #12).

Not in a conftest.py: tests/conftest.py is imported by name (`from conftest import ...`) by the
ingestion tests, and a second conftest.py would shadow it. Each test module imports the
fixtures it uses from here (`from db_helpers import conn`).

They need a PostgreSQL + PostGIS server. Give an admin connection in TEST_DATABASE_URL, e.g. with Docker:

    $env:TEST_DATABASE_URL = "postgresql://deserveat:<password>@localhost:5432/postgres"   # PowerShell
    export TEST_DATABASE_URL=postgresql://deserveat:<password>@localhost:5432/postgres     # bash
    pytest tests/database

Each test session creates a throw-away database (deserveat_test), runs files/01_ddl.sql in it and drops it
at the end: the real warehouse is never touched. Without TEST_DATABASE_URL (or without psycopg2) these tests
are skipped, so `pytest tests` still works on a machine without a database.
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DDL = PROJECT_ROOT / "files" / "01_ddl.sql"
SAMPLE_DATA = PROJECT_ROOT / "files" / "02_sample_data.sql"
TEST_DB = "deserveat_test"
ADMIN_URL = os.environ.get("TEST_DATABASE_URL")

sys.path.insert(0, str(PROJECT_ROOT / "src" / "loading"))


def scratch_db_url():
    """ADMIN_URL with the database name replaced by TEST_DB."""
    base, _, _ = ADMIN_URL.rpartition("/")
    return f"{base}/{TEST_DB}"


def run_sql_file(conn, path):
    with conn.cursor() as cur:
        cur.execute(Path(path).read_text(encoding="utf-8"))
    conn.commit()


def scalar(conn, query, params=None):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()[0]


def _admin_execute(statement):
    import psycopg2
    conn = psycopg2.connect(ADMIN_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(statement)
    finally:
        conn.close()


@pytest.fixture(scope="session")
def db_url():
    if not ADMIN_URL:
        pytest.skip("TEST_DATABASE_URL not set: database tests skipped")
    psycopg2 = pytest.importorskip("psycopg2")
    from psycopg2 import sql
    drop = sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(TEST_DB))
    _admin_execute(drop)
    _admin_execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB)))
    conn = psycopg2.connect(scratch_db_url())
    try:
        run_sql_file(conn, DDL)
    finally:
        conn.close()
    yield scratch_db_url()
    _admin_execute(drop)


@pytest.fixture
def conn(db_url):
    """A connection to the test database; uncommitted work is rolled back after the test."""
    import psycopg2
    connection = psycopg2.connect(db_url)
    yield connection
    connection.rollback()
    connection.close()
