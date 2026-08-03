"""Role and permission entities for Role-Based Access Control (RBAC).

Sentrix uses enterprise roles with explicit permission grants. Roles are
referenced from JWT claims so that authorization can be enforced without a
database round-trip on every request.
"""

from __future__ import annotations

import enum


class RoleName(str, enum.Enum):
    """Enterprise roles defined by the Sentrix platform."""

    ADMIN = "admin"
    SOC_ANALYST = "soc_analyst"
    THREAT_HUNTER = "threat_hunter"
    DFIR = "dfir"
    RED_TEAM = "red_team"
    BLUE_TEAM = "blue_team"
    SECURITY_ENGINEER = "security_engineer"
    MANAGER = "manager"

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# Permission catalog
# ---------------------------------------------------------------------------
# Permissions follow a ``<resource>:<action>`` convention, e.g. ``users:read``,
# ``alerts:contain``. New permissions are added to the catalog before they can
# be granted to roles.
# ---------------------------------------------------------------------------

# User & RBAC
USERS_READ = "users:read"
USERS_WRITE = "users:write"
ROLES_MANAGE = "roles:manage"

# Platform
DASHBOARD_VIEW = "dashboard:view"
AUDIT_READ = "audit:read"

# Security operations
ALERTS_READ = "alerts:read"
ALERTS_TRIAGE = "alerts:triage"
ALERTS_CONTAIN = "alerts:contain"
INVESTIGATIONS_READ = "investigations:read"
INVESTIGATIONS_WRITE = "investigations:write"
HUNTS_RUN = "hunts:run"
FORENSICS_RUN = "forensics:run"
TOOLS_EXECUTE = "tools:execute"
REPORTS_GENERATE = "reports:generate"
AGENTS_RUN = "agents:run"

# Tool engine resources
FILESYSTEM_READ = "filesystem:read"
FILESYSTEM_WRITE = "filesystem:write"
TERMINAL_EXECUTE = "terminal:execute"
PYTHON_EXECUTE = "python:execute"

# Integration & admin
INTEGRATIONS_MANAGE = "integrations:manage"
BILLING_MANAGE = "billing:manage"


class Role:
    """A named role with an explicit set of granted permissions."""

    __slots__ = ("name", "permissions", "description")

    def __init__(
        self,
        name: RoleName | str,
        permissions: set[str],
        description: str = "",
    ) -> None:
        self.name = str(name)
        self.permissions = permissions
        self.description = description

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


# ---------------------------------------------------------------------------
# Role catalog
# ---------------------------------------------------------------------------
# Admins have broad platform permissions. Operational roles are scoped to the
# domains they own. Grants are explicit — never wildcard — for auditability.
# ---------------------------------------------------------------------------

ROLE_CATALOG: dict[str, Role] = {
    RoleName.ADMIN.value: Role(
        RoleName.ADMIN,
        {
            USERS_READ,
            USERS_WRITE,
            ROLES_MANAGE,
            DASHBOARD_VIEW,
            AUDIT_READ,
            ALERTS_READ,
            ALERTS_TRIAGE,
            ALERTS_CONTAIN,
            INVESTIGATIONS_READ,
            INVESTIGATIONS_WRITE,
            HUNTS_RUN,
            FORENSICS_RUN,
            TOOLS_EXECUTE,
            FILESYSTEM_READ,
            FILESYSTEM_WRITE,
            TERMINAL_EXECUTE,
            PYTHON_EXECUTE,
            REPORTS_GENERATE,
            AGENTS_RUN,
            INTEGRATIONS_MANAGE,
            BILLING_MANAGE,
        },
        "Full platform administration.",
    ),
    RoleName.SOC_ANALYST.value: Role(
        RoleName.SOC_ANALYST,
        {
            DASHBOARD_VIEW,
            ALERTS_READ,
            ALERTS_TRIAGE,
            INVESTIGATIONS_READ,
            INVESTIGATIONS_WRITE,
            REPORTS_GENERATE,
        },
        "Tiered SOC analyst: triage, investigate, and report.",
    ),
    RoleName.THREAT_HUNTER.value: Role(
        RoleName.THREAT_HUNTER,
        {
            DASHBOARD_VIEW,
            ALERTS_READ,
            INVESTIGATIONS_READ,
            HUNTS_RUN,
            REPORTS_GENERATE,
        },
        "Proactive threat hunting across telemetry.",
    ),
    RoleName.DFIR.value: Role(
        RoleName.DFIR,
        {
            DASHBOARD_VIEW,
            ALERTS_READ,
            INVESTIGATIONS_READ,
            INVESTIGATIONS_WRITE,
            FORENSICS_RUN,
            TOOLS_EXECUTE,
            REPORTS_GENERATE,
        },
        "Digital forensics and incident response.",
    ),
    RoleName.RED_TEAM.value: Role(
        RoleName.RED_TEAM,
        {
            DASHBOARD_VIEW,
            INVESTIGATIONS_READ,
            TOOLS_EXECUTE,
            REPORTS_GENERATE,
        },
        "Offensive security assessments and controlled tooling.",
    ),
    RoleName.BLUE_TEAM.value: Role(
        RoleName.BLUE_TEAM,
        {
            DASHBOARD_VIEW,
            ALERTS_READ,
            ALERTS_TRIAGE,
            ALERTS_CONTAIN,
            INVESTIGATIONS_READ,
            INVESTIGATIONS_WRITE,
            REPORTS_GENERATE,
        },
        "Defensive security operations.",
    ),
    RoleName.SECURITY_ENGINEER.value: Role(
        RoleName.SECURITY_ENGINEER,
        {
            DASHBOARD_VIEW,
            ALERTS_READ,
            INVESTIGATIONS_READ,
            TOOLS_EXECUTE,
            INTEGRATIONS_MANAGE,
            REPORTS_GENERATE,
        },
        "Instrumentation, integrations, and tooling.",
    ),
    RoleName.MANAGER.value: Role(
        RoleName.MANAGER,
        {
            DASHBOARD_VIEW,
            ALERTS_READ,
            INVESTIGATIONS_READ,
            AUDIT_READ,
            REPORTS_GENERATE,
        },
        "Read-only oversight: dashboards, audit, and reports.",
    ),
}


def get_role(role_name: str) -> Role | None:
    """Return the role definition for a role name, or ``None`` if unknown."""
    return ROLE_CATALOG.get(role_name)


def get_role_permissions(role_name: str) -> list[str]:
    """Return the sorted permission list for a role (used in JWT claims)."""
    role = get_role(role_name)
    return sorted(role.permissions) if role else []

