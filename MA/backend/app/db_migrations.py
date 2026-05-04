"""
Mevcut veritabanları için hafif şema yamaları (Alembic yok).
Uygulama açılışında eksik kolonlar eklenir.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def ensure_users_risk_columns(engine: Engine) -> None:
    """
    users tablosunda risk_appetite ve min_confidence_threshold yoksa ekler.
    User modeli ile uyumlu: RiskAppetite.MODERATE -> 'moderate', eşik 0.65.
    """
    try:
        insp = inspect(engine)
        if not insp.has_table("users"):
            return
        existing = {c["name"] for c in insp.get_columns("users")}
    except Exception as e:
        logger.warning("users tablosu incelenemedi: %s", e)
        return

    patches: list[str] = []
    if "risk_appetite" not in existing:
        patches.append(
            "ALTER TABLE users ADD COLUMN risk_appetite VARCHAR(32) DEFAULT 'moderate'"
        )
    if "min_confidence_threshold" not in existing:
        patches.append(
            "ALTER TABLE users ADD COLUMN min_confidence_threshold FLOAT DEFAULT 0.65"
        )

    if not patches:
        return

    with engine.begin() as conn:
        for sql in patches:
            conn.execute(text(sql))
            logger.info("Şema yaması uygulandı: %s", sql)


def normalize_users_risk_appetite_values(engine: Engine) -> None:
    """Eski satırlarda MODERATE / MEDIUM gibi değerleri küçük harfli enum value'ya çeker."""
    try:
        insp = inspect(engine)
        if not insp.has_table("users"):
            return
        if "risk_appetite" not in {c["name"] for c in insp.get_columns("users")}:
            return
    except Exception as e:
        logger.warning("risk_appetite normalizasyonu atlandı: %s", e)
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE users SET risk_appetite = LOWER(TRIM(risk_appetite)) "
                "WHERE risk_appetite IS NOT NULL"
            )
        )
        conn.execute(
            text(
                "UPDATE users SET risk_appetite = 'moderate' "
                "WHERE risk_appetite IN ('medium', 'med', 'MEDIUM')"
            )
        )
        logger.info("users.risk_appetite değerleri normalize edildi")
