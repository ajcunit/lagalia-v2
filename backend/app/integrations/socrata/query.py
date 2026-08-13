"""Query builder SoQL parametritzat (docs/08-hub-integracions.md §2.1).

Corregeix les injeccions de la v1: cap mètode accepta SoQL cru; els noms
de camp es validen per patró, els valors de text sempre van escapats
dins de literals i els valors tipats es validen abans d'entrar.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Self

_FIELD_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_DATASET_RE = re.compile(r"^[a-z0-9]{4}-[a-z0-9]{4}$")
_INE10_RE = re.compile(r"^\d{10}$")


class SoqlValidationError(ValueError):
    pass


def validate_dataset_id(dataset_id: str) -> str:
    if not _DATASET_RE.match(dataset_id):
        raise SoqlValidationError(f"Identificador de dataset invàlid: {dataset_id!r}")
    return dataset_id


def validate_ine10(value: str) -> str:
    if not _INE10_RE.match(value):
        raise SoqlValidationError("codi_ine10 ha de ser exactament 10 dígits")
    return value


def _field(name: str) -> str:
    if not _FIELD_RE.match(name):
        raise SoqlValidationError(f"Nom de camp invàlid: {name!r}")
    return name


def _text_literal(value: str) -> str:
    # L'única via d'entrada de text: escapat (dobla ') i dins de cometes.
    return "'" + value.replace("'", "''") + "'"


def _timestamp_literal(value: date | datetime | str) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise SoqlValidationError(f"Data no ISO: {value!r}") from exc
    return _text_literal(value.isoformat())


def _number_literal(value: int | float | Decimal | str) -> str:
    try:
        return str(Decimal(str(value)))
    except InvalidOperation as exc:
        raise SoqlValidationError(f"Valor numèric invàlid: {value!r}") from exc


class SoqlQuery:
    """Consulta immutable en construcció; en surt un dict de paràmetres $."""

    def __init__(self, dataset_id: str) -> None:
        self.dataset_id = validate_dataset_id(dataset_id)
        self._select: list[str] = []
        self._where: list[str] = []
        self._order: str | None = None
        self._limit: int | None = None
        self._offset: int | None = None
        self._q: str | None = None

    def select(self, *fields: str) -> Self:
        self._select.extend(_field(f) for f in fields)
        return self

    def where_eq(self, field: str, value: str) -> Self:
        self._where.append(f"{_field(field)} = {_text_literal(value)}")
        return self

    def where_ine10(self, field: str, value: str) -> Self:
        return self.where_eq(field, validate_ine10(value))

    def where_gte_timestamp(self, field: str, value: date | datetime | str) -> Self:
        self._where.append(f"{_field(field)} >= {_timestamp_literal(value)}")
        return self

    def where_lte_timestamp(self, field: str, value: date | datetime | str) -> Self:
        self._where.append(f"{_field(field)} <= {_timestamp_literal(value)}")
        return self

    def where_gte_number(self, field: str, value: int | float | Decimal | str) -> Self:
        self._where.append(f"{_field(field)} >= {_number_literal(value)}")
        return self

    def where_lte_number(self, field: str, value: int | float | Decimal | str) -> Self:
        self._where.append(f"{_field(field)} <= {_number_literal(value)}")
        return self

    def where_contains(self, field: str, value: str) -> Self:
        """Subcadena case-insensitive. El valor entra com a literal escapat;
        els comodins de LIKE dins del valor es neutralitzen deixant-los com a
        text (SoQL no té ESCAPE: % i _ es tracten amb upper+like i no poden
        sortir del literal)."""
        # Sense ESCAPE a SoQL: eliminem els comodins del valor de l'usuari
        # perquè no puguin ampliar la cerca (mai poden injectar sintaxi:
        # el literal ja va escapat i entre cometes).
        cleaned = value.replace("%", " ").replace("_", " ").strip()
        if not cleaned:
            return self
        literal = _text_literal(f"%{cleaned}%").upper()
        self._where.append(f"upper({_field(field)}) like {literal}")
        return self

    def full_text(self, value: str) -> Self:
        """Cerca de text completa: viatja com a paràmetre $q, mai dins $where."""
        self._q = value.strip() or None
        return self

    def order_by(self, field: str, *, descending: bool = False) -> Self:
        self._order = f"{_field(field)} {'DESC' if descending else 'ASC'}"
        return self

    def limit(self, value: int) -> Self:
        self._limit = max(1, int(value))
        return self

    def offset(self, value: int) -> Self:
        self._offset = max(0, int(value))
        return self

    def params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self._select:
            params["$select"] = ", ".join(self._select)
        if self._where:
            params["$where"] = " AND ".join(self._where)
        if self._order:
            params["$order"] = self._order
        if self._limit is not None:
            params["$limit"] = str(self._limit)
        if self._offset is not None:
            params["$offset"] = str(self._offset)
        if self._q is not None:
            params["$q"] = self._q
        return params
