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
    if profile.protocol == AiProtocol.GEMINI:
        return {}  # la clau viatja com a paràmetre ?key=
    return {"Authorization": f"Bearer {key}"} if key else {}


async def list_models(profile: AiProviderProfile) -> list[str]:
    """Autodetecció de models (healthcheck d'admin, síncron i curt)."""
    base = profile.base_url.rstrip("/")
    params: dict[str, str] = {}
    if profile.protocol == AiProtocol.CLAUDE:
        url = f"{base}/v1/models"
    elif profile.protocol == AiProtocol.OLLAMA:
        url = f"{base}/api/tags"
    elif profile.protocol == AiProtocol.GEMINI:
        url = f"{base}/v1beta/models"
        key = _api_key(profile)
        if key:
            params["key"] = key
    else:
        url = f"{base}/models"
    async with httpx.AsyncClient(timeout=_ADMIN_TIMEOUT, transport=_transport) as client:
        try:
            response = await client.get(url, headers=_headers(profile), params=params)
        except httpx.TransportError as exc:
            raise ProviderError(f"proveïdor inaccessible: {exc}") from exc
    if response.status_code != 200:
        raise ProviderError(f"el proveïdor ha respost {response.status_code}")
    payload = response.json()
    if profile.protocol == AiProtocol.OLLAMA:
        return sorted(
            str(item.get("name"))
            for item in payload.get("models", [])
            if isinstance(item, dict) and item.get("name")
        )
    if profile.protocol == AiProtocol.GEMINI:
        return sorted(
            str(item.get("name", "")).removeprefix("models/")
            for item in payload.get("models", [])
            if isinstance(item, dict) and item.get("name")
        )
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
    elif profile.protocol == AiProtocol.OLLAMA:
        url = f"{base}/api/chat"
        body = {
            "model": chosen,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
    elif profile.protocol == AiProtocol.GEMINI:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system") or None
        url = f"{base}/v1beta/models/{chosen}:generateContent"
        body = {
            "contents": [
                {
                    "role": "model" if m["role"] == "assistant" else "user",
                    "parts": [{"text": m["content"]}],
                }
                for m in messages
                if m["role"] != "system"
            ],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
    elif profile.protocol == AiProtocol.OPENAI_COMPATIBLE:
        url = f"{base}/chat/completions"
        body = {"model": chosen, "max_tokens": max_tokens, "messages": messages}
    else:
        raise ProviderError(f"protocol no suportat encara: {profile.protocol}")

    started = time.monotonic()
    status, error_detail = "success", None
    content, tokens_in, tokens_out = "", None, None
    params: dict[str, str] = {}
    if profile.protocol == AiProtocol.GEMINI:
        key = _api_key(profile)
        if key:
            params["key"] = key
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=_transport) as client:
            response = await client.post(url, json=body, headers=_headers(profile), params=params)
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
        elif profile.protocol == AiProtocol.OLLAMA:
            content = (data.get("message") or {}).get("content", "")
            tokens_in = data.get("prompt_eval_count")
            tokens_out = data.get("eval_count")
        elif profile.protocol == AiProtocol.GEMINI:
            candidates = data.get("candidates") or []
            parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
            content = "".join(part.get("text", "") for part in parts)
            usage = data.get("usageMetadata", {})
            tokens_in = usage.get("promptTokenCount")
            tokens_out = usage.get("candidatesTokenCount")
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


async def stream(
    profile: AiProviderProfile,
    messages: list[dict[str, str]],
    *,
    task: str,
    model: str | None = None,
    max_tokens: int = 4096,
    user_id: int | None = None,
    trace_id: str | None = None,
    input_summary: str | None = None,
):
    """Compleció en streaming: cedeix {"kind": "text"|"thinking", "text": ...}.

    Els models raonadors (Qwen, deepseek-r1…) emeten primer el raonament
    (reasoning_content a vLLM, <think> inline a Ollama): es reenvia com a
    "thinking" perquè la UI mostri activitat des del primer token.

    Protocols amb stream natiu: openai_compatible (SSE) i claude (SSE) i
    ollama (NDJSON). Gemini fa fallback a complete() en un sol tros.
    """
    chosen = model or profile.default_model
    if not chosen:
        raise ProviderError("el perfil no té model per defecte")
    if profile.protocol == AiProtocol.GEMINI:
        result = await complete(
            profile, messages, task=task, model=model, max_tokens=max_tokens,
            user_id=user_id, trace_id=trace_id, input_summary=input_summary,
        )
        yield {"kind": "text", "text": result.content}
        return

    base = profile.base_url.rstrip("/")
    if profile.protocol == AiProtocol.CLAUDE:
        url = f"{base}/v1/messages"
        system = "\n".join(m["content"] for m in messages if m["role"] == "system") or None
        body: dict[str, Any] = {
            "model": chosen, "max_tokens": max_tokens, "stream": True,
            "messages": [m for m in messages if m["role"] != "system"],
        }
        if system:
            body["system"] = system
    elif profile.protocol == AiProtocol.OLLAMA:
        url = f"{base}/api/chat"
        body = {"model": chosen, "messages": messages, "stream": True,
                "options": {"num_predict": max_tokens}}
    else:
        url = f"{base}/chat/completions"
        body = {"model": chosen, "max_tokens": max_tokens, "messages": messages, "stream": True}

    import json as _json

    started = time.monotonic()
    status, error_detail = "success", None
    tokens_in = tokens_out = None
    collected: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=_transport) as client:
            async with client.stream("POST", url, json=body, headers=_headers(profile)) as response:
                if response.status_code != 200:
                    raise ProviderError(f"el proveïdor ha respost {response.status_code}")
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        break
                    try:
                        event = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
                    delta = ""
                    thinking = ""
                    if profile.protocol == AiProtocol.CLAUDE:
                        if event.get("type") == "content_block_delta":
                            block_delta = event.get("delta") or {}
                            delta = block_delta.get("text", "")
                            thinking = block_delta.get("thinking", "")
                        elif event.get("type") == "message_delta":
                            usage = event.get("usage") or {}
                            tokens_out = usage.get("output_tokens", tokens_out)
                        elif event.get("type") == "message_start":
                            usage = (event.get("message") or {}).get("usage") or {}
                            tokens_in = usage.get("input_tokens", tokens_in)
                    elif profile.protocol == AiProtocol.OLLAMA:
                        delta = (event.get("message") or {}).get("content", "")
                        if event.get("done"):
                            tokens_in = event.get("prompt_eval_count", tokens_in)
                            tokens_out = event.get("eval_count", tokens_out)
                    else:
                        choices = event.get("choices") or []
                        if choices:
                            choice_delta = choices[0].get("delta") or {}
                            delta = choice_delta.get("content") or ""
                            thinking = choice_delta.get("reasoning_content") or ""
                        usage = event.get("usage") or {}
                        if usage:
                            tokens_in = usage.get("prompt_tokens", tokens_in)
                            tokens_out = usage.get("completion_tokens", tokens_out)
                    if thinking:
                        yield {"kind": "thinking", "text": thinking}
                    if delta:
                        collected.append(delta)
                        yield {"kind": "text", "text": delta}
    except httpx.TransportError as exc:
        status, error_detail = "error", f"proveïdor inaccessible: {exc}"
    except ProviderError as exc:
        status, error_detail = "error", str(exc)

    latency_ms = int((time.monotonic() - started) * 1000)
    async with session_factory() as session:
        session.add(
            AiRun(
                task=task, provider_profile_id=profile.id, model=chosen,
                input_summary=(input_summary or "")[:500] or None,
                input_tokens=tokens_in, output_tokens=tokens_out,
                latency_ms=latency_ms, status=status, error_detail=error_detail,
                user_id=user_id, trace_id=trace_id,
            )
        )
        await session.commit()
    if status == "error":
        raise ProviderError(error_detail or "error desconegut")


async def embed(
    profile: AiProviderProfile,
    texts: list[str],
    *,
    model: str | None = None,
    user_id: int | None = None,
    trace_id: str | None = None,
) -> list[list[float]]:
    """Embeddings en lot (rag.embed): openai_compatible /embeddings o ollama /api/embed."""
    chosen = model or profile.default_model
    if not chosen:
        raise ProviderError("el perfil no té model per defecte")
    base = profile.base_url.rstrip("/")
    if profile.protocol == AiProtocol.OLLAMA:
        url, body = f"{base}/api/embed", {"model": chosen, "input": texts}
    elif profile.protocol == AiProtocol.OPENAI_COMPATIBLE:
        url, body = f"{base}/embeddings", {"model": chosen, "input": texts}
    else:
        raise ProviderError(f"el protocol {profile.protocol} no suporta embeddings aquí")

    started = time.monotonic()
    status, error_detail, vectors, tokens_in = "success", None, [], None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=_transport) as client:
            response = await client.post(url, json=body, headers=_headers(profile))
        if response.status_code != 200:
            raise ProviderError(f"el proveïdor ha respost {response.status_code}")
        data = response.json()
        if profile.protocol == AiProtocol.OLLAMA:
            vectors = data.get("embeddings") or []
        else:
            vectors = [item["embedding"] for item in data.get("data", [])]
            tokens_in = (data.get("usage") or {}).get("prompt_tokens")
        if len(vectors) != len(texts):
            raise ProviderError("nombre d'embeddings inesperat")
    except httpx.TransportError as exc:
        status, error_detail = "error", f"proveïdor inaccessible: {exc}"
    except (ProviderError, KeyError, ValueError) as exc:
        status, error_detail = "error", str(exc)

    async with session_factory() as session:
        session.add(
            AiRun(
                task="rag.embed", provider_profile_id=profile.id, model=chosen,
                input_summary=f"{len(texts)} fragments",
                input_tokens=tokens_in, output_tokens=None,
                latency_ms=int((time.monotonic() - started) * 1000),
                status=status, error_detail=error_detail,
                user_id=user_id, trace_id=trace_id,
            )
        )
        await session.commit()
    if status == "error":
        raise ProviderError(error_detail or "error desconegut")
    return vectors
