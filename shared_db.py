"""
shared_db.py — единая база данных для main.py и TGbot.py

Использует SQLite (без сервера, файл oylan.db рядом с проектом).
Оба файла импортируют TenderDB и работают с одними данными.

Замени на PostgreSQL в продакшене — только поменяй движок SQLAlchemy.
"""

import sqlite3
import json
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "oylan.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


class TenderDB:
    """
    Единый класс для работы с БД.
    Используется в main.py (FastAPI) и TGbot.py одновременно.
    """

    def __init__(self):
        self._init_tables()

    def _init_tables(self):
        with get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tenders (
                    id          TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    price       REAL,
                    region      TEXT,
                    district    TEXT,
                    keyword     TEXT,
                    status      TEXT DEFAULT 'active',
                    created_at  TEXT DEFAULT (datetime('now')),
                    url         TEXT
                );

                CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id             INTEGER PRIMARY KEY,
                    filters_json        TEXT NOT NULL DEFAULT '{}',
                    active              INTEGER NOT NULL DEFAULT 0,
                    last_notified_id    TEXT,
                    updated_at          TEXT DEFAULT (datetime('now'))
                );
            """)

    # ── ТЕНДЕРЫ ──────────────────────────────────────────

    def add_tender(self, tender: dict) -> bool:
        """Добавить тендер. Вызывается из main.py при получении данных."""
        try:
            with get_conn() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO tenders
                        (id, title, price, region, district, keyword, status, url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tender.get("id"),
                    tender.get("title"),
                    tender.get("price") or tender.get("amount"),
                    tender.get("region"),
                    tender.get("district"),
                    tender.get("keyword"),
                    tender.get("status", "active"),
                    tender.get("url"),
                ))
            return True
        except Exception as e:
            print(f"[DB] add_tender error: {e}")
            return False

    def search_tenders(self, filters: dict) -> list[dict]:
        """Поиск тендеров по фильтрам. Используется в боте и в /api/tenders/search."""
        conditions = ["1=1"]
        params = []

        if filters.get("region"):
            conditions.append("region = ?")
            params.append(filters["region"])

        if filters.get("district"):
            conditions.append("district = ?")
            params.append(filters["district"])

        if filters.get("price_min"):
            conditions.append("price >= ?")
            params.append(filters["price_min"])

        if filters.get("price_max"):
            conditions.append("price <= ?")
            params.append(filters["price_max"])

        if filters.get("keyword"):
            conditions.append("title LIKE ?")
            params.append(f"%{filters['keyword']}%")

        sql = f"""
            SELECT * FROM tenders
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT 50
        """
        with get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_all_tenders(self) -> list[dict]:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tenders ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_new_tenders(self, filters: dict, since_id: str | None) -> list[dict]:
        """
        Возвращает тендеры новее since_id, соответствующие фильтрам.
        Используется фоновым потоком уведомлений.
        """
        all_matched = self.search_tenders(filters)
        if not since_id:
            return all_matched

        new = []
        for t in all_matched:
            if t["id"] == since_id:
                break
            new.append(t)
        return new

    # ── ПОДПИСКИ ─────────────────────────────────────────

    def save_subscription(self, user_id: int, filters: dict, active: bool):
        """Сохранить/обновить подписку пользователя."""
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO subscriptions (user_id, filters_json, active, updated_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    filters_json = excluded.filters_json,
                    active       = excluded.active,
                    updated_at   = excluded.updated_at
            """, (user_id, json.dumps(filters, ensure_ascii=False), int(active)))

    def get_subscription(self, user_id: int) -> dict | None:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "user_id":          row["user_id"],
            "filters":          json.loads(row["filters_json"]),
            "active":           bool(row["active"]),
            "last_notified_id": row["last_notified_id"],
        }

    def get_all_active_subscriptions(self) -> list[dict]:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM subscriptions WHERE active = 1"
            ).fetchall()
        return [
            {
                "user_id":          r["user_id"],
                "filters":          json.loads(r["filters_json"]),
                "active":           bool(r["active"]),
                "last_notified_id": r["last_notified_id"],
            }
            for r in rows
        ]

    def update_last_notified(self, user_id: int, tender_id: str):
        with get_conn() as conn:
            conn.execute(
                "UPDATE subscriptions SET last_notified_id = ? WHERE user_id = ?",
                (tender_id, user_id)
            )