from decimal import Decimal, InvalidOperation


def format_money(value, household=None) -> str:
    """Format a Decimal as currency, e.g. ``1234.5`` -> ``$1,234.50``."""
    try:
        amount = Decimal(value if value not in (None, "") else "0")
    except (InvalidOperation, TypeError, ValueError):
        return ""
    symbol = household.currency_symbol if household is not None else "$"
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol}{abs(amount):,.2f}"
