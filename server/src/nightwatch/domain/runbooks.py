"""Runbooks (runbooks/*.yaml): loaded once at init, matched to incidents deterministically."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from nightwatch_core.models import Incident


class RunbookMatch(BaseModel):
    titles: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    families: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)


class RunbookStep(BaseModel):
    action: str
    why: str


class Runbook(BaseModel):
    id: str
    title: str
    match: RunbookMatch
    steps: list[RunbookStep] = Field(min_length=1)


def runbooks_dir() -> Path:
    """NIGHTWATCH_RUNBOOKS_DIR, else <zip root>/runbooks (Lambda), else <repo>/runbooks."""
    if env := os.environ.get("NIGHTWATCH_RUNBOOKS_DIR"):
        return Path(env)
    here = Path(__file__).resolve()
    for root in (here.parents[2], here.parents[4]):  # /var/task, or the repo root
        if (root / "runbooks").is_dir():
            return root / "runbooks"
    raise FileNotFoundError("runbooks/ directory not found")


def load_runbooks(directory: Path | None = None) -> dict[str, Runbook]:
    directory = directory or runbooks_dir()
    books = {}
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        books[path.stem] = Runbook(id=path.stem, **data)
    return books


def _primary_family(incident: Incident) -> str | None:
    primary = [r for r in incident.signals if r.role == "primary" and r.hazard_family]
    return primary[-1].hazard_family if primary else None


def runbook_for(incident: Incident, runbooks: dict[str, Runbook]) -> Runbook | None:
    """Title (e.g. "Fire risk") → event → primary hazard family → kind."""
    books = list(runbooks.values())
    family = _primary_family(incident)
    for matches in (
        lambda b: incident.title in b.match.titles,
        lambda b: incident.title in b.match.events,
        lambda b: family is not None and family in b.match.families,
        lambda b: incident.kind in b.match.kinds,
    ):
        found = next((b for b in books if matches(b)), None)
        if found:
            return found
    return None
