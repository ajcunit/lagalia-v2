from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Identity, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import TimestampMixin


class Setting(Base, TimestampMixin):
    """Configuració clau/valor (docs/04-model-de-dades.md §5).

    Els valors amb is_secret=true es guarden xifrats i mai es retornen
    per API (només `is_set: true`) — comportament del mòdul de config.
    """

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True)
    value: Mapped[dict[str, Any] | list[Any] | str | int | float | bool | None] = mapped_column(
        JSONB
    )
    description: Mapped[str | None] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, server_default="false")
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
