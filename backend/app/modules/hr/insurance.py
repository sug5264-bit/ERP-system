"""4대보험 (Korean social insurance) calculator.

Rates are based on 2026 reference values (employee share):
    국민연금 (NPS):    4.5% capped at 590만원 base
    건강보험 (NHI):    3.545%
    장기요양 (LTCI):   12.95% of NHI
    고용보험 (EI):     0.9%

산재보험 (industrial accident) is employer-only and not deducted.
"""
from decimal import Decimal

NPS_RATE = Decimal("0.045")
NPS_CAP = Decimal("5900000")  # monthly cap
NHI_RATE = Decimal("0.03545")
LTCI_OF_NHI = Decimal("0.1295")
EI_RATE = Decimal("0.009")


def calculate_4_insurances(gross: Decimal) -> dict[str, Decimal]:
    """Return employee-share contributions, all rounded to KRW (no decimals)."""
    g = Decimal(gross)
    nps_base = min(g, NPS_CAP)
    nps = (nps_base * NPS_RATE).quantize(Decimal("1"))
    nhi = (g * NHI_RATE).quantize(Decimal("1"))
    ltci = (nhi * LTCI_OF_NHI).quantize(Decimal("1"))
    ei = (g * EI_RATE).quantize(Decimal("1"))
    total = nps + nhi + ltci + ei
    return {"nps": nps, "nhi": nhi, "ltci": ltci, "ei": ei, "total": total}
