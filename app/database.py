"""
Database connection and helper utilities.
Uses PyMySQL with connection pooling via a simple per-request pattern.
"""

import pymysql
import pymysql.cursors
from flask import current_app, g


def get_db():
    """Return a MySQL connection stored in Flask's app context `g`."""
    if 'db' not in g:
        cfg = current_app.config

        g.db = pymysql.connect(
            host=cfg['MYSQL_HOST'],
            port=cfg['MYSQL_PORT'],
            user=cfg['MYSQL_USER'],
            password=cfg['MYSQL_PASSWORD'],
            database=cfg['MYSQL_DB'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    return g.db


def close_db(error=None):
    """Close the DB connection at the end of each request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def query_db(sql, args=(), one=False):
    """
    Execute a SELECT query and return results.

    :param sql:  Parameterized SQL string (use %s placeholders)
    :param args: Tuple of arguments
    :param one:  If True, return a single row dict; else return list of dicts
    """
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql, args)
        result = cur.fetchall()
    return (result[0] if result else None) if one else result


def execute_db(sql, args=()):
    """
    Execute an INSERT / UPDATE / DELETE statement.

    :returns: lastrowid (for INSERTs) or rowcount
    """
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    except Exception as exc:
        conn.rollback()
        raise exc


def init_app(app):
    """Register teardown so the DB connection is closed after each request."""
    app.teardown_appcontext(close_db)
