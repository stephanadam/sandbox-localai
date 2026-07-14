"""The AI layer: a roster of specialist agents plus the RAG assistant backend.

The web app talks to the "bigger local AI system" only through ``ask_agent``.
Backends:

* ``mock``        - offline, agent-aware heuristic. No external service needed,
                    so the site is fully usable and testable out of the box.
* ``ollama``      - local LLM server; each agent gets a role-specific system
                    prompt (mirrors the CrewAI agent roster).
* ``anythingllm`` - AnythingLLM workspace chat endpoint (RAG over OpenSearch).

Every backend falls back to ``mock`` on error so the assistant always responds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from app.config import settings

# Modules shown in the sidebar / used as document categories.
MODULES: dict[str, str] = {
    "alternative_finance": "Alternative Finance",
    "specialty_lending": "Specialty Lending",
    "acquisitions": "Acquisitions",
    "legal_funding": "Legal Funding",
    "portfolio_management": "Portfolio Management",
}

# Specialist agents (mirrors the CrewAI roster the local AI system runs).
AGENTS: dict[str, dict[str, str]] = {
    "finance": {
        "role": "Finance Specialist",
        "goal": "Financial analysis and projections",
        "backstory": "Expert in corporate finance",
        "icon": "📊",
    },
    "capital_markets": {
        "role": "Capital Markets Expert",
        "goal": "Market and funding analysis",
        "backstory": "Specialist in equity and debt",
        "icon": "📈",
    },
    "underwriting_risk": {
        "role": "Underwriting & Risk Manager",
        "goal": "Risk assessment",
        "backstory": "Experienced in risk",
        "icon": "🛡️",
    },
    "legal": {
        "role": "Legal Advisor",
        "goal": "Legal compliance",
        "backstory": "Corporate legal expert",
        "icon": "⚖️",
    },
    "accounting": {
        "role": "Accounting Specialist",
        "goal": "Accounting and reporting",
        "backstory": "CPA-level expert",
        "icon": "🧾",
    },
    "marketing": {
        "role": "Marketing Strategist",
        "goal": "Marketing and growth",
        "backstory": "Digital marketing expert",
        "icon": "📣",
    },
    "data_analytics": {
        "role": "Data Analytics Expert",
        "goal": "Data insights",
        "backstory": "Data scientist",
        "icon": "🔬",
    },
}

DEFAULT_AGENT = "finance"


@dataclass
class AgentReply:
    text: str
    backend: str
    agent_key: str


def agent_or_default(agent_key: str) -> str:
    return agent_key if agent_key in AGENTS else DEFAULT_AGENT


def _system_prompt(agent_key: str) -> str:
    a = AGENTS[agent_key]
    return (
        f"You are a {a['role']}. {a['backstory']}. "
        f"Your goal: {a['goal']}. Answer concisely and professionally."
    )


def ask_agent(
    agent_key: str,
    question: str,
    context_text: str | None = None,
    document_title: str | None = None,
) -> AgentReply:
    agent_key = agent_or_default(agent_key)

    if settings.ai_backend == "ollama":
        try:
            return _ask_ollama(agent_key, question, context_text)
        except Exception as exc:  # noqa: BLE001
            return _degrade(
                agent_key, question, context_text, document_title, "ollama", exc
            )
    if settings.ai_backend == "anythingllm":
        try:
            return _ask_anythingllm(agent_key, question, context_text)
        except Exception as exc:  # noqa: BLE001
            return _degrade(
                agent_key, question, context_text, document_title, "anythingllm", exc
            )

    return _ask_mock(agent_key, question, context_text, document_title)


def _degrade(
    agent_key, question, context_text, document_title, backend, exc
) -> AgentReply:
    reply = _ask_mock(agent_key, question, context_text, document_title)
    reply.text = (
        f"[{backend} backend unavailable: {exc}. Showing offline agent "
        f"response instead.]\n\n{reply.text}"
    )
    return reply


def _ask_ollama(agent_key, question, context_text) -> AgentReply:
    prompt = question
    if context_text:
        prompt = f"Using this document as context:\n\n{context_text}\n\n{question}"
    response = httpx.post(
        f"{settings.ollama_url}/api/generate",
        json={
            "model": settings.ollama_model,
            "system": _system_prompt(agent_key),
            "prompt": prompt,
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return AgentReply(
        text=response.json().get("response", "").strip(),
        backend="ollama",
        agent_key=agent_key,
    )


def _ask_anythingllm(agent_key, question, context_text) -> AgentReply:
    message = f"[As {AGENTS[agent_key]['role']}] {question}"
    if context_text:
        message += f"\n\nDocument context:\n{context_text}"
    headers = {"Content-Type": "application/json"}
    if settings.anythingllm_api_key:
        headers["Authorization"] = f"Bearer {settings.anythingllm_api_key}"
    url = (
        f"{settings.anythingllm_url}/api/v1/workspace/"
        f"{settings.anythingllm_workspace}/chat"
    )
    response = httpx.post(
        url, json={"message": message, "mode": "query"}, headers=headers, timeout=120
    )
    response.raise_for_status()
    data = response.json()
    text = data.get("textResponse") or data.get("response") or str(data)
    return AgentReply(text=text.strip(), backend="anythingllm", agent_key=agent_key)


def _ask_mock(agent_key, question, context_text, document_title=None) -> AgentReply:
    """Deterministic, role-aware offline reply so the assistant always works."""
    agent = AGENTS[agent_key]
    lines = [f"{agent['icon']} {agent['role']} — {agent['goal']}", ""]

    lines.append(f'You asked: "{question.strip()}"')
    lines.append("")

    if not context_text and document_title:
        # A document was attached but no usable text could be read from it.
        lines.append(
            f'The attached document "{document_title}" has no extractable text '
            "(it may be a scanned/image PDF or an unsupported format), so I "
            "answered from general expertise. Upload a text-based version for a "
            "document-grounded answer."
        )
        lines.append("")
        lines.append(
            f"[Offline agent response — connect Ollama or AnythingLLM for full RAG.]"
        )
        return AgentReply(text="\n".join(lines), backend="mock", agent_key=agent_key)

    if context_text:
        words = re.findall(r"\b\w+\b", context_text)
        sentences = [
            s.strip() for s in re.split(r"(?<=[.!?])\s+", context_text) if s.strip()
        ]
        terms = _detect_terms(context_text)
        lines.append(
            f"Reviewed the attached document ({len(words)} words, "
            f"{len(sentences)} sentences)."
        )
        if terms:
            lines.append(f"Key terms detected: {', '.join(terms)}.")
        focus = _AGENT_FOCUS.get(agent_key, [])
        hits = [t for t in terms if t in focus]
        if hits:
            lines.append(
                f"From a {agent['role']} perspective, note especially: "
                f"{', '.join(hits)}."
            )
        if sentences:
            lines.append("")
            lines.append("Relevant excerpt:")
            lines.append(f"“{sentences[0]}”")
    else:
        lines.append(
            f"As a {agent['role']} ({agent['backstory']}), here is my initial take. "
            "Attach a document for a grounded, RAG-based answer."
        )

    lines.append("")
    lines.append(
        "[Offline agent response — connect Ollama or AnythingLLM for full RAG.]"
    )
    return AgentReply(text="\n".join(lines), backend="mock", agent_key=agent_key)


_AGENT_FOCUS: dict[str, list[str]] = {
    "finance": ["revenue", "yield", "return", "cash", "valuation", "ebitda"],
    "capital_markets": ["equity", "debt", "funding", "market", "bond", "credit"],
    "underwriting_risk": ["risk", "liability", "default", "collateral", "breach"],
    "legal": ["agreement", "liability", "indemnify", "compliance", "clause", "breach"],
    "accounting": ["revenue", "expense", "reporting", "audit", "tax", "gaap"],
    "marketing": ["growth", "customer", "brand", "acquisition", "channel"],
    "data_analytics": ["data", "model", "metric", "trend", "forecast", "insight"],
}

_TERMS = sorted({t for terms in _AGENT_FOCUS.values() for t in terms} | {
    "portfolio", "underwriting", "financing", "arbitration", "dispute", "damages",
    "settlement", "roi", "irr", "diversification",
})


def _detect_terms(text: str) -> list[str]:
    lowered = text.lower()
    return [t for t in _TERMS if t in lowered]
