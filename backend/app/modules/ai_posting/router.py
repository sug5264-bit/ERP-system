"""AI posting suggestion endpoint."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_internal_user, require_role
from app.core.db import get_db
from app.modules.finance.models import Account, AccountType


router = APIRouter(
    prefix="/api/ai-posting",
    tags=["ai-posting"],
    dependencies=[Depends(get_current_internal_user)],
)


# Test hook: when set, _llm_propose uses this client instead of constructing
# a real anthropic.Anthropic(). Lets unit tests inject a fake.
_ANTHROPIC_CLIENT = None


def set_anthropic_client(client) -> None:
    """Test hook to inject a stub Anthropic client."""
    global _ANTHROPIC_CLIENT
    _ANTHROPIC_CLIENT = client


# ---- Heuristic rules ------------------------------------------------------
# Keyword → account-code mapping. First matching rule wins. Production should
# replace this with an LLM-based classifier.
_RULES: list[tuple[list[str], str, str]] = [
    # (keywords, debit_code, credit_code) for the typical entry shape.
    # Cash receipt = Dr 현금 / Cr Revenue
    (["입금", "수금", "현금 받음", "receipt"], "1100", "4100"),
    # Office supply / stationery → expense
    (["문구", "사무용품", "office supply", "stationery"], "5110", "1100"),
    # Travel / 교통비
    (["교통비", "택시", "taxi", "출장"], "5120", "1100"),
    # 식대 / meal
    (["식대", "회식", "점심", "meal", "lunch", "dinner"], "5130", "1100"),
    # 임대료 / rent
    (["임대료", "월세", "rent", "임차료"], "5140", "1100"),
    # 통신비 / phone
    (["통신비", "전화", "인터넷", "phone", "internet"], "5150", "1100"),
    # 인건비 — payroll
    (["급여", "월급", "payroll", "임금"], "5200", "1100"),
    # 매입 — purchase from supplier
    (["매입", "purchase", "원료", "raw material"], "1300", "2100"),
    # 세금 / tax
    (["부가세", "vat", "tax", "세금"], "2150", "1100"),
]


class ProposalIn(BaseModel):
    description: str
    amount: Decimal
    tax_amount: Decimal | None = None


class ProposalLine(BaseModel):
    account_code: str
    account_name: str | None = None
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


class Proposal(BaseModel):
    description: str
    confidence: float  # 0-1
    matched_rule: str | None = None
    lines: list[ProposalLine]


def propose_entry(db: Session, description: str, amount: Decimal,
                  tax_amount: Decimal | None = None) -> Proposal:
    """Default heuristic mapping. If `ANTHROPIC_API_KEY` is set, swap in the
    LLM-based proposer; falls back to heuristic on any error."""
    import os
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _llm_propose(db, description, amount, tax_amount)
        except Exception:
            import logging
            logging.getLogger("erp.ai_posting").exception(
                "LLM proposal failed, falling back to heuristic"
            )
    return _heuristic_propose(db, description, amount, tax_amount)


def _llm_propose(db: Session, description: str, amount: Decimal,
                 tax_amount: Decimal | None = None) -> Proposal:
    """LLM-driven proposal using Anthropic Claude.

    We hand the LLM the Chart of Accounts and ask it to pick debit/credit
    accounts + line amounts. The result is validated (balanced, valid codes)
    before being returned. Any validation failure raises and the caller falls
    back to the rule-based path.
    """
    import json as _json

    # Only import the real SDK when we need to construct a fresh client.
    # Tests inject _ANTHROPIC_CLIENT directly and avoid the dependency.
    if _ANTHROPIC_CLIENT is None:
        import anthropic
    else:
        anthropic = None  # not needed

    accounts = db.query(Account).order_by(Account.code).all()
    coa_text = "\n".join(
        f"{a.code} {a.name} ({a.type.value if hasattr(a.type, 'value') else a.type})"
        for a in accounts
    )

    prompt = f"""You are a Korean accountant. Given the description and amount,
produce a balanced journal entry by selecting debit and credit accounts from
the chart of accounts below.

Chart of accounts:
{coa_text}

Transaction:
- Description: {description}
- Amount: {amount} KRW
- VAT (if applicable): {tax_amount or 0} KRW

Respond ONLY with JSON in this exact shape:
{{"lines": [{{"account_code": "1234", "debit": 0, "credit": 0}}, ...],
  "confidence": 0.0-1.0, "rationale": "short Korean rationale"}}
Each line must use codes from the chart. Debits must equal credits.
"""

    client = _ANTHROPIC_CLIENT if _ANTHROPIC_CLIENT is not None else anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text if msg.content else "{}"
    # Strip Markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    data = _json.loads(text)

    by_code = {a.code: a for a in accounts}
    lines: list[ProposalLine] = []
    total_dr = total_cr = Decimal("0")
    for ln in data.get("lines", []):
        acc = by_code.get(ln.get("account_code"))
        if not acc:
            raise ValueError(f"LLM picked unknown account {ln.get('account_code')}")
        d = Decimal(str(ln.get("debit", 0) or 0))
        c = Decimal(str(ln.get("credit", 0) or 0))
        total_dr += d
        total_cr += c
        lines.append(ProposalLine(
            account_code=acc.code, account_name=acc.name, debit=d, credit=c,
        ))
    if total_dr != total_cr:
        raise ValueError(f"LLM produced unbalanced entry: dr {total_dr} != cr {total_cr}")
    if not lines:
        raise ValueError("LLM produced no lines")

    return Proposal(
        description=description,
        confidence=float(data.get("confidence", 0.75)),
        matched_rule=f"LLM: {data.get('rationale', '')[:80]}",
        lines=lines,
    )


def _heuristic_propose(db: Session, description: str, amount: Decimal,
                        tax_amount: Decimal | None = None) -> Proposal:
    """Heuristic mapping based on keyword rules — the deterministic fallback."""
    desc_lower = description.lower()
    matched_keyword = None
    debit_code = credit_code = None
    for keywords, dc, cc in _RULES:
        for kw in keywords:
            if kw.lower() in desc_lower:
                matched_keyword = kw
                debit_code = dc
                credit_code = cc
                break
        if matched_keyword:
            break

    if not matched_keyword:
        # Fallback: ambiguous → cash + suspense
        debit_code, credit_code = "5900", "1100"  # 잡손실/잡비 / 현금
        confidence = 0.1
    else:
        confidence = 0.7

    def _lookup(code: str) -> Account | None:
        return db.query(Account).filter(Account.code == code).first()

    debit_acc = _lookup(debit_code)
    credit_acc = _lookup(credit_code)
    lines: list[ProposalLine] = []
    if tax_amount and tax_amount > 0:
        # Split when VAT is provided
        # Dr expense (amount - tax), Dr VAT receivable (tax), Cr cash (amount)
        vat_acc = _lookup("1350") or _lookup("2150")  # 부가세대급금 or 예수금
        net = amount - tax_amount
        if debit_acc:
            lines.append(ProposalLine(
                account_code=debit_acc.code,
                account_name=debit_acc.name,
                debit=net, credit=Decimal("0"),
            ))
        if vat_acc:
            lines.append(ProposalLine(
                account_code=vat_acc.code,
                account_name=vat_acc.name,
                debit=tax_amount, credit=Decimal("0"),
            ))
        if credit_acc:
            lines.append(ProposalLine(
                account_code=credit_acc.code,
                account_name=credit_acc.name,
                debit=Decimal("0"), credit=amount,
            ))
    else:
        if debit_acc:
            lines.append(ProposalLine(
                account_code=debit_acc.code,
                account_name=debit_acc.name,
                debit=amount, credit=Decimal("0"),
            ))
        if credit_acc:
            lines.append(ProposalLine(
                account_code=credit_acc.code,
                account_name=credit_acc.name,
                debit=Decimal("0"), credit=amount,
            ))

    # Lower confidence if any account is missing
    if not debit_acc or not credit_acc:
        confidence = min(confidence, 0.3)
        if not debit_acc:
            lines.append(ProposalLine(
                account_code=debit_code, account_name=None,
                debit=amount, credit=Decimal("0"),
            ))
        if not credit_acc:
            lines.append(ProposalLine(
                account_code=credit_code, account_name=None,
                debit=Decimal("0"), credit=amount,
            ))

    return Proposal(
        description=description,
        confidence=confidence,
        matched_rule=matched_keyword,
        lines=lines,
    )


@router.post("/propose", response_model=Proposal)
def propose(payload: ProposalIn, db: Session = Depends(get_db)):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    return propose_entry(
        db, payload.description, payload.amount, payload.tax_amount
    )


@router.post(
    "/accept",
    dependencies=[Depends(require_role("manager"))],
)
def accept_proposal(
    description: str,
    proposal: Proposal,
    db: Session = Depends(get_db),
    force_low_confidence: bool = False,
):
    """Convert an accepted Proposal into a real JournalEntry.

    Proposals with confidence < 0.5 are rejected unless `force_low_confidence`
    is set — this prevents accidental posting of weak rule-engine fallbacks.
    """
    from datetime import date as _date

    from app.modules.finance.models import JournalEntry, JournalLine

    if proposal.confidence < 0.5 and not force_low_confidence:
        raise HTTPException(
            status_code=400,
            detail=f"Proposal confidence {proposal.confidence} below 0.5 — "
                   "review the proposal or pass force_low_confidence=true",
        )

    total_debit = sum((Decimal(l.debit) for l in proposal.lines), Decimal("0"))
    total_credit = sum((Decimal(l.credit) for l in proposal.lines), Decimal("0"))
    if total_debit != total_credit:
        raise HTTPException(status_code=400, detail="Unbalanced proposal")

    entry = JournalEntry(
        entry_date=_date.today(),
        description=f"AI: {description}",
        reference="AI-PROP",
    )
    for ln in proposal.lines:
        acc = db.query(Account).filter(Account.code == ln.account_code).first()
        if not acc:
            raise HTTPException(
                status_code=400,
                detail=f"Account {ln.account_code} not found — create it first",
            )
        entry.lines.append(JournalLine(
            account_id=acc.id, debit=ln.debit, credit=ln.credit,
        ))
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "lines": len(entry.lines)}
