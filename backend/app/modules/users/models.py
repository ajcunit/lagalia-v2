import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    LargeBinary,
    String,
    Table,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.models import TimestampMixin
from app.modules.departments.models import Department


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    PROCUREMENT_MANAGER = "procurement_manager"
    DEPT_MANAGER = "dept_manager"
    EMPLOYEE = "employee"


# Una assignació no es modifica: es crea i s'esborra. Per això només created_at.
user_departments = Table(
    "user_departments",
    Base.metadata,
    Column(
        "user_id",
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "department_id",
        BigInteger,
        ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Index("ix_user_departments_department_id", "department_id"),
)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(CITEXT(), unique=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    # NULL per a usuaris de directori (LDAP): auth_source de l'API es deriva d'aquí.
    password_hash: Mapped[str | None] = mapped_column(String(255))

    # Xifrat aplicatiu AES-256-GCM (docs/06-seguretat.md §4); mai en clar.
    dni_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    # Clau opaca del feed iCal (revocable regenerant-la); mai el JWT.
    ical_key: Mapped[str | None] = mapped_column(String(64), unique=True)

    can_audit: Mapped[bool] = mapped_column(Boolean, server_default="false")
    can_plan: Mapped[bool] = mapped_column(Boolean, server_default="false")

    departments: Mapped[list[Department]] = relationship(secondary=user_departments)


class LdapGroupMapping(Base):
    """Regla grup AD → rol O departament (specs/ldap-auth.md).

    El grup de rol és el que dona accés a la plataforma; el de departament
    només assigna l'abast. CHECK a la BD: exactament un dels dos camps.
    """

    __tablename__ = "ldap_group_mappings"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    ad_group: Mapped[str] = mapped_column(String(500))
    role: Mapped[UserRole | None] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    department_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("departments.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Tots els tokens d'una mateixa sessió comparteixen família: si un token
    # rotat es reutilitza, es revoca la família sencera.
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_ip: Mapped[str | None] = mapped_column(INET)
