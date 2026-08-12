"""Paginació per cursor (keyset) segons les convencions del contracte.

El cursor codifica [valor_del_camp_d'ordre, id] de l'últim element en
base64url; és opac per al client i no conté cap dada sensible.
"""

import base64
import binascii
import json
from typing import Any

from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, cast, literal, or_, tuple_

from app.core.problems import Problem


class PageMeta(BaseModel):
    total: int
    next_cursor: str | None = None


def encode_cursor(values: list[Any]) -> str:
    payload = json.dumps(values, default=str, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> list[Any]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        raise Problem(422, "Cursor de paginació invàlid", "validation") from None
    if not isinstance(values, list) or len(values) != 2:
        raise Problem(422, "Cursor de paginació invàlid", "validation")
    return values


def keyset_condition(
    column: Any,
    id_column: Any,
    last_value: Any,
    last_id: Any,
    *,
    descending: bool,
) -> ColumnElement[bool]:
    """Condició de continuació del keyset (columna, id) respecte al cursor.

    Dues subtileses que han mossegat de debò:
    - El valor viatja com a text dins del cursor JSON: es fa CAST al tipus
      real de la columna al servidor (sense això, Postgres no pot comparar
      timestamptz/numeric amb varchar i la pàgina 2 peta).
    - Els NULLs del camp d'ordre (DESC nulls last / ASC nulls first) han de
      continuar apareixent després del tall: la comparació de tuples amb
      NULL és NULL i els perdria.
    """
    try:
        last_id_int = int(last_id)
    except (TypeError, ValueError):
        raise Problem(422, "Cursor de paginació invàlid", "validation") from None

    if last_value is None:
        if descending:
            # Som al tram final de NULLs: només queden NULLs amb id menor.
            return and_(column.is_(None), id_column < last_id_int)
        # ASC nulls first: acabem els NULLs i després TOTS els no nuls.
        return or_(and_(column.is_(None), id_column > last_id_int), column.is_not(None))

    typed_value = cast(literal(str(last_value)), column.type)
    keyset = tuple_(column, id_column)
    boundary = tuple_(typed_value, literal(last_id_int))
    if descending:
        # Després del tall vénen no nuls menors i, al final, els NULLs.
        return or_(keyset < boundary, column.is_(None))
    return keyset > boundary
