"""Pre-built KPI library + drill-down queries.

Each KPI is a Python callable registered with a `code`, returning a single
scalar (number) + optional dimensions for drill-down (e.g., by month, by
warehouse). The library is curated rather than user-built, complementing the
generic Report Builder.
"""
