"""Interface to the local AI system.

This module is the single integration point between the web front end and the
"bigger local AI system". Today it supports two backends:

* ``mock``   - a fully local, dependency-free heuristic analysis so the site is
               usable and testable without any AI service running.
* ``ollama`` - calls a local Ollama server (a common way to self-host LLMs).

Add new local backends (llama.cpp, vLLM, a custom service, ...) by extending
``analyze`` with another branch. The rest of the app only depends on the
``AnalysisResult`` returned here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from app.config import settings

ANALYSIS_TYPES = {
    "summary": "Plain-language summary",
    "risks": "Risk & liability spotting",
    "clauses": "Key clause extraction",
    "obligations": "Obligations & deadlines",
}

_PROMPTS = {
    "summary": "Summarize the following legal document in plain language for a client:",
    "risks": "Identify the key legal risks and liabilities in the following document:",
    "clauses": "Extract and list the key clauses from the following legal document:",
    "obligations": "List the obligations, deadlines, and responsibilities in this document:",
}


@dataclass
class AnalysisResult:
    result_text: str
    backend: str


def analyze(text: str, analysis_type: str = "summary") -> AnalysisResult:
    if analysis_type not in ANALYSIS_TYPES:
        analysis_type = "summary"

    if settings.ai_backend == "ollama":
        try:
            return _analyze_with_ollama(text, analysis_type)
        except Exception as exc:  # noqa: BLE001 - fall back gracefully
            fallback = _analyze_with_mock(text, analysis_type)
            fallback.result_text = (
                f"[Ollama backend unavailable: {exc}. Showing local heuristic "
                f"analysis instead.]\n\n{fallback.result_text}"
            )
            return fallback

    return _analyze_with_mock(text, analysis_type)


def _analyze_with_ollama(text: str, analysis_type: str) -> AnalysisResult:
    prompt = f"{_PROMPTS[analysis_type]}\n\n{text}"
    response = httpx.post(
        f"{settings.ollama_url}/api/generate",
        json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    return AnalysisResult(
        result_text=data.get("response", "").strip(), backend="ollama"
    )


def _analyze_with_mock(text: str, analysis_type: str) -> AnalysisResult:
    """Deterministic, offline analysis so the app works with no AI service.

    This is intentionally simple: it demonstrates the end-to-end flow and gives
    reviewers something meaningful to look at until a real model is wired in.
    """
    words = re.findall(r"\b\w+\b", text)
    word_count = len(words)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

    legal_terms = [
        "agreement", "liability", "indemnify", "indemnification", "terminate",
        "termination", "confidential", "warranty", "breach", "governing law",
        "jurisdiction", "damages", "obligation", "party", "parties", "clause",
        "deadline", "notice", "payment", "arbitration", "dispute",
    ]
    lowered = text.lower()
    found = sorted({t for t in legal_terms if t in lowered})

    header = f"[Local heuristic analysis - {ANALYSIS_TYPES[analysis_type]}]"
    stats = (
        f"Document length: {word_count} words, {len(sentences)} sentences.\n"
        f"Detected legal terms: {', '.join(found) if found else 'none detected'}."
    )

    if analysis_type == "summary":
        preview = " ".join(sentences[:3]) if sentences else text[:400]
        body = f"Opening of document:\n{preview}"
    elif analysis_type == "risks":
        risk_terms = [t for t in found if t in {
            "liability", "indemnify", "indemnification", "breach", "damages",
            "termination", "terminate", "dispute", "arbitration",
        }]
        body = (
            "Potential risk areas flagged based on detected terms:\n- "
            + "\n- ".join(risk_terms)
            if risk_terms
            else "No high-signal risk terms detected in this document."
        )
    elif analysis_type == "clauses":
        clause_lines = [s for s in sentences if any(t in s.lower() for t in found)]
        body = (
            "Sentences referencing key legal terms:\n- "
            + "\n- ".join(clause_lines[:8])
            if clause_lines
            else "No clause-like sentences detected."
        )
    else:  # obligations
        obligation_lines = [
            s for s in sentences
            if re.search(r"\b(shall|must|will|agree|required|responsible)\b", s, re.I)
        ]
        body = (
            "Sentences expressing obligations:\n- "
            + "\n- ".join(obligation_lines[:8])
            if obligation_lines
            else "No explicit obligation language detected."
        )

    result = f"{header}\n\n{stats}\n\n{body}"
    return AnalysisResult(result_text=result, backend="mock")
