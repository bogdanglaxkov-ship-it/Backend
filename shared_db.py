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
                    url         TEXT,
                    country     TEXT DEFAULT 'KZ'
                );

                -- Добавляем колонку country если её нет (миграция для старых БД)
                CREATE TABLE IF NOT EXISTS _migration_done (id INTEGER PRIMARY KEY);
            """)
            # Миграция: добавляем country в существующую БД если колонки нет
            try:
                conn.execute("ALTER TABLE tenders ADD COLUMN country TEXT DEFAULT 'KZ'")
            except Exception:
                pass  # Колонка уже существует
            # Миграция: geo_checked отделяет "ещё не проверяли гео" от "проверили,
            # региона нет" (пустой region сам по себе не годится как маркер,
            # т.к. у российских тендеров region легитимно всегда пустой)
            try:
                conn.execute("ALTER TABLE tenders ADD COLUMN geo_checked INTEGER DEFAULT 0")
            except Exception:
                pass  # Колонка уже существует
            conn.executescript("""

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
        """Добавить/обновить тендер. Вызывается из main.py и из синка при получении данных.
        Upsert: при повторной синхронизации того же id подтягиваем исправленные/дозаполненные
        поля (например price), не затирая уже известные значения пустыми/отсутствующими.
        """
        price = tender.get("price")
        if price is None:
            price = tender.get("amount")
        try:
            with get_conn() as conn:
                conn.execute("""
                    INSERT INTO tenders
                        (id, title, price, region, district, keyword, status, url, country)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title    = excluded.title,
                        price    = COALESCE(excluded.price, tenders.price),
                        region   = CASE WHEN excluded.region   IS NOT NULL AND excluded.region   != '' THEN excluded.region   ELSE tenders.region   END,
                        district = CASE WHEN excluded.district IS NOT NULL AND excluded.district != '' THEN excluded.district ELSE tenders.district END,
                        status   = excluded.status,
                        url      = COALESCE(excluded.url, tenders.url)
                """, (
                    tender.get("id"),
                    tender.get("title"),
                    price,
                    tender.get("region"),
                    tender.get("district"),
                    tender.get("keyword"),
                    tender.get("status", "active"),
                    tender.get("url"),
                    tender.get("country", "KZ"),
                ))
            return True
        except Exception as e:
            print(f"[DB] add_tender error: {e}")
            return False

    def search_tenders(self, filters: dict) -> list[dict]:
        """Поиск тендеров по фильтрам. Используется в боте и в /api/tenders/search.
        Базово всегда фильтрует только Казахстан (country = 'KZ').
        """
        # Базовый фильтр — только КЗ тендеры
        conditions = ["(country = 'KZ' OR country IS NULL)"]
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
        """Тендеры для списка/аналитики. Свежесинканные записи почти всегда
        временно без региона (гео-обогащение идёт отдельным фоновым шагом) —
        сортировка "просто по дате" топит их наверху и вытесняет из LIMIT
        уже обогащённые тендеры с реальным регионом. Поэтому сначала отдаём
        те, у кого регион уже есть, а уже потом — самые свежие остальные.
        """
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tenders WHERE (country = 'KZ' OR country IS NULL) "
                "ORDER BY (region IS NOT NULL AND region != '') DESC, created_at DESC "
                "LIMIT 300"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_tenders_missing_region(self, limit: int = 80) -> list[str]:
        """ID тендеров, которые ещё не проверяли на реальный регион/страну.
        Пустой region НЕ значит "не проверяли" — у подтверждённых российских
        тендеров региона нет и не будет, поэтому маркером служит geo_checked.
        """
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT id FROM tenders WHERE geo_checked = 0 OR geo_checked IS NULL LIMIT ?",
                (limit,),
            ).fetchall()
        return [r["id"] for r in rows]

    def update_geo(self, tender_id: str, region: str, country: str) -> None:
        """Обновляет регион и фактическую страну тендера по данным полной модели
        и отмечает его как проверенный, чтобы enrich не гонял его повторно."""
        with get_conn() as conn:
            conn.execute(
                "UPDATE tenders SET region = ?, country = ?, geo_checked = 1 WHERE id = ?",
                (region, country, tender_id),
            )

    def get_tender_by_id(self, tender_id: str) -> dict | None:
        """Один тендер по id — для карточки деталей на сайте."""
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM tenders WHERE id = ?", (tender_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_tenders_by_district(self, district: str) -> list[dict]:
        """Тендеры конкретного района — для клика по карте в AnalyticsDashboard."""
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tenders WHERE district = ? AND (country = 'KZ' OR country IS NULL) "
                "ORDER BY created_at DESC",
                (district,)
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