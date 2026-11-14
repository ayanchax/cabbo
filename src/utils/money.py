from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

MONEY_PRECISION = Decimal("0.01")
def subunits(value, factor):
    return int((Decimal(str(value)) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def to_decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount >= 0 else None
    except (InvalidOperation, ValueError):
        return None