# Архитектура ETL-проекта «Наш город»

## 1. Обзор системы

Проект реализует ETL-пайплайн обработки данных портала «Наш город» (gorod.mos.ru).
Исходные данные — два XLSX-файла с заявками граждан и ответами ведомств за февраль 2019 г.

**Технологический стек:**
- Python 3.10 + Pandas (извлечение и трансформация)
- Pydantic V2 (валидация схем данных)
- SQLAlchemy 2.0 + SQLite (хранение нормализованных сущностей)
- Matplotlib (визуализация KPI)
- python-pptx (генерация презентации)

## 2. Структура проекта
Data_analyst/
|----src/
|     |----models/ # Схема данных (Pydantic + QLAlchemy ORM)
|     |----schemas.py # Pydantic модели для валидации
|     |----database.py # ORM модели и движок SQLite
|     |----etl/
|     |     |----run_pipeline.pу # Основной ETL скрипт
|     |----transformation/
|     |     |----build_mart.py # Построение витрины mart_okrug_sla
|     |----visualization/
|     |----plot_kpis.py # Matplotlib графики
|     |----create_pptx.py # Генерация PPTX презентации
|----data/ # Сырые XLSX файлы (в .gitignore)
|----reports/ # Артифакты: PNG, PPTX (в .gitignore)
|----docs/ # Документация (этот файл + ADR + SCALING)
|----tests/ # Юнит-тесты Pydantic схем
|----requirements.txt
|----README.md


## 3. Схема базы данных (3НФ)

```mermaid
erDiagram
    dim_okrug ||--o{ dim_raion : "содержит районы"
    dim_category ||--o{ dim_topic : "содержит темы"
    dim_raion ||--o{ fact_request : " FK district_id"
    dim_topic ||--o{ fact_request : " FK topic_id"
    fact_request ||--o| fact_response : "message_id (1:0..1)"

    dim_okrug {
        int id PK
        string name "ЦАО, САО, ... НАО, ТАО"
    }
    dim_raion {
        int id PK
        int okrug_id FK
        string name
    }
    dim_…}
    dim_topic {
        int id PK
        int category_id FK
        string name
    }
    fact_request {
        int id PK
        int message_id UK "бизнес-ключ из источника"
        int request_number
        string object_address
        date pub_date
        date sla_date
        string status
        int district_id FK
        int topic_id FK
    }
    fact_response {
        int id PK
        int message_id FK "связь с заявкой"
        int request_number
        date response_date
    }

Ключевые решения:
- каталоги (dim_*) хранят текстовые атрибуты по одному разу это устраняет аномалии обновления и вставки.
- Факты (fact_*) содержат только FK и бизнес-метрики - это позволяет быстро агрегировать данные.
- message_id уникальный бизнес-ключ из источника. Используется для идемпотентной загрузки ( ON CONFLICT DO UPDATE).
- object_address оставлял текстом в факте нормализации адресов (геокодирование) выходит за рамки задач

## 4. ETL-пайплайн: этапы
XLSX файлы --> Pandas: чтение --> Pydantic: валидация --> Нормализация округов --> SQLite: UPSERT --> SQL: витрина mart_okrug_sla --> Matplotlib: графики --> PPTX: презентация

### 4.1 Извлечение (Extract)

- pd.read_excel() читает оба XLSX-файла.
- Колонки переименовываются через маппинг REQUESTS_COL_MAP / RESPONSES_COL_MAP (Русские → английские имена полей Pydantic).

### 4.2 Валидация (Validate)

- Каждая строка проходит через RawRequest.model_validate()/RawResponse.model_validate()
- Парсер дат _parse_date() принимает str («04.02.2019»), datetime, pandas.Timestamp и None.
- Enum ResponseStatus отбрасывает строки с неизвестным статусом.
- Невалидные строки логируются, но не попадают в БД.

### 4.3 Трансформация (Transform)

- Нормализация округов: Функция normalize_okrug() приводит все варианты написания («Юго-Западный округ», «ЮЗАО») к канонической аббревиатуре. Это устранило дублирование справочника (21 → 12 записей).
- Справочники создаются через get_or_create() - если запись уже есть, возвращается ее ID; иначе создаётся новая.
- Факты загружаются через sqlite_insert().on_conflict_do_update(index_elements=["message_id"], ...) - это гарантирует идемпотентность: повторный запуск пайплайна не создаст дубликатов.

### 4.4 Загрузка (Load)
- SQLite-файл mos_gov.db загружается автоматически при первом запуске.
- Таблицы создаются через Base.metadata.create_all(engine).

## 5. Витрина данных mart_okrug_sla

Витрина агрегирует нормализованные сущности в широкую таблицу для ВІ-слоя.

SQL-запрос (полный текст в src/transformation/build_mart.py):
WITH normalized AS (
    SELECT
        COALESCE(o.name, 'Не указан') AS okrug_name,
        r.message_id, r.pub_date, r.sla_date, resp.response_date,
        CASE WHEN resp.response_date IS NOT NULL THEN 1 ELSE 0 END AS is_answered,
        CASE
            WHEN resp.response_date IS NOT NULL AND r.sla_date IS NOT NULL
                 AND resp.response_date > r.sla_date THEN 1
            WHEN resp.response_date IS NULL AND r.sla_date IS NOT NULL
                 AND r.sla_date < CURRENT_DATE THEN 1
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
    COUNT(*) AS total_requests,
    SUM(is_answered) AS answered_requests,
    SUM(is_overdue) AS overdue_count,
    ROUND(100.0 * SUM(is_overdue) / NULLIF(COUNT(*), 0), 2) AS overdue_rate_pct,
    ROUND(AVG(response_days), 2) AS avg_response_days
FROM normalized
GROUP BY okrug_name
ORDER BY overdue_rate_pct DESC;

### 5.1 Бизнес-правила расчёта показателей

Показатель          Формула                                 База
total_requests      COUNT(*)                                Все заявки округа
answered_requests   SUM(is_answered)                        Все заявки округа
overdue_count       SUM(is_overdue)                         Все заявки округа
overdue_rate_pct    100 x overdue_count / total_requests    Все заявки округа
avg_response_days   AVG(response_days)                      Только отвеченные заявки

Определение просрочки (is_overdue = 1):
1. Есть ответ, но он пришёл позже протоколного срока (response_date > sla_date ), ИЛИ
2. Ответа нет, а протоколный срок истёк относительно текущей даты (sla_date < CURRENT_DATE).

Заявки с sla_date IS NULL (общественный транспорт) не считаются просроченными — у них нет регламента.

##6. Визуализация

### 6.1 График overdue_rate_by_okrug.png

Столбчатая диаграмма доли просроченных заявок по округам. Цветовая кодировка:
- Красный (≥50%) — максимальный уровень
- Оранжевый (30-50%) - повышенный уровень
- Зелёный (<30%) — приемлемый уровень

### 6.2 График volume_vs_speed.png

Комбинированный график: столбцы (всего заявок) + линия (среднее время ответа, дней). Две оси Y для разных масштабов.

### 6.3 Презентация prezentation.pptx

Слайд 1 - титульный. Слайд 2 - график overdue_rate_by_okrug.png под заголовком «Сравнительная статистика превышения регламентного срока в разрезе округов».

## 7. Идемпотентность

Пайплайн можно запускать многократно без риска дублирования данных:
- Справочники: get_or_create() проверяет уникальность по name (или (okrug_id, name) для районов).
- Факты: ON CONFLICT DO UPDATE по message_id - если запись уже есть, она обновляется иначе вставляется.
- Витрина: DROP TABLE IF EXISTS + CREATE TABLE AS - пересоздается с нуля при каждом запуске.

## 8. Запуск

1. Установка зависимостей
pip install -r requirements.txt
2. Запуск ETL
python -m src.etl.run_pipeline
3. Построение витрины
python -m src.transformation.build_mart
4. Визуализация
python -m src.visualization.plot_kpis
python -m src.visualization.create_pptx
5. Тесты
pytest -v

