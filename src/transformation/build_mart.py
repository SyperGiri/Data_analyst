"""Построение аналитической витрины mart_okrug_sla."""

import logging
from sqlalchemy import text
from src.models.database import engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MART_SQL = """
CREATE TABLE mart_okrug_sla AS
WITH normalized AS (
    SELECT
        COALESCE(o.name, 'Не указан') AS okrug_name,
        r.message_id,
        r.pub_date,
        r.sla_date,
        resp.response_date,
        CASE WHEN resp.response_date IS NOT NULL THEN 1 ELSE 0 END AS is_answered,
        CASE
            -- Просрочка: ответа нет И SLA истёк (используем текущую дату как контрольную)
            WHEN resp.response_date IS NULL
                 AND r.sla_date IS NOT NULL
                 AND r.sla_date < CURRENT_DATE THEN 1
            -- Или ответ пришёл позже SLA
            WHEN resp.response_date IS NOT NULL
                 AND r.sla_date IS NOT NULL
                 AND resp.response_date > r.sla_date THEN 1
            ELSE 0
        END AS is_overdue,
        CASE
            WHEN resp.response_date IS NOT NULL
                THEN CAST(julianday(resp.response_date) - julianday(r.pub_date) AS REAL)
            ELSE NULL
        END AS response_days
    FROM fact_request r
    LEFT JOIN fact_response resp ON resp.message_id = r.message_id
    LEFT JOIN dim_raion d ON d.id = r.district_id
    LEFT JOIN dim_okrug o ON o.id = d.okrug_id
)
SELECT
    okrug_name,
    COUNT(*)                                    AS total_requests,
    SUM(is_answered)                            AS answered_requests,
    SUM(is_overdue)                             AS overdue_count,
    ROUND(100.0 * SUM(is_overdue) / NULLIF(COUNT(*), 0), 2) AS overdue_rate_pct,
    ROUND(AVG(response_days), 2)                AS avg_response_days
FROM normalized
GROUP BY okrug_name
ORDER BY overdue_rate_pct DESC;
"""


def build_mart():
    logger.info("🏗️  Построение витрины mart_okrug_sla...")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS mart_okrug_sla"))
        conn.execute(text(MART_SQL))
        count = conn.execute(
            text("SELECT COUNT(*) FROM mart_okrug_sla")
        ).scalar()
    logger.info(f"✅ Витрина построена: {count} округов.")


if __name__ == "__main__":
    build_mart()