"""Pure date logic for recurring schedules (no database access)."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from .models import Frequency

STEP = {
    Frequency.WEEKLY: relativedelta(weeks=1),
    Frequency.MONTHLY: relativedelta(months=1),
    Frequency.QUARTERLY: relativedelta(months=3),
    Frequency.ANNUAL: relativedelta(years=1),
}

# Average occurrences per month, for "monthly equivalent" summaries.
PER_MONTH = {
    Frequency.WEEKLY: Decimal(52) / Decimal(12),
    Frequency.MONTHLY: Decimal(1),
    Frequency.QUARTERLY: Decimal(1) / Decimal(3),
    Frequency.ANNUAL: Decimal(1) / Decimal(12),
}


def occurrences(
    start: date,
    frequency: str,
    *,
    window_start: date,
    window_end: date,
    end_date: date | None = None,
) -> Iterator[date]:
    """Yield due dates of a schedule that fall inside ``[window_start, window_end]``.

    Each occurrence is computed from ``start`` (``start + n * step``) rather than
    from the previous occurrence, so a bill due on the 31st lands on the last
    day of short months and returns to the 31st afterwards instead of drifting.
    """
    step = STEP[Frequency(frequency)]
    last = min(window_end, end_date) if end_date else window_end
    n = 0
    while True:
        due = start + step * n
        if due > last:
            return
        if due >= window_start:
            yield due
        n += 1
