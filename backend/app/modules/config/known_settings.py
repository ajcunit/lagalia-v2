"""Paràmetres coneguts de la plataforma (specs/config-ui.md).

La taula de paràmetres només mostrava els que ja existien a la BD, de
manera que un paràmetre nou (p. ex. els destinataris de l'informe
d'auditoria) no es podia crear des de la UI. Aquest registre els
declara perquè apareguin sempre, buits i editables.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class KnownSetting:
    key: str
    description: str
    placeholder: str = ""
    is_secret: bool = False


KNOWN_SETTINGS: list[KnownSetting] = [
    KnownSetting("org.name", "Nom de l'ens", "Ajuntament de Cunit"),
    KnownSetting("org.ine10_code", "Codi INE10 de l'ens", "4305160009"),
    KnownSetting(
        "contracts.expiry_warning_months",
        "Mesos d'antelació de l'avís de venciment (global)",
        "6",
    ),
    KnownSetting(
        "retention.audit_log_days",
        "Retenció de l'auditoria en dies abans de la purga automàtica "
        "(30-3650; per defecte 730 = 2 anys; segons indicacions del DPO)",
        "730",
    ),
    KnownSetting(
        "retention.ai_days",
        "Retenció d'execucions d'IA i converses de xat en dies "
        "(30-3650; per defecte 365 = 1 any; segons indicacions del DPO)",
        "365",
    ),
    KnownSetting(
        "reports.audit_enabled",
        "Informe d'auditoria automàtic activat (true/false; desactivat de sèrie)",
        "false",
    ),
    KnownSetting(
        "reports.audit_interval_days",
        "Cadència de l'informe d'auditoria automàtic, en dies (1-365)",
        "30",
    ),
    KnownSetting(
        "reports.audit_recipients",
        "Destinataris de l'informe mensual d'auditoria (correus separats per comes)",
        "intervencio@cunit.cat, secretaria@cunit.cat",
    ),
    KnownSetting(
        "modules.disabled",
        "Mòduls desactivats (llista JSON; gestiona-ho des de la pestanya Mòduls)",
        "[]",
    ),
    KnownSetting(
        "sync.nightly_enabled",
        "Sincronització nocturna de contractes activada (true/false; no definit = activada)",
        "true",
    ),
    KnownSetting(
        "sync.nightly_time",
        "Hora local (Europe/Madrid) de la cadena nocturna, format HH:MM",
        "02:30",
    ),
    KnownSetting(
        "sync.nightly_days",
        "Dies de la setmana de la cadena nocturna (llista JSON ISO: 1=dilluns … "
        "7=diumenge; buit = tots)",
        "[1, 2, 3, 4, 5, 6, 7]",
    ),
    KnownSetting(
        "sync.nightly_enrich",
        "Encuar l'enriquiment PSCP dels expedients pendents en acabar la cadena "
        "nocturna (true/false; no definit = activat)",
        "true",
    ),
    KnownSetting(
        "rag.indexable_phases",
        "Fases dels documents que es descarreguen i s'indexen al RAG (llista JSON; "
        "buit o no definit = totes). La resta es mostren només amb enllaç al portal.",
        '["licitacio", "adjudicacio", "formalitzacio"]',
    ),
]
