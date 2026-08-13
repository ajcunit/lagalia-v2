"""Favorits (specs/favorites.md): carpetes personals + snapshot extern.

Els expedients externs viuen NOMÉS aquí: mai a `contracts` (02 §2.11
esmenat — distorsionarien la informació de l'ens).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.models import TimestampMixin


class FavoriteFolder(Base, TimestampMixin):
    __tablename__ = "favorite_folders"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    color: Mapped[str | None] = mapped_column(String(20))

    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="folder", cascade="all, delete-orphan"
    )


class Favorite(Base, TimestampMixin):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("folder_id", "file_code", name="uq_favorites_folder_code"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    folder_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("favorite_folders.id", ondelete="CASCADE"), index=True
    )
    file_code: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str | None] = mapped_column(String(2000))
    awarding_body: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Totes les files lot/fase mapejades del registre públic.
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)

    folder: Mapped[FavoriteFolder] = relationship(back_populates="favorites")
