\# Data\_analyst — ETL-проект (тестовое задание)



Проект обработки данных портала «Наш город» (Москва).



\## Структура

\- src/extraction — чтение XLSX / web

\- src/transformation — очистка и обогащение (pandas)

\- src/loading — загрузка в SQLite

\- src/models — схемы (Pydantic) и ORM (SQLAlchemy)

\- src/visualization — графики (matplotlib)

\- dags — пайплайны оркестрации

\- notebooks — EDA и черновики

\- tests — unit-тесты

\- docs — документация и ADR

\- data — сырые файлы (в .gitignore)



\## Запуск

1\. python -m venv venv \&\& venv\\Scripts\\activate

2\. pip install -r requirements.txt

