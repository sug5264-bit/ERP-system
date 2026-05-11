"""AI-assisted journal-entry suggestion.

Given a free-text invoice description (or OCR'd text), proposes a balanced
journal entry by mapping vocabulary to existing Account codes. Designed as
an adapter — the default is a rule-based heuristic; a production deploy can
swap in an LLM call by overriding `propose_entry`.
"""
