"""Paginació per cursor (keyset) segons les convencions del contracte.

El cursor codifica [valor_del_camp_d'ordre, id] de l'últim element en
base64url; és opac per al client i no conté cap dada sensible.
"""

import base64
import binascii
import json
from typing import Any

from pydantic import BaseModel

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
