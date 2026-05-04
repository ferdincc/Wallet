"""
User model
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float
from sqlalchemy.types import TypeDecorator, String as SAString
from sqlalchemy.sql import func
import enum
from app.database import Base


class RiskAppetite(str, enum.Enum):
    """Risk appetite levels"""
    CONSERVATIVE = "conservative"  # Muhafazakar - %80+ güven skoru gerekir
    MODERATE = "moderate"  # Orta - %65+ güven skoru gerekir
    AGGRESSIVE = "aggressive"  # Agresif - %60+ güven skoru yeterli


class RiskAppetiteColumn(TypeDecorator):
    """
    SQLite / metin kolonunda 'moderate', 'MODERATE', 'medium' vb. tüm varyantları
    RiskAppetite enumuna güvenli şekilde çevirir (Pydantic uyumu).
    """
    impl = SAString(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, RiskAppetite):
            return value.value
        s = str(value).strip().lower()
        if s == "medium":
            return RiskAppetite.MODERATE.value
        if s in ("conservative", "moderate", "aggressive"):
            return s
        up = str(value).strip().upper()
        if up in RiskAppetite.__members__:
            return RiskAppetite[up].value
        return RiskAppetite.MODERATE.value

    def process_result_value(self, value, dialect):
        if value is None or (isinstance(value, str) and not value.strip()):
            return RiskAppetite.MODERATE
        s = str(value).strip()
        low = s.lower()
        if low == "medium":
            return RiskAppetite.MODERATE
        if low in ("conservative", "moderate", "aggressive"):
            return RiskAppetite(low)
        up = s.upper()
        if up in RiskAppetite.__members__:
            return RiskAppetite[up]
        return RiskAppetite.MODERATE


class User(Base):
    """User model for simulation portfolios"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    risk_appetite = Column(RiskAppetiteColumn(), nullable=False, default=RiskAppetite.MODERATE)
    min_confidence_threshold = Column(Float, nullable=False, default=0.65)  # Minimum confidence for trades
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        ra = self.risk_appetite.value if isinstance(self.risk_appetite, RiskAppetite) else self.risk_appetite
        return f"<User(username='{self.username}', risk_appetite='{ra}')>"

