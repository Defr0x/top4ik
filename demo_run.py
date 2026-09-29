"""
Демо-режим NeuroAPI без MySQL.

Хостеры шаред-хостинга часто закрывают внешние подключения к MySQL,
поэтому для локальной проверки/превью проще поднять весь сайт на
локальной SQLite-базе — код приложения тот же самый, меняется только
подключение к БД.

Запуск:
    python demo_run.py
"""

import os
import re
import sqlite3

import mysql.connector

DEMO_DB = os.environ.get("DEMO_DB", "/tmp/neuroapi_demo.db")

CREATE_USERS_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    balance REAL NOT NULL DEFAULT 0
)
"""

CREATE_KEYS_SQLITE = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product VARCHAR(50) NOT NULL,
    api_key VARCHAR(80) NOT NULL UNIQUE,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


class DemoCursor:
    """Обертка над sqlite-курсором, имитирующая mysql-connector."""

    def __init__(self, cur, dictionary=False):
        self._cur = cur
        self._dict = dictionary
        self.lastrowid = None

    def execute(self, sql, params=()):
        if re.match(r"\s*CREATE TABLE IF NOT EXISTS `?api_keys`?", sql, re.I):
            sql = CREATE_KEYS_SQLITE
        sql = re.sub(r"%s", "?", sql.replace("`", ""))
        try:
            self._cur.execute(sql, params or ())
        except sqlite3.IntegrityError as e:
            # Пробрасываем как ошибку MySQL — код приложения ловит именно её
            raise mysql.connector.IntegrityError(str(e))
        self.lastrowid = self._cur.lastrowid

    def _convert(self, row):
        if row is None or not self._dict:
            return row
        cols = [d[0] for d in self._cur.description]
        return dict(zip(cols, row))

    def fetchone(self):
        return self._convert(self._cur.fetchone())

    def fetchall(self):
        return [self._convert(r) for r in self._cur.fetchall()]

    @property
    def rowcount(self):
        return self._cur.rowcount

    def close(self):
        self._cur.close()


class DemoConnection:
    def __init__(self):
        self._c = sqlite3.connect(DEMO_DB, check_same_thread=False, timeout=10)

    def cursor(self, dictionary=False, buffered=False):
        return DemoCursor(self._c.cursor(), dictionary=dictionary)

    def commit(self):
        self._c.commit()

    def rollback(self):
        self._c.rollback()

    def close(self):
        self._c.close()

    def is_connected(self):
        return True


def demo_connect(*args, **kwargs):
    return DemoConnection()


def main():
    # Подменяем подключение к MySQL на локальную SQLite до старта приложения
    mysql.connector.connect = demo_connect

    with closing_connection() as conn:
        cur = conn.cursor()
        cur.execute(CREATE_USERS_SQLITE)
        cur.execute(CREATE_KEYS_SQLITE)
        conn.commit()

    # Фиктивные значения, чтобы приложение не ругалось на пустой конфиг
    os.environ.setdefault("DB_HOST", "demo")
    os.environ.setdefault("DB_NAME", "demo")
    os.environ.setdefault("DB_USER", "demo")
    os.environ.setdefault("DB_PASSWORD", "demo")
    os.environ.setdefault("SECRET_KEY", "demo-secret-key")
    os.environ.setdefault("HOST", "127.0.0.1")
    os.environ.setdefault("PORT", "5000")

    from app import run

    print(f"[DEMO] NeuroAPI работает на локальной базе {DEMO_DB} (MySQL не используется)")
    run()


def closing_connection():
    conn = DemoConnection()

    class _Ctx:
        def __enter__(self):
            return conn

        def __exit__(self, *exc):
            conn.close()

    return _Ctx()


if __name__ == "__main__":
    main()
