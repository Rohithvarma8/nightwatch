"""MCP Apps incident card: one self-contained ui:// HTML resource, read once at init."""

from importlib.resources import files

from mcp.server.apps import Apps

CARD_URI = "ui://nightwatch/incidents.html"


def card_html() -> str:
    return files("nightwatch.ui").joinpath("incidents.html").read_text(encoding="utf-8")


def register(apps: Apps) -> None:
    apps.add_html_resource(
        CARD_URI,
        card_html(),
        name="incidents",
        title="Night Watch incident card",
        description="Severity, summary, top action, evidence, status, and escalation countdown.",
        prefers_border=True,
    )
