"""Agent classificador CPV (specs/cpv-ai-suggest.md; pipeline A3 §3).

Híbrid: heurística + extracció LLM + recuperació lèxica puntuada +
re-rànquing LLM amb fallback lèxic si el JSON no valida.
"""

import json
import re
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import providers, tasks

_ADMIN_PREFIX_RE = re.compile(
    r"^(contracte|contractació|servei|expedient)\s+(de|del|d')\s+", re.IGNORECASE
)
_STOPWORDS = {
    "de", "del", "la", "el", "els", "les", "i", "a", "al", "als", "per", "amb", "en",
    "un", "una", "uns", "unes", "que", "dels", "d", "l", "o", "u", "es",
}
_TYPE_KEYWORDS = {
    "obra": ["obra", "obres", "construcció", "reforma", "urbanització", "enderroc", "pavimentació"],
    "servei": ["servei", "serveis", "manteniment", "neteja", "gestió", "assistència", "redacció"],
    "subministrament": ["subministrament", "adquisició", "compra", "equipament", "material"],
}
_TYPE_PREFIX = {"obra": "45", "servei": None, "subministrament": None}

CPV_EXTRACT_PROMPT = (
    "You are an expert in European CPV classification (Reg. 213/2008).\n"
    "Extract from the contract description: relevant Catalan keywords (singular),\n"
    "likely CPV division prefixes (2 digits) and any full candidate CPV codes.\n"
    'Return ONLY JSON: {"keywords": [...], "divisions": [...], "codes": [...]}'
)
CPV_RANK_PROMPT = (
    "You are an expert in European CPV classification (Reg. 213/2008).\n"
    "Rank candidates for the contract description. Select the most specific codes.\n"
    'Return ONLY a JSON array: [{"code","description","score","justification"}] '
    "with at most 5 items, score in [0,1] and justification in Catalan."
)


def clean_description(value: str) -> str:
    cleaned = value.strip()
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _ADMIN_PREFIX_RE.sub("", cleaned)
    return cleaned or value.strip()


def detect_type(value: str) -> str | None:
    lowered = value.lower()
    scores = {
        kind: sum(1 for word in words if word in lowered)
        for kind, words in _TYPE_KEYWORDS.items()
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else None


def stem_ca(word: str) -> str:
    """Stemming català simplificat (A3 §3.6)."""
    for suffix in ("es", "ons", "ns", "iva", "iu", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: len(word) - len(suffix)]
    return word


def keywords_of(value: str) -> list[str]:
    words = re.findall(r"[a-zà-üA-ZÀ-Ü]{3,}", value.lower())
    return [w for w in words if w not in _STOPWORDS]


def strip_json(content: str) -> str:
    """Neteja v1 (A3 §2): <think>, blocs ``` i retall al JSON."""
    content = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", content, flags=re.DOTALL)
    content = re.sub(r"```(?:json)?", "", content)
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = content.find(opener), content.rfind(closer)
        if start != -1 and end > start:
            return content[start : end + 1]
    return content.strip()


async def _extract(
    session: AsyncSession, description: str, **run_kw: Any
) -> dict[str, Any]:
    resolved = await tasks.resolve(session, "cpv.extract")
    try:
        result = await providers.complete(
            resolved.profile,
            [
                {"role": "system", "content": CPV_EXTRACT_PROMPT},
                {"role": "user", "content": description},
            ],
            task="cpv.extract",
            model=resolved.model,
            max_tokens=resolved.max_tokens or 20000,
            input_summary=description[:200],
            **run_kw,
        )
        parsed = json.loads(strip_json(result.content))
        if isinstance(parsed, dict):
            return parsed
    except (providers.ProviderError, json.JSONDecodeError):
        pass
    return {}


async def retrieve_candidates(
    session: AsyncSession,
    description: str,
    llm_hints: dict[str, Any],
    contract_type: str | None,
) -> list[dict[str, Any]]:
    """Recuperació lèxica puntuada (taula de punts d'A3 §3.4)."""
    keywords = keywords_of(description)
    hint_keywords = [
        str(k).lower() for k in llm_hints.get("keywords", []) if isinstance(k, str)
    ]
    all_keywords = list(dict.fromkeys(keywords + [k for k in hint_keywords if k]))[:12]
    stems = [stem_ca(k) for k in all_keywords]
    divisions = [str(d)[:2] for d in llm_hints.get("divisions", []) if str(d)[:2].isdigit()]
    codes = [str(c) for c in llm_hints.get("codes", []) if re.match(r"^\d{8}", str(c))]

    scores: dict[str, dict[str, Any]] = {}

    def add(code: str, description_text: str, points: float) -> None:
        entry = scores.setdefault(
            code, {"code": code, "description": description_text, "score": 0.0}
        )
        entry["score"] += points

    # Coincidències per mot (exactes amb stemming) i difuses (trigram).
    for stem in dict.fromkeys(stems):
        if len(stem) < 3:
            continue
        rows = (
            await session.execute(
                text(
                    "SELECT code, description, similarity(lower(description), :w) AS sim "
                    "FROM cpv_codes WHERE lower(description) LIKE :like "
                    "OR similarity(lower(description), :w) > 0.25 "
                    "ORDER BY sim DESC NULLS LAST LIMIT 40"
                ),
                {"w": stem, "like": f"%{stem}%"},
            )
        ).all()
        for row in rows:
            exact = stem in (row.description or "").lower()
            add(row.code, row.description, 1.0 if exact else 0.5)

    # Parelles de mots consecutius.
    for first, second in zip(stems, stems[1:], strict=False):
        rows = (
            await session.execute(
                select(func.count())
                .select_from(text("cpv_codes"))
                .where(text("lower(description) LIKE :a AND lower(description) LIKE :b"))
                .params(a=f"%{first}%", b=f"%{second}%")
            )
        ).scalar_one()
        if rows:
            pair_rows = (
                await session.execute(
                    text(
                        "SELECT code, description FROM cpv_codes "
                        "WHERE lower(description) LIKE :a AND lower(description) LIKE :b LIMIT 20"
                    ),
                    {"a": f"%{first}%", "b": f"%{second}%"},
                )
            ).all()
            for row in pair_rows:
                add(row.code, row.description, 5.0)

    # Codis i divisions del LLM; prefix del tipus detectat.
    for code in codes:
        row = (
            await session.execute(
                text("SELECT code, description FROM cpv_codes WHERE code LIKE :p LIMIT 1"),
                {"p": f"{code[:8]}%"},
            )
        ).first()
        if row:
            add(row.code, row.description, 10.0)
    prefixes = [(d, 5.0) for d in divisions]
    type_prefix = _TYPE_PREFIX.get(contract_type or "")
    if type_prefix:
        prefixes.append((type_prefix, 5.0))
    for prefix, points in prefixes:
        for code, entry in list(scores.items()):
            if code.startswith(prefix):
                entry["score"] += points

    ranked = sorted(scores.values(), key=lambda e: e["score"], reverse=True)
    return ranked[:60]


async def suggest(
    session: AsyncSession,
    raw_text: str,
    *,
    user_id: int | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    description = clean_description(raw_text)
    contract_type = detect_type(description)
    run_kw = {"user_id": user_id, "trace_id": trace_id}

    hints = await _extract(session, description, **run_kw)
    candidates = await retrieve_candidates(session, description, hints, contract_type)
    lexical_top = [
        {
            "code": c["code"],
            "description": c["description"],
            "score": round(min(1.0, c["score"] / 20.0), 2),
            "justification": "coincidència lèxica amb el diccionari CPV",
        }
        for c in candidates[:5]
    ]
    if not candidates:
        return {"contract_type": contract_type, "suggestions": [], "source": "lexical"}

    candidate_lines = "\n".join(f"{c['code']} — {c['description']}" for c in candidates)
    try:
        resolved = await tasks.resolve(session, "cpv.rank")
        result = await providers.complete(
            resolved.profile,
            [
                {"role": "system", "content": CPV_RANK_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Contract description: {description}\n\n"
                        f"Candidates:\n{candidate_lines}"
                    ),
                },
            ],
            task="cpv.rank",
            model=resolved.model,
            max_tokens=resolved.max_tokens or 20000,
            input_summary=description[:200],
            **run_kw,
        )
        parsed = json.loads(strip_json(result.content))
        valid_codes = {c["code"] for c in candidates}
        suggestions = []
        for item in parsed if isinstance(parsed, list) else []:
            code = str(item.get("code", ""))
            if code in valid_codes:
                suggestions.append(
                    {
                        "code": code,
                        "description": next(
                            c["description"] for c in candidates if c["code"] == code
                        ),
                        "score": float(item.get("score", 0)),
                        "justification": str(item.get("justification", ""))[:500],
                    }
                )
        if suggestions:
            return {
                "contract_type": contract_type,
                "suggestions": suggestions[:5],
                "source": "llm",
            }
    except (providers.ProviderError, json.JSONDecodeError, ValueError, KeyError, StopIteration):
        pass
    return {"contract_type": contract_type, "suggestions": lexical_top, "source": "lexical"}
