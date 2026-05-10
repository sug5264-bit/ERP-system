"""Foreign exchange rates + multi-currency conversion helpers.

Conventions:
  • Base currency for the books is set in core.config (default KRW).
  • Rates are stored as `from_ccy → to_ccy` with a `rate` (Decimal).
    To convert 100 USD → KRW: lookup USD→KRW rate and multiply.
"""
