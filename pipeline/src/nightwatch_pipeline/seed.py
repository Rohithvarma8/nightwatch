"""Seed the demo household: `python -m nightwatch_pipeline.seed --table <name>`."""

import argparse

from nightwatch_core.models import Household, Zone
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
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True)
    args = parser.parse_args()
    Store(args.table).put_household(DEMO_HOUSEHOLD)
    print(f"seeded {DEMO_HOUSEHOLD.id} ({DEMO_HOUSEHOLD.name}) into {args.table}")


if __name__ == "__main__":
    main()
