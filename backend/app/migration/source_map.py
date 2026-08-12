"""Mapa de l'esquema v1 (specs/v1-migration.md).

ÚNIC lloc amb noms de taules/columnes de la v1, transcrits de docs/02.
El primer assaig amb una còpia real de producció ha de validar-los;
si difereixen, només es toca aquest fitxer. Els tests construeixen
l'esquema sintètic amb `synthetic_ddl()` — mateixa font de veritat.
"""

# Esquema on viuen les taules a l'origen ("public" a producció; els
# tests el sobreescriuen per aïllar-se).
DEFAULT_SCHEMA = "public"

TABLES = {
    "departments": "departamentos",
    "users": "usuarios",
    "user_departments": "usuarios_departamentos",
    "contracts": "contratos",
    "contract_departments": "contratos_departamentos",
    "contract_managers": "contratos_responsables",
    "minor_contracts": "contratos_menores",
    "minor_contract_departments": "contratos_menores_departamentos",
}

ROLE_MAP = {
    "admin": "admin",
    "responsable_contratacion": "procurement_manager",
    "responsable": "dept_manager",
    "empleado": "employee",
}

INTERNAL_STATUS_MAP = {
    "normal": "normal",
    "pendiente_aprobacion": "pending_review",
    "aprobado": "approved",
    "rechazado": "rejected",
}

# SELECTs de lectura (només columnes que la v2 necessita).
SELECTS = {
    "departments": "SELECT id, nombre FROM {schema}.departamentos ORDER BY id",
    "users": (
        "SELECT id, nombre, email, rol, dni, activo, "
        "permiso_auditoria, permiso_pla_contractacio "
        "FROM {schema}.usuarios ORDER BY id"
    ),
    "user_departments": ("SELECT usuario_id, departamento_id FROM {schema}.usuarios_departamentos"),
    "contracts": (
        "SELECT id, expediente, estado, COALESCE(lote, '') AS lote, objeto, "
        "tipo_contrato, procedimiento, adjudicatario, nif_adjudicatario, "
        "importe_adjudicacion, fecha_publicacion, fecha_inicio, fecha_fin, "
        "estado_interno, meses_aviso_vencimiento "
        "FROM {schema}.contratos ORDER BY id"
    ),
    "contract_departments": (
        "SELECT contrato_id, departamento_id FROM {schema}.contratos_departamentos"
    ),
    "contract_managers": ("SELECT contrato_id, usuario_id FROM {schema}.contratos_responsables"),
    "minor_contracts": (
        "SELECT id, expediente, estado_interno FROM {schema}.contratos_menores ORDER BY id"
    ),
    "minor_contract_departments": (
        "SELECT contrato_menor_id, departamento_id FROM {schema}.contratos_menores_departamentos"
    ),
}


def select_sql(entity: str, schema: str) -> str:
    if not schema.replace("_", "").isalnum():
        raise ValueError(f"esquema d'origen invàlid: {schema!r}")
    return SELECTS[entity].format(schema=schema)


def synthetic_ddl(schema: str) -> list[str]:
    """DDL mínim per als tests (mateixos noms que el mapa)."""
    s = schema
    return [
        f"CREATE SCHEMA IF NOT EXISTS {s}",
        f"CREATE TABLE {s}.departamentos (id serial PRIMARY KEY, nombre text NOT NULL)",
        (
            f"CREATE TABLE {s}.usuarios (id serial PRIMARY KEY, nombre text, "
            "email text NOT NULL, rol text NOT NULL, dni text, activo boolean DEFAULT true, "
            "permiso_auditoria boolean DEFAULT false, "
            "permiso_pla_contractacio boolean DEFAULT false)"
        ),
        (f"CREATE TABLE {s}.usuarios_departamentos (usuario_id int, departamento_id int)"),
        (
            f"CREATE TABLE {s}.contratos (id serial PRIMARY KEY, expediente text NOT NULL, "
            "estado text NOT NULL, lote text, objeto text, tipo_contrato text, "
            "procedimiento text, adjudicatario text, nif_adjudicatario text, "
            "importe_adjudicacion numeric(15,2), fecha_publicacion date, "
            "fecha_inicio date, fecha_fin date, estado_interno text DEFAULT 'normal', "
            "meses_aviso_vencimiento int)"
        ),
        (f"CREATE TABLE {s}.contratos_departamentos (contrato_id int, departamento_id int)"),
        (f"CREATE TABLE {s}.contratos_responsables (contrato_id int, usuario_id int)"),
        (
            f"CREATE TABLE {s}.contratos_menores (id serial PRIMARY KEY, "
            "expediente text NOT NULL, estado_interno text DEFAULT 'normal')"
        ),
        (
            f"CREATE TABLE {s}.contratos_menores_departamentos ("
            "contrato_menor_id int, departamento_id int)"
        ),
    ]
