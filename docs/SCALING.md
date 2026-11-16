# Масштабирование архитектуры

Этот документ описывает, как модифицировать текущую архитектуру при увеличении объёма данных до нескольких миллионов строк.

## 1. Текущие ограничения

| Компонент | Текущее состояние | Ограничение при росте |
|---|---|---|
| **СУБД** | SQLite (файловая) | Нет конкурентной записи, нет партиционирования, нет репликации |
| **ETL** | Pandas (in-memory) | Требует RAM = размер данных × 3–5 (для дубликатов при операциях) |
| **Витрина** | Пересоздаётся с нуля (`DROP + CREATE`) | При 10M строк — минуты вместо секунд |
| **Валидация** | Pydantic (построчно в цикле) | Медленно на больших DataFrame |
| **Оркестрация** | Ручной запуск скриптов | Нет расписания, нет мониторинга, нет retry |

## 2. План масштабирования

### 2.1 Переход на PostgreSQL (вместо SQLite)

**Когда:** >1M строк, нужна конкурентная запись, репликация, бэкапы.

**Изменения:**
- Заменить `create_engine("sqlite:///mos_gov.db")` на `create_engine("postgresql://user:pass@host:5432/db")`.
- Добавить индексы на FK (`district_id`, `topic_id`, `message_id`) — PostgreSQL использует B-tree индексы для ускорения `JOIN`.
- Включить `VACUUM ANALYZE` после массовых загрузок — обновляет статистику для оптимизатора запросов.

**Преимущества:**
- Партиционирование таблиц (например, по `pub_date` — по месяцам).
- Параллельное выполнение запросов (PostgreSQL 11+).
- Репликация для чтения (read replicas) — разгрузка основного сервера.

### 2.2 Колоночная СУБД для аналитики (ClickHouse / Greenplum)

**Когда:** >10M строк, нужны сложные агрегации, дашборды в реальном времени.

**Архитектура:**
[Источники] → [Airflow/Dagster] → [PostgreSQL (OLTP)] → [Airflow] → [ClickHouse (OLAP)] → [Superset]


**Обоснование:**
- **PostgreSQL** хранит нормализованные сущности (OLTP) — быстрые `INSERT/UPDATE`, транзакции.
- **ClickHouse** хранит витрины (OLAP) — быстрые `GROUP BY`, агрегации по миллионам строк за миллисекунды.
- **ETL между ними:** Airflow-даг переливает данные из PostgreSQL в ClickHouse через `COPY` или JDBC.

**Пример витрины в ClickHouse:**
```sql
CREATE TABLE mart_okrug_sla (
    okrug_name String,
    pub_date Date,
    total_requests UInt32,
    overdue_count UInt32,
    overdue_rate_pct Float32
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(pub_date)
ORDER BY (okrug_name, pub_date);

### 2.3 Пратиционирование таблиц

Когда :> 5М строк в fact_request, нужны быстрые запросы по диапазонам дат.
Решение:
CREATE TABLE fact_request (
    id SERIAL,
    message_id INT,
    pub_date DATE,
    ...
) PARTITION BY RANGE (pub_date);

CREATE TABLE fact_request_2019_q1 PARTITION OF fact_request
    FOR VALUES FROM ('2019-01-01') TO ('2019-04-01');

CREATE TABLE fact_request_2019_q2 PARTITION OF fact_request
    FOR VALUES FROM ('2019-04-01') TO ('2019-07-01');

Преимущества:
- Запросы с фильтром WHERE pub_date BETWEEN ... сканируют только нужные партии (partition pruning).
- Старые партии можно архивировать или удалять без блокировки всей таблицы.

### 2.4 Кэширование витрин

Когда: Дашборд Superset запрашивает одну и ту же витрину сотни раз в день.
Решение:
- Redis для кэширования результатов SQL-запросов (TTL = 1 час).
- Materialized Views - витрина пересчитывается по расписанию (например, раз в час), а запросы идут к материализованному представлению.

CREATE MATERIALIZED VIEW mart_okrug_sla_mv AS
SELECT ... FROM fact_request ...;

-- Обновление по расписанию (через pg_cron или Airflow)
REFRESH MATERIALIZED VIEW CONCURRENTLY mart_okrug_sla_mv;

## 2.5 Очереди для асинхронной обработки

Когда: ETL-пайплайн обрабатывает данные дольше, чем интервал между запусками (например, загрузка занимает 2 часа, а данные приходят клиентам 30 минут).
Решение:
- Apache Kafka или RabbitMQ - источник данных публикует сообщения в очередь.
- Celery или Airflow  - воркеры читают из очереди и обрабатывают параллельно.

Архитектура:
[gorod.mos.ru] → [Kafka topic: raw_requests] → [Celery workers] → [PostgreSQL]

