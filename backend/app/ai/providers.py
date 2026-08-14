"""Capa de proveïdors LLM (specs/ai-providers.md; 07 §1.1).

Interfície única sobre protocols openai_compatible i claude. TLS sempre
verificat; tota crida registra una fila a ai_runs.
"""

import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.ai.models import AiProtocol, AiProviderProfile, AiRun
from app.core import crypto
from app.core.db import session_factory

_TIMEOUT = 120.0
_ADMIN_TIMEOUT = 15.0

# Només per a tests: injecció d'un transport fals (MockTransport).
_transport: httpx.AsyncBaseTransport | None = None


class ProviderError(Exception):
    pass


@dataclass
class CompletionResult:
    content: str
    input_tokens: int | None
    output_tokens: int | None
    model: str


def _api_key(profile: AiProviderProfile) -> str | None:
    if profile.api_key_encrypted is None:
        return None
    return crypto.decrypt_value(profile.api_key_encrypted)


def _headers(profile: AiProviderProfile) -> dict[str, str]:
    key = _api_key(profile)
    if profile.protocol == AiProtocol.CLAUDE:
        headers = {"anthropic-version": "2023-06-01"}
        if key:
            headers["x-api-key"] = key
        return headers
    return {"Authorization": f"Bearer {key}"} if key else {}


async def list_models(profile: AiProviderProfile) -> list[str]:
    """Autodetecció de models (healthcheck d'admin, síncron i curt)."""
    base = profile.base_url.rstrip("/")
    url = f"{base}/models" if profile.protocol != AiProtocol.CLAUDE else f"{base}/v1/models"
    async with httpx.AsyncClient(timeout=_ADMIN_TIMEOUT, transport=_transport) as client:
        try:
            response = await client.get(url, headers=_headers(profile))
        except httpx.TransportError as exc:
            raise ProviderError(f"proveïdor inaccessible: {exc}") from exc
    if response.status_code != 200:
        raise ProviderError(f"el proveïdor ha respost {response.status_code}")
    payload = response.json()
    return sorted(
        str(item.get("id"))
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    )


async def complete(
    profile: AiProviderProfile,
    messages: list[dict[str, str]],
    *,
    task: str,
    model: str | None = None,
    max_tokens: int = 4096,
    user_id: int | None = None,
    trace_id: str | None = None,
    input_summary: str | None = None,
) -> CompletionResult:
    """Crida única de compleció; registra sempre ai_runs (èxit o error)."""
    chosen = model or profile.default_model
    if not chosen:
        raise ProviderError("el perfil no té model per defecte")
    base = profile.base_url.rstrip("/")
    if profile.protocol == AiProtocol.CLAUDE:
        url = f"{base}/v1/messages"
        system = "\n".join(m["content"] for m in messages if m["role"] == "system") or None
        body: dict[str, Any] = {
            "model": chosen,
            "max_tokens": max_tokens,
            "messages": [m for m in messages if m["role"] != "system"],
        }
        if system:
            body["system"] = system
    elif profile.protocol == AiProtocol.OPENAI_COMPATIBLE:
        url = f"{base}/chat/completions"
        body = {"model": chosen, "max_tokens": max_tokens, "messages": messages}
    else:
        raise ProviderError(f"protocol no suportat encara: {profile.protocol}")

    started = time.monotonic()
    status, error_detail = "success", None
    content, tokens_in, tokens_out = "", None, None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=_transport) as client:
            response = await client.post(url, json=body, headers=_headers(profile))
        if response.status_code != 200:
            raise ProviderError(f"el proveïdor ha respost {response.status_code}")
        data = response.json()
        if profile.protocol == AiProtocol.CLAUDE:
            content = "".join(
                block.get("text", "") for block in data.get("content", [])
                if block.get("type") == "text"
            )
            usage = data.get("usage", {})
            tokens_in, tokens_out = usage.get("input_tokens"), usage.get("output_tokens")
        else:
            content = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens")
            tokens_out = usage.get("completion_tokens")
    except httpx.TransportError as exc:
        status, error_detail = "error", f"proveïdor inaccessible: {exc}"
    except (ProviderError, KeyError, ValueError) as exc:
        status, error_detail = "error", str(exc)

    latency_ms = int((time.monotonic() - started) * 1000)
    async with session_factory() as session:
        session.add(
            AiRun(
                task=task,
                provider_profile_id=profile.id,
                model=chosen,
                input_summary=(input_summary or "")[:500] or None,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                latency_ms=latency_ms,
                status=status,
                error_detail=error_detail,
                user_id=user_id,
                trace_id=trace_id,
            )
        )
        await session.commit()

    if status == "error":
        raise ProviderError(error_detail or "error desconegut")
    return CompletionResult(
        content=content, input_tokens=tokens_in, output_tokens=tokens_out, model=chosen
    )
