from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resume_text: Mapped[str] = mapped_column(Text)
    job_description_text: Mapped[str] = mapped_column(Text)
    extracted_keywords: Mapped[dict] = mapped_column(JSONB)
    match_score: Mapped[int] = mapped_column(Integer)
    result_payload: Mapped[dict] = mapped_column(JSONB)


class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    company_name: Mapped[str] = mapped_column(Text)
    role_title: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(Text)
    generated_text: Mapped[str] = mapped_column(Text)
