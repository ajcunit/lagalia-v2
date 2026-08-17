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
        "reports.audit_recipients",
        "Destinataris de l'informe mensual d'auditoria (correus separats per comes)",
        "intervencio@cunit.cat, secretaria@cunit.cat",
    ),
]
