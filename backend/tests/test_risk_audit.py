"""Red flags (specs/risk-audit.md)."""

import pytest

from tests.conftest import login_headers

pytestmark = pytest.mark.anyio


async def test_red_flags_api(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin")
    plain = await make_user("employee")  # sense can_audit

    denied = api_client.get(
        "/api/v1/audit/red-flags", headers=login_headers(api_client, plain.email)
    )
    assert denied.status_code == 403

    auditor = await make_user("employee", can_audit=True)
    for user in (admin, auditor):
        response = api_client.get(
            "/api/v1/audit/red-flags", headers=login_headers(api_client, user.email)
        )
        assert response.status_code == 200, response.text
        body = response.json()
        for block in ("splitting", "reckless_bids", "critical_renewals", "single_bidder"):
            assert "total" in body[block] and isinstance(body[block]["items"], list)
