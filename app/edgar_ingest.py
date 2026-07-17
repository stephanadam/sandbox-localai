"""Ingest SEC filings via edgartools into structured, LLM-ready context.

Pulls a company's latest filing of a given form (8-K / 10-Q / 10-K), then builds
a compact text document containing:
  * a header summary (`to_context()`): key financials + section list,
  * the primary financial statements (XBRL-parsed) as readable line items,
  * MD&A and Risk Factors section text when present.

This structured context is far more useful to an LLM than a raw PDF/HTML dump.
"""

from __future__ import annotations

import re

from app.config import settings

SUPPORTED_FORMS = ["10-K", "10-Q", "8-K"]
_MAX_CHARS = 40000

# Candidate item keys for narrative sections (differ across 10-K vs 10-Q).
_MDNA_KEYS = ["Item 7", "Part I, Item 2", "Item 2"]
_RISK_KEYS = ["Item 1A", "Part II, Item 1A", "Part I, Item 1A"]


class EdgarError(Exception):
    """Raised when a filing cannot be fetched or parsed."""


def _render_statement(stmt, max_rows: int = 45) -> str:
    if stmt is None:
        return ""
    try:
        import pandas as pd

        df = stmt.to_dataframe()
    except Exception:
        try:
            return str(stmt)[:2000]
        except Exception:
            return ""
    date_cols = [c for c in df.columns if re.match(r"^\d{4}-\d{2}-\d{2}", str(c))]
    if not date_cols or "label" not in df.columns:
        return str(df)[:2000]
    valcol = date_cols[0]
    lines = [f"(period: {valcol})"]
    for _, row in df.iterrows():
        label = str(row.get("label") or "").strip()
        if not label or bool(row.get("abstract")):
            continue
        val = row.get(valcol)
        try:
            if val is None or pd.isna(val):
                continue
        except Exception:
            pass
        lines.append(f"{label}: {val}")
        if len(lines) >= max_rows:
            break
    return "\n".join(lines)


def _get_section(obj, keys: list[str]) -> str:
    for key in keys:
        try:
            text = str(obj[key])
        except Exception:
            continue
        if text and len(text) > 80:
            return text
    return ""


def fetch_edgar_filing(ticker: str, form_type: str) -> tuple[str, str, str]:
    """Return (title, structured_text, accession_no) for the latest filing.

    Raises ``EdgarError`` with a user-friendly message on any failure.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        raise EdgarError("Please enter a ticker symbol.")
    if form_type not in SUPPORTED_FORMS:
        form_type = "10-Q"

    try:
        from edgar import Company, set_identity
    except Exception as exc:  # pragma: no cover - import guard
        raise EdgarError(f"edgartools is not available: {exc}") from exc

    try:
        set_identity(settings.edgar_identity)
        company = Company(ticker)
    except Exception as exc:
        raise EdgarError(f"Could not find company for ticker '{ticker}'.") from exc

    try:
        filings = company.get_filings(form=form_type)
        filing = filings.latest()
    except Exception as exc:
        raise EdgarError(f"Could not list {form_type} filings for {ticker}.") from exc
    if filing is None:
        raise EdgarError(f"No {form_type} filings found for {ticker}.")

    try:
        obj = filing.obj()
    except Exception as exc:
        raise EdgarError(f"Could not parse the {form_type} filing.") from exc

    parts: list[str] = []
    try:
        parts.append(str(obj.to_context()))
    except Exception:
        pass

    for name, attr in [
        ("Income Statement", "income_statement"),
        ("Balance Sheet", "balance_sheet"),
        ("Cash Flow Statement", "cash_flow_statement"),
    ]:
        stmt = getattr(obj, attr, None)
        rendered = _render_statement(stmt)
        if rendered:
            parts.append(f"\n== {name} ==\n{rendered}")

    mdna = _get_section(obj, _MDNA_KEYS)
    if mdna:
        parts.append(f"\n== Management's Discussion & Analysis ==\n{mdna[:8000]}")
    risk = _get_section(obj, _RISK_KEYS)
    if risk:
        parts.append(f"\n== Risk Factors ==\n{risk[:8000]}")

    text = "\n".join(p for p in parts if p).strip()
    if not text:
        raise EdgarError("The filing was found but no content could be extracted.")
    text = text[:_MAX_CHARS]

    period = getattr(obj, "period_of_report", None) or getattr(filing, "filing_date", "")
    title = f"{ticker} {form_type} ({period})".strip()
    accession = str(getattr(filing, "accession_no", "") or "")
    return title, text, accession
