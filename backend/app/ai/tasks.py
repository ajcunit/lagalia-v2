"""Resolució de proveïdor/model per tasca (specs/ai-task-config.md)."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.models import AiProviderProfile, AiTaskConfig
from app.core.problems import Problem

# Tasques conegudes (creix amb cada agent). Clau → descripció per a la UI.
KNOWN_TASKS: dict[str, str] = {
    "cpv.extract": "Classificador CPV — extracció de paraules clau i divisions",
    "cpv.rank": "Classificador CPV — re-rànquing final dels candidats",
    "audit.report": "Auditor — informe executiu sobre els red flags",
    "analyst.chat": "Analista de dades — preguntes en llenguatge natural amb eines",
    "rag.embed": "RAG — embeddings dels documents (cal un model d'embeddings)",
    "doc.index": "Redactor — proposta d'índex a partir de les referències",
    "doc.section": "Redactor — redacció d'una secció amb RAG i citació de fonts",
    "legal.review": "Assistent legal — revisió de conformitat amb citació d'articles",
    "doc.review": "Redactor — agent revisor (coherència, buits i to del document)",
    "chat.contract": "Xat d'expedient — respostes amb el context i els documents del contracte",
}


@dataclass
class Resolved:
    profile: AiProviderProfile
    model: str | None  # None → model per defecte del perfil
    max_tokens: int | None


async def resolve(session: AsyncSession, task: str) -> Resolved:
    """Config de la tasca (si el perfil és actiu) → primer perfil actiu → 409."""
    config = (
        await session.execute(select(AiTaskConfig).where(AiTaskConfig.task == task))
    ).scalar_one_or_none()
    if config is not None:
        profile = await session.get(AiProviderProfile, config.provider_profile_id)
        if profile is not None and profile.enabled:
            return Resolved(profile=profile, model=config.model, max_tokens=config.max_tokens)
    fallback = (
        await session.execute(
            select(AiProviderProfile)
            .where(AiProviderProfile.enabled)
            .order_by(AiProviderProfile.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if fallback is None:
        raise Problem(409, "Cap perfil d'IA actiu (configura'l a /admin/ai)", "conflict")
    return Resolved(profile=fallback, model=None, max_tokens=None)
