"""Seed the demo household: `python -m nightwatch_pipeline.seed --table <name>`."""

import argparse

from nightwatch_core.models import Contact, ContactChannels, EscalationPolicy, Household, Zone
from nightwatch_pipeline.store import Store

# Simi Valley, CA. Verified 2026-10-15 with https://api.weather.gov/points/34.2694,-118.7815:
# forecastZone CAZ374 and fireWeatherZone CAZ374, both named "Southeastern Ventura County
# Valleys"; county CAC111 (Ventura); timeZone America/Los_Angeles.
DEMO_HOUSEHOLD = Household(
    id="hh_demo",
    name="Demo Household",
    tz="America/Los_Angeles",
    lat=34.2694,
    lon=-118.7815,
    location="Ventura County, Southeastern Ventura County Valleys (Simi Valley area)",
    forecast_zone=Zone(id="CAZ374", name="Southeastern Ventura County Valleys"),
    fire_zone=Zone(id="CAZ374", name="Southeastern Ventura County Valleys"),
    county="CAC111",
    ack_timeout_s=120,  # demo: escalate after 2 minutes (default 600)
)


def demo_contact(email: str | None) -> Contact:
    """Priya, the roommate. Push goes to the household ntfy topic (SSM); email from tfvars."""
    return Contact(
        id="c_priya",
        household_id=DEMO_HOUSEHOLD.id,
        name="Priya",
        aliases=["roommate"],
        channels=ContactChannels(ntfy=True, email=email),
        escalation_order=1,
    )


DEMO_POLICY = EscalationPolicy(
    household_id=DEMO_HOUSEHOLD.id, min_severity="high", contact_ids=["c_priya"]
)


def seed(store: Store, contact_email: str | None, ack_timeout_s: int) -> str:
    household = DEMO_HOUSEHOLD.model_copy(update={"ack_timeout_s": ack_timeout_s})
    store.put_household(household)
    store.put_contact(demo_contact(contact_email))
    store.put_policy(DEMO_POLICY)
    email = "with email" if contact_email else "push only"
    return (
        f"seeded {household.id} ({household.name}), contact Priya ({email}), "
        f"escalation policy (high+, {household.ack_timeout_s}s)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True)
    parser.add_argument("--contact-email", default=None, help="Priya's email (from tfvars)")
    parser.add_argument("--ack-timeout-s", type=int, default=DEMO_HOUSEHOLD.ack_timeout_s)
    args = parser.parse_args()
    seeded = seed(Store(args.table), args.contact_email or None, args.ack_timeout_s)
    print(f"{seeded} into {args.table}")


if __name__ == "__main__":
    main()
