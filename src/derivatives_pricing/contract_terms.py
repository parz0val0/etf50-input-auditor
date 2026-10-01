"""Retrospective known-event guard, not a complete historical contract master."""
from datetime import date
from math import isfinite
KNOWN_ADJUSTMENTS = (
 ('2023-11-27', 'https://www.sse.com.cn/assortment/options/disclo/update/c/c_20231124_5730762.shtml'),
 ('2024-12-02', 'https://www.sse.com.cn/assortment/options/disclo/update/c/c_20241129_10765181.shtml'),
 ('2025-12-17', 'https://star.sse.com.cn/assortment/options/disclo/update/c/c_20251216_10801845.shtml'),
)
# Only this retrospective 2024 event inventory has been reviewed locally.
# This is a necessary scenario guard, never certification of the full data contract.
REVIEWED_COVERAGE = ("2024-01-01", "2024-12-31")
REVIEWED_2024_EVENT_DATES = frozenset(("2024-12-02",))

def static_terms_eligible(row):
    unit = row.get('contract_unit')
    if row.get('adjustment_flag') != 'M' or not isinstance(unit, (int,float)) or not isfinite(unit) or unit != 10000:
        return False, 'adjusted_or_unverified_unit'
    try:
        observed, expiry = date.fromisoformat(row['date']), date.fromisoformat(row['expiry'])
    except (KeyError,TypeError,ValueError):
        return False, 'missing_or_invalid_contract_dates'
    if expiry <= observed:
        return False, 'invalid_contract_tenor'
    inventory = frozenset(e for e,_ in KNOWN_ADJUSTMENTS if REVIEWED_COVERAGE[0] <= e <= REVIEWED_COVERAGE[1])
    if not KNOWN_ADJUSTMENTS or inventory != REVIEWED_2024_EVENT_DATES:
        return False, 'unverified_adjustment_inventory'
    if not (date.fromisoformat(REVIEWED_COVERAGE[0]) <= observed < expiry <= date.fromisoformat(REVIEWED_COVERAGE[1])):
        return False, 'outside_reviewed_adjustment_coverage'
    if any(observed == date.fromisoformat(e) for e,_ in KNOWN_ADJUSTMENTS):
        # M/10000 alone does not attest the effective event-day contract master.
        return False, 'event_day_terms_not_verified'
    if any(observed < date.fromisoformat(effective) <= expiry for effective,_ in KNOWN_ADJUSTMENTS):
        return False, 'crosses_contract_adjustment'
    return True, 'eligible'
