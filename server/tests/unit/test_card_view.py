from nightwatch.domain.explain import explain
from nightwatch.domain.fixtures import FIXTURE_INCIDENTS
from nightwatch.domain.incidents import deploy_versions, to_view
from nightwatch_core.models import Evidence

from .helpers import incident


def _prod(detail: str):
    inc = incident("inc_p", "checkout-service latency", kind="prod")
    return inc.model_copy(
        update={"evidence": [Evidence(type="deploy_proximity", detail=detail, weight=0.6)]}
    )


def test_deploy_versions_from_rules_detail() -> None:
    inc = _prod("Latency rose 4 minutes after deployment d-3869LHKLL (v2→v3); no other service")
    assert deploy_versions(inc) == "v2→v3"
    assert to_view(inc).deploy_versions == "v2→v3"


def test_deploy_versions_none_for_hazards_and_unparseable() -> None:
    assert deploy_versions(incident("inc_h", "Red Flag Warning")) is None
    assert deploy_versions(_prod("Latency rose after a deploy")) is None


def test_explanation_carries_the_card_view() -> None:
    prod = next(i for i in FIXTURE_INCIDENTS if i.kind == "prod")
    exp = explain(prod, "brief")
    assert exp.incident == to_view(prod)
    assert exp.incident.deploy_versions == "v42→v43"
