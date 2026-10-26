"""Rebuild the committed ProPublica cache from the live API (not needed to run the app).

Run from backend/ with the project's Python, for example:
  python -m app.tools.refresh_cache            # featured charities plus two mapping-test filers
  python -m app.tools.refresh_cache 222511873  # specific EINs
Requests are sequential with a pause between them to stay polite to the free API. Refreshing changes the
data behind saved runs, so do it before recording evidence, not after.
"""

from __future__ import annotations

import asyncio
import sys

from app.tools import propublica

# Small real filers kept in the cache so tests cover the 990EZ and 990PF field mappings.
MAPPING_TEST_EINS: tuple[str, ...] = (
    "061527913",  # Ridgefield Garden Club Inc, Form 990EZ
    "061603158",  # Halvorsen Family Foundation, Form 990PF
)
PAUSE_S = 1.0


async def refresh(eins: list[str]) -> int:
    failures = 0
    for ein in eins:
        try:
            profile = await propublica.get_org_profile(ein, require_filings=False, refresh=True)
        except propublica.OrgNotFound as exc:
            failures += 1
            print(f"{ein}: FAILED ({exc})")
        else:
            latest = profile.filings[0] if profile.filings else None
            print(
                f"{ein}: {profile.name} | filings with data: {len(profile.filings)} | "
                f"latest tax year: {latest.tax_year if latest else None} | "
                f"latest revenue: {latest.total_revenue if latest else None}"
            )
        await asyncio.sleep(PAUSE_S)
    return failures


def main(argv: list[str]) -> int:
    if propublica.offline_mode():
        print("OFFLINE_MODE=1 is set; unset it to refresh the cache.")
        return 1
    eins = argv or [*propublica.FEATURED_EINS, *MAPPING_TEST_EINS]
    return 1 if asyncio.run(refresh(eins)) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
