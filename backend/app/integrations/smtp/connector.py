"""Connector smtp: enviament de correu amb la stdlib, en thread.

TLS sempre verificat (06 §2). Les credencials arriben desxifrades pel hub.
"""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

from app.integrations import hub
from app.integrations.base import ConnectorError, HealthStatus, Manifest

MANIFEST = Manifest(
    slug="smtp",
    name="Correu sortint (SMTP)",
    version="1.0.0",
    capabilities=["email_send"],
    config_defaults={
        "host": "",
        "port": 587,
        "starttls": True,
        "from_address": "",
        "from_name": "LAGALia",
    },
    credentials=["username", "password"],
)


class SmtpConnector:
    manifest = MANIFEST

    def __init__(self, config: dict[str, Any], credentials: dict[str, str]) -> None:
        self.config = config
        self._username = credentials.get("username")
        self._password = credentials.get("password")

    def _connect(self) -> smtplib.SMTP:
        host = str(self.config.get("host") or "")
        if not host:
            raise ConnectorError("smtp sense host configurat")
        client = smtplib.SMTP(host, int(self.config.get("port") or 587), timeout=15)
        client.ehlo()
        if self.config.get("starttls", True):
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        if self._username and self._password:
            client.login(self._username, self._password)
        return client

    def _send_sync(self, to: list[str], subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = formataddr(
            (str(self.config.get("from_name") or "LAGALia"), str(self.config["from_address"]))
        )
        message["To"] = ", ".join(to)
        message["Subject"] = subject
        message.set_content(body)
        try:
            with self._connect() as client:
                client.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise ConnectorError(f"enviament smtp fallit: {exc}") from exc

    async def send_mail(self, to: list[str], subject: str, body: str) -> None:
        if not to:
            return
        await asyncio.to_thread(self._send_sync, to, subject, body)

    async def healthcheck(self) -> HealthStatus:
        def _check() -> None:
            with self._connect():
                pass

        try:
            await asyncio.to_thread(_check)
        except (ConnectorError, OSError) as exc:
            return HealthStatus(healthy=False, detail=str(exc))
        return HealthStatus(healthy=True)


def _factory(config: dict[str, Any], credentials: dict[str, str]) -> SmtpConnector:
    return SmtpConnector(config, credentials)


hub.register(MANIFEST, _factory)
