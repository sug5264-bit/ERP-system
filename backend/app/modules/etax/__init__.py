"""Korean electronic tax invoice (전자세금계산서) issuance.

Mirrors the NTS Hometax data model. The actual submission to Hometax is
abstracted behind `submit()` so tests can run without external dependencies.
"""
