"""Генерация PPTX-презентации с ключевым графиком."""

import logging
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = BASE_DIR / "reports"
IMAGE_PATH = REPORTS_DIR / "overdue_rate_by_okrug.png"
PPTX_PATH = REPORTS_DIR / "presentation.pptx"

TITLE = "Сравнительная статистика превышения регламентного срока в разрезе округов"


def create_presentation():
    if not IMAGE_PATH.exists():
        raise FileNotFoundError(f"График не найден: {IMAGE_PATH}. Сначала запусти plot_kpis.py.")

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Слайд 1: титульный
    slide1 = prs.slides.add_slide(prs.slide_layouts[0])
    slide1.shapes.title.text = "Портал «Наш город»: SLA-аналитика"
    slide1.placeholders[1].text = "ETL-проект обработки данных заявок граждан\nТестовое задание — 2026"

    # Слайд 2: график
    slide2 = prs.slides.add_slide(prs.slide_layouts[5])
    slide2.shapes.title.text = TITLE
    slide2.shapes.title.text_frame.paragraphs[0].font.size = Pt(24)

    # ВАЖНО: добавляем картинку на СЛАЙД (slide2), а не на презентацию (prs)
    slide2.shapes.add_picture(
        str(IMAGE_PATH),
        Inches(0.8), Inches(1.4),
        width=Inches(11.7),
    )

    prs.save(PPTX_PATH)
    logger.info(f"📑 Презентация сохранена: {PPTX_PATH}")


if __name__ == "__main__":
    create_presentation()