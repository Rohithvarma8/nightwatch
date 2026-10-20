"""DynamoDB single-table key layout (DESIGN.md §3). Pure string builders."""

from nightwatch_core.models import SEVERITY_RANK, Severity

META = "META"
PROFILE = "PROFILE"
GSI1 = "GSI1"


def household_pk(household_id: str) -> str:
    return f"HH#{household_id}"


def incident_pk(incident_id: str) -> str:
    return f"INC#{incident_id}"


def event_sk(at: str, event_id: str) -> str:
    return f"EVT#{at}#{event_id}"


def contact_sk(contact_id: str) -> str:
    return f"CONTACT#{contact_id}"


CONTACT_PREFIX = "CONTACT#"
ESCALATION_POLICY = "POLICY#escalation"


def rate_pk(household_id: str, contact_id: str) -> str:
    """Notification rate-limit counter (one item per contact per clock hour)."""
    return f"RATE#{household_id}#{contact_id}"


def service_pk(service: str) -> str:
    return f"SVC#{service}"


def deploy_sk(ended_at: str, deployment_id: str) -> str:
    return f"DEPLOY#{ended_at}#{deployment_id}"


def signal_pk(source: str, external_id: str) -> str:
    return f"SIG#{source}#{external_id}"


def openkey_sk(correlation_key: str) -> str:
    return f"OPENKEY#{correlation_key}"


def active_gsi1_pk(household_id: str) -> str:
    return f"HH#{household_id}#ACTIVE"


def active_gsi1_sk(severity: Severity, started_at: str) -> str:
    """Ascending sort = most severe first, then oldest first."""
    return f"{SEVERITY_RANK[severity]}#{started_at}"
