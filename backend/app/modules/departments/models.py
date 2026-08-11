from sqlalchemy import BigInteger, Boolean, Identity, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import TimestampMixin


class Department(Base, TimestampMixin):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    # Grup de Gestiona associat, si la integració és activa.
    gestiona_group_id: Mapped[str | None] = mapped_column(String(100))
    gestiona_group_name: Mapped[str | None] = mapped_column(String(255))
    gestiona_group_href: Mapped[str | None] = mapped_column(String(500))
