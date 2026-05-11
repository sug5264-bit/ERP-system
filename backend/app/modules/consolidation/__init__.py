"""연결재무제표 (Consolidated financial statements) + 세무조정.

Each legal entity (자회사 포함) is represented by a tenant. The consolidation
endpoint sums per-entity trial balances then strips intercompany transactions.
"""
