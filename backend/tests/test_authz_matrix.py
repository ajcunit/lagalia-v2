"""Taula de veritat de l'annex A2, testejada cel·la a cel·la.

TRUTH_TABLE és una transcripció MANUAL i independent de la matriu del
codi (docs/annexos/A2-matriu-permisos.md §2): si PERMISSION_MATRIX
canvia, aquest test només ha de passar si el canvi respecta l'annex.
Cada cel·la és (accés, flag_requerit) o None (denegat).
"""

import pytest

from app.core import authz
from app.core.authz import Access
from app.modules.users.models import User, UserRole

Cell = tuple[Access, str | None] | None

ROLES = (
    UserRole.ADMIN,
    UserRole.PROCUREMENT_MANAGER,
    UserRole.DEPT_MANAGER,
    UserRole.EMPLOYEE,
)

_A = (Access.ALL, None)
_D = (Access.DEPT, None)

# Columnes: admin, procurement_manager, dept_manager, employee.
TRUTH_TABLE: dict[str, tuple[Cell, Cell, Cell, Cell]] = {
    # Contractes
    "contracts:read": (_A, _A, _D, _D),
    "contracts:create": (_A, _A, None, None),
    "contracts:update": (_A, _A, None, None),
    "contracts:update_warning": (_A, _A, _D, None),
    "contracts:assign": (_A, _A, None, None),
    "contracts:bulk_assign": (_A, _A, None, None),
    "contracts:close_alert": (_A, _A, (Access.MANAGED, None), None),
    "contracts:enrich": (_A, _A, None, None),
    "contracts:export": (_A, _A, _D, _D),
    "contracts:open_gestiona": (_A, _A, None, None),
    # Menors
    "minor_contracts:read": (_A, _A, _D, _D),
    "minor_contracts:update": (_A, _A, None, None),
    # Duplicats
    "duplicates:manage": (_A, _A, None, None),
    # Sincronització
    "sync:execute": (_A, _A, None, None),
    "sync:read": (_A, _A, None, None),
    "association_rules:manage": (_A, _A, None, None),
    # Organització
    "departments:read": (_A, _A, _A, _A),
    "departments:write": (_A, _A, None, None),
    "users:read": (_A, None, None, None),  # ⚠️ divergència v1→v2: només admin
    "users:write": (_A, None, None, None),
    "me:update": (_A, _A, _A, _A),
    # Configuració
    "config:read": (_A, _A, _A, _A),
    "config:write": (_A, None, None, None),
    "webhooks:manage": (_A, None, None, None),
    # Pla anual
    "plan:read": (_A, _A, _D, (Access.DEPT, "can_plan")),
    "plan:write": (_A, _A, (Access.DEPT, "can_plan"), (Access.DEPT, "can_plan")),
    "plan:approve": (_A, None, None, None),
    # Auditoria de contractació
    "audit:run": (
        _A,
        (Access.ALL, "can_audit"),
        (Access.DEPT, "can_audit"),
        (Access.DEPT, "can_audit"),
    ),
    # Auditoria de seguretat
    "audit_log:read": (_A, None, None, None),
    # Tasques
    "tasks:read": (_A, _A, _D, (Access.ASSIGNED, None)),
    "tasks:write": (_A, _A, _D, None),
    "tasks:update_status": (_A, _A, (Access.ASSIGNED, None), (Access.ASSIGNED, None)),
    # Revisió legal
    "compliance:run": (_A, _A, _D, None),
    "compliance:manage": (_A, None, None, None),
    # Eines d'ús propi
    "tools:use": (_A, _A, _A, _A),
    # Sistema
    "system:read": (_A, None, None, None),
}


def _user(role: UserRole, *, can_audit: bool = False, can_plan: bool = False) -> User:
    return User(role=role, can_audit=can_audit, can_plan=can_plan)


def test_matrix_and_truth_table_cover_the_same_actions() -> None:
    assert set(TRUTH_TABLE) == set(authz.PERMISSION_MATRIX)


@pytest.mark.parametrize(
    ("action", "role", "expected"),
    [
        (action, role, cells[i])
        for action, cells in TRUTH_TABLE.items()
        for i, role in enumerate(ROLES)
    ],
)
def test_matrix_cell(action: str, role: UserRole, expected: Cell) -> None:
    without_flags = authz.evaluate(_user(role), action)
    with_flags = authz.evaluate(_user(role, can_audit=True, can_plan=True), action)

    if expected is None:
        assert without_flags is None
        assert with_flags is None
        return

    access, required_flag = expected
    assert with_flags is not None and with_flags.access == access
    if required_flag is None:
        assert without_flags is not None and without_flags.access == access
    else:
        # Sense el flag, l'acció desapareix.
        assert without_flags is None


def test_allowed_actions_respects_flags() -> None:
    employee = _user(UserRole.EMPLOYEE)
    auditor = _user(UserRole.EMPLOYEE, can_audit=True)

    assert "audit:run" not in authz.allowed_actions(employee)
    assert "audit:run" in authz.allowed_actions(auditor)


def test_scope_full_roles() -> None:
    for role in (UserRole.ADMIN, UserRole.PROCUREMENT_MANAGER):
        scope = authz.scope_for(_user(role))
        assert scope.type == "all"
        assert authz.can_switch_view(_user(role))


def test_scope_departmental_roles_default_to_empty() -> None:
    # Sense departaments: llista buida, mai «tot» (A2 §3).
    for role in (UserRole.DEPT_MANAGER, UserRole.EMPLOYEE):
        scope = authz.scope_for(_user(role))
        assert scope.type == "departments"
        assert scope.department_ids == []
        assert not authz.can_switch_view(_user(role))


def test_authorize_rejects_unknown_action() -> None:
    with pytest.raises(ValueError, match="desconeguda"):
        authz.Authorize("inventada:acció")
