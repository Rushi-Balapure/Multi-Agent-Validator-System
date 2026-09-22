"""Deterministic four-way label policy for fixture runs.

Live model prompts are a later slice. This module does not call a model,
a network, or the retrieval index. It implements the research-plan decision
order for a stated evidence collection:

1. Relevance. Passages that do not address the claim are ignored.
2. No addressing passage → unaddressed.
3. Material conflict or inconclusive relevant evidence → underdetermined.
4. Otherwise support or contradiction, only at the preserved scope.

A causal claim is not treated as supported by association language. A
non-significant or directionless passage is not proof of no effect.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from validator.schemas import Evidence, ScientificLabel

_TOKEN = re.compile(r"[a-z0-9]+")
_NEGATION = re.compile(r"\b(not|no|never|without|failed)\b")
_SPAN_ID = re.compile(r"\[(D[01]:[^\]]+)\]")

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "and",
        "or",
        "to",
        "for",
        "with",
        "by",
        "from",
        "that",
        "this",
        "is",
        "are",
        "was",
        "were",
        "be",
        "as",
        "at",
        "than",
        "into",
        "over",
        "its",
        "their",
        "these",
        "those",
        "did",
        "does",
        "do",
        "what",
        "which",
        "about",
        "under",
        "after",
        "before",
        "between",
        "within",
    }
)
INCREASE = frozenset(
    {
        "increase",
        "increased",
        "increases",
        "increasing",
        "higher",
        "improved",
        "improvement",
        "improves",
    }
)
DECREASE = frozenset(
    {
        "decrease",
        "decreased",
        "decreases",
        "decreasing",
        "lower",
        "reduced",
        "reduction",
        "reduces",
    }
)
DIRECTION_WORDS = INCREASE | DECREASE
CAUSAL = frozenset({"cause", "caused", "causes", "causal", "causation"})
ASSOCIATION = frozenset(
    {"associated", "association", "correlated", "correlation", "linked"}
)


class PassageView(BaseModel):
    """Text the label policy may read. No claim, gold label, or D0/D1 role."""

    model_config = ConfigDict(extra="forbid")

    span_id: str = Field(min_length=1)
    text: str


class LabelDecision(BaseModel):
    """Scientific label only. Execution status stays with the caller."""

    model_config = ConfigDict(extra="forbid")

    label: ScientificLabel
    rationale_codes: list[str]
    cited_span_ids: list[str]
    uncertainty_reasons: list[str]


def raw_tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.casefold()))


def content_tokens(text: str) -> set[str]:
    """Topical tokens, with function words and direction words removed."""
    return {
        token
        for token in raw_tokens(text)
        if token not in STOPWORDS and token not in DIRECTION_WORDS and len(token) > 2
    }


def span_id(scope: str, doc_id: int | str, start: int, end: int) -> str:
    return f"{scope}:{doc_id}:{start}-{end}"


def evidence_span_id(evidence: Evidence) -> str | None:
    """Span id for one evidence record, or None when the citation has no span."""
    if evidence.offsets is None or not evidence.text_span:
        return None
    return span_id(
        evidence.access_scope.value,
        evidence.doc_id,
        evidence.offsets.start,
        evidence.offsets.end,
    )


def span_ids_in(text: str) -> list[str]:
    return _SPAN_ID.findall(text)


def polarity(text: str) -> str | None:
    """Return increase, decrease, mixed, or None. Negation flips a single direction."""
    tokens = raw_tokens(text)
    increased = bool(tokens & INCREASE)
    decreased = bool(tokens & DECREASE)
    negated = _NEGATION.search(text.casefold()) is not None
    if increased and decreased:
        return "mixed"
    if increased:
        return "decrease" if negated else "increase"
    if decreased:
        return "increase" if negated else "decrease"
    return None


def _relative_stance(claim_text: str, passage_text: str) -> str:
    claim_polarity = polarity(claim_text)
    passage_polarity = polarity(passage_text)
    if passage_polarity == "mixed" or claim_polarity == "mixed":
        return "mixed"
    if passage_polarity is None or claim_polarity is None:
        return "neutral"
    if passage_polarity == claim_polarity:
        return "support"
    return "contradict"


def _addresses(claim_text: str, passage_text: str) -> bool:
    return len(content_tokens(claim_text) & content_tokens(passage_text)) >= 2


def decide_label(claim_text: str, passages: list[PassageView]) -> LabelDecision:
    """Apply the four-way decision order to one claim and one evidence collection."""
    if not claim_text.strip():
        raise ValueError("label policy requires claim text")
    addressing = [passage for passage in passages if _addresses(claim_text, passage.text)]
    if not addressing:
        return LabelDecision(
            label=ScientificLabel.UNADDRESSED,
            rationale_codes=["no_addressing_passage"],
            cited_span_ids=[],
            uncertainty_reasons=["no_addressing_passage"],
        )

    stances = [(passage, _relative_stance(claim_text, passage.text)) for passage in addressing]
    stance_set = {stance for _, stance in stances}
    if "mixed" in stance_set or {"support", "contradict"} <= stance_set:
        return _decision(
            ScientificLabel.UNDERDETERMINED,
            ["conflicting_results"],
            [passage.span_id for passage, _ in stances],
            ["conflicting_results"],
        )
    if "support" not in stance_set and "contradict" not in stance_set:
        return _decision(
            ScientificLabel.UNDERDETERMINED,
            ["inconclusive_relevant_evidence"],
            [passage.span_id for passage, _ in stances],
            ["inconclusive_relevant_evidence"],
        )

    decisive = "support" if "support" in stance_set else "contradict"
    cited = [passage.span_id for passage, stance in stances if stance == decisive]
    label = (
        ScientificLabel.SUPPORTED if decisive == "support" else ScientificLabel.CONTRADICTED
    )
    code = "supporting_direction" if decisive == "support" else "contradicting_direction"
    if label is ScientificLabel.SUPPORTED and _causal_overreach(claim_text, addressing):
        return _decision(
            ScientificLabel.UNDERDETERMINED,
            ["causal_overreach"],
            cited,
            ["causal_overreach"],
        )
    return _decision(label, [code], cited, [])


def _causal_overreach(claim_text: str, passages: list[PassageView]) -> bool:
    """Supported association does not establish a causal claim."""
    if not (raw_tokens(claim_text) & CAUSAL):
        return False
    evidence_tokens: set[str] = set()
    for passage in passages:
        evidence_tokens |= raw_tokens(passage.text)
    if evidence_tokens & CAUSAL:
        return False
    return True


def _decision(
    label: ScientificLabel,
    rationale_codes: list[str],
    cited_span_ids: list[str],
    uncertainty_reasons: list[str],
) -> LabelDecision:
    return LabelDecision(
        label=label,
        rationale_codes=rationale_codes,
        cited_span_ids=cited_span_ids,
        uncertainty_reasons=uncertainty_reasons,
    )
