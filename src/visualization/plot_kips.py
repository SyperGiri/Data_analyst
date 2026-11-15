"""
Визуализация ключевых показателей витрины mart_okrug_sla через Matplotlib.

Генерирует два графика:
1. Столбчатая диаграмма доли просроченных заявок по округам.
2. Комбинированный график: столбцы (кол-во заявок) + линия (среднее время ответа).

Графики сохраняются в reports/*.png (папка в .gitignore).
"""

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # без GUI-окна — важно для headless/CI
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import text

from src.models.database import engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Русские шрифты для matplotlib (иначе кириллица превратится в квадратики)
plt.rcParams["font.family"] = ["DejaVu Sans"]


def load_mart() -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text("SELECT * FROM mart_okrug_sla"), conn)
    # Убираем служебный 'Не указан' из графика (нет округов у транспорта)
    df = df[df.okrug_name != "Не указан"].copy()
    return df.sort_values("overdue_rate_pct", ascending=False)


def plot_overdue_rate(df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = [
        "#d62728" if v >= 20 else "#ff9f1c" if v >= 10 else "#2ca02c"
        for v in df["overdue_rate_pct"]
    ]
    bars = ax.bar(df["okrug_name"], df["overdue_rate_pct"], color=colors)

    for bar, val in zip(bars, df["overdue_rate_pct"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val + 0.3,
            f"{val:.1f}%",
            ha="center", va="bottom", fontsize=10, fontweight="bold",
        )

    ax.set_title(
        "Сравнительная статистика превышения регламентного срока в разрезе округов",
        fontsize=14, pad=15,
    )
    ax.set_xlabel("Округ")
    ax.set_ylabel("Доля просроченных ответов, %")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    out = REPORTS_DIR / "overdue_rate_by_okrug.png"
    plt.savefig(out, dpi=150)
    plt.close(fig)
    logger.info(f"📊 График сохранён: {out}")


def plot_volume_vs_speed(df: pd.DataFrame):
    fig, ax1 = plt.subplots(figsize=(12, 6))

    ax1.bar(df["okrug_name"], df["total_requests"],
            color="#4c72b0", alpha=0.7, label="Всего заявок")
    ax1.set_ylabel("Количество заявок", color="#4c72b0")
    ax1.set_title("Объём заявок и среднее время ответа по округам",
                  fontsize=14, pad=15)

    ax2 = ax1.twinx()
    ax2.plot(df["okrug_name"], df["avg_response_days"],
             color="#dd8452", marker="o", linewidth=2,
             label="Среднее время ответа, дней")
    ax2.set_ylabel("Среднее время ответа, дней", color="#dd8452")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right")

    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    out = REPORTS_DIR / "volume_vs_speed.png"
    plt.savefig(out, dpi=150)
    plt.close(fig)
    logger.info(f"📊 График сохранён: {out}")


if __name__ == "__main__":
    df = load_mart()
    logger.info(f"Данные витрины загружены: {len(df)} округов")
    plot_overdue_rate(df)
    plot_volume_vs_speed(df)
    logger.info("🎉 Визуализация готова!")