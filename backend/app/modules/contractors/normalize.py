"""Normalització de noms d'adjudicatari (specs/contractor-normalization.md).

Només per a COMPARACIÓ d'identitat: mai s'escriu el nom normalitzat.
Dos noms amb la mateixa normalització són la mateixa empresa (variant
trivial de puntuació/majúscules/forma societària).
"""

import re
import unicodedata

# Formes societàries al FINAL del nom (amb o sense punts/espais).
_CORPORATE_FORMS = (
    "slu",
    "sll",
    "slp",
    "sl",
    "sau",
    "sa",
    "sccl",
    "scp",
    "scoop",
    "coop",
    "aie",
    "ute",
)

# Formes escrites senceres, també només al final (es treuen abans).
_CORPORATE_PHRASES = (
    "sociedad limitada unipersonal",
    "sociedad limitada",
    "sociedad anonima unipersonal",
    "sociedad anonima",
    "societat limitada unipersonal",
    "societat limitada",
    "societat anonima",
    "societat cooperativa catalana limitada",
    "societat cooperativa",
    "sociedad cooperativa",
)

_PUNCT_RE = re.compile(r"[^a-z0-9\s]")
_SPACES_RE = re.compile(r"\s+")


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = _PUNCT_RE.sub(" ", text.lower())
    text = _SPACES_RE.sub(" ", text).strip()
    # Primer les formes escrites senceres («... SOCIEDAD LIMITADA»).
    changed = True
    while changed:
        changed = False
        for phrase in _CORPORATE_PHRASES:
            if text != phrase and text.endswith(" " + phrase):
                text = text[: -len(phrase)].strip()
                changed = True

    # Elimina formes societàries del final, iterativament. La puntuació ja
    # és espai, així que «S.L.U.» arriba com a lletres soltes «s l u».
    words = text.split(" ")
    while len(words) > 1:
        if words[-1] in _CORPORATE_FORMS:
            words.pop()
            continue
        # Ajunta lletres soltes del final: «s l» → «sl», «s c c l» → «sccl».
        start = len(words)
        while start > 1 and len(words[start - 1]) == 1:
            start -= 1
        if start < len(words) and "".join(words[start:]) in _CORPORATE_FORMS:
            del words[start:]
            continue
        break
    return " ".join(words)


def identity_key(name: str | None) -> str:
    """Clau d'identitat per a comparació DINS del mateix NIF.

    Insensible també a espais i guions («OFF-SHORE» vs «OFFSHORE»): amb el
    NIF igual, la col·lisió de claus és la mateixa empresa amb seguretat.
    """
    return normalize_name(name).replace(" ", "")
