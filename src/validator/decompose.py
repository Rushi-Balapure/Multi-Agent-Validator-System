"""Deterministic claim proposer.

Phase-2 inputs are an optional question and a frozen conclusion, plus an
optional report the conclusion was taken from. The output is a schema-valid
``Report`` whose embedded ``Claim`` records use ``dataset="agentic"``:
neutral questions, asserted answers, and exact source spans.

Quantities, confidence language, population, experimental setting, comparators,
and causal scope are copied from the source. A conjunction such as
"X improves A and B" becomes two claims, and later conjuncts keep a dependency
on the first claim from that sentence. "Associated with" stays an association.
Opinions and recommendations are separate claims.

This module is offline. It does not retrieve, score BM25, or call a model.
``dry_run=False`` is refused so a later live proposer cannot be switched on by
accident. Asserted answers stay on the ``Claim`` record. ``neutral_reader_input``
returns the neutral question only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from validator.schemas import Claim, ClaimSource, Report, SplitRole

CLAIM_BUDGET = 8

_CAUSAL_WORD = re.compile(r"\b(?:cause|caused|causes|causation|causal)\b", re.I)
_HEDGE = re.compile(
    r"\b(?:may|might|could|suggests|suggested|appears|appeared|possibly|likely|significantly)\b",
    re.I,
)
_QUANTITY = re.compile(
    r"\beffect size(?:\s+of)?\s+\d+(?:\.\d+)?"
    r"|\b\d+(?:\.\d+)?\s*%"
    r"|\b\d+(?:\.\d+)?\s*-fold"
    r"|\b\d+(?:\.\d+)?\s*(?:mg|kg|mmHg)\b",
    re.I,
)
_POP = (
    r"adults aged [^,.;]+|older adults|the mouse model|mouse model|"
    r"mice|mouse|rats|adults|humans|patients"
)
_POP_MENTION = re.compile(
    rf"\b(?:in|among|for|to)\s+(?P<pop>{_POP})\b",
    re.I,
)
_SUFFIX_COMP = re.compile(
    r"^(?P<body>.*\S)\s+(?P<suffix>(?:compared with|compared to|relative to|versus|vs\.?)\s+.+)\s*$",
    re.I,
)
_SUFFIX_TIME = re.compile(
    r"^(?P<body>.*\S)\s+(?P<suffix>(?:after|at|over|within|during)\s+\d+(?:\.\d+)?\s+"
    r"(?:days?|weeks?|months?|years?))\s*$",
    re.I,
)
_SUFFIX_POP = re.compile(
    rf"^(?P<body>.*\S)\s+(?P<suffix>(?:in|among|for|to)\s+(?:{_POP}))\s*$",
    re.I,
)
_PREFIX_SETTING = re.compile(
    r"^(?P<prefix>in\s+(?:a|an)\s+randomized(?:\s+controlled)?\s+trial\s*,\s*)(?P<body>\S.*)$",
    re.I,
)
_PREFIX_POP = re.compile(
    rf"^(?P<prefix>(?:in|among|for)\s+(?:{_POP})\s*,\s*)(?P<body>\S.*)$",
    re.I,
)
_COMP_TARGET = re.compile(
    r"\b(?P<cue>compared with|compared to|relative to|versus|vs\.?)\s+(?P<target>[^.;,(]+)",
    re.I,
)
_TIME_FIELD = re.compile(
    r"\b(?:after|at|over|within|during)\s+\d+(?:\.\d+)?\s+(?:days?|weeks?|months?|years?)\b",
    re.I,
)
_VERB = re.compile(
    r"\b(?:"
    r"(?:did|does|do)\s+not\s+(?:significantly\s+|slightly\s+)?"
    r"(?:improve|improves|increase|increases|decrease|decreases|reduce|reduces|"
    r"lower|lowers|raise|raises|cause|causes)"
    r"|(?:may|might|could)\s+be\s+associated\s+with"
    r"|(?:is|was|are|were)\s+associated\s+with"
    r"|(?:may|might|could)\s+(?:significantly\s+|slightly\s+)?"
    r"(?:improve|improves|increase|increases|decrease|decreases|reduce|reduces|"
    r"lower|lowers|raise|raises|cause|causes)"
    r"|(?:significantly|slightly)\s+"
    r"(?:improved|improves|improve|increased|increases|increase|decreased|decreases|decrease|"
    r"reduced|reduces|reduce|lowered|lowers|raised|raises)"
    r"|associated\s+with"
    r"|correlated\s+with"
    r"|linked\s+to"
    r"|leads\s+to|lead\s+to|led\s+to"
    r"|improved|improves|improve"
    r"|increased|increases|increase"
    r"|decreased|decreases|decrease"
    r"|reduced|reduces|reduce"
    r"|lowered|lowers"
    r"|raised|raises"
    r"|caused|causes|cause"
    r"|prevented|prevents"
    r"|enhanced|enhances"
    r"|worsened|worsens"
    r")\b",
    re.I,
)
_DIRECTION = re.compile(
    r"\b(?:increases?|increased|increasing|decreases?|decreased|decreasing|"
    r"improves?|improved|reduces?|reduced|lowers?|lowered|raises?|raised|"
    r"higher|lower|causes?|caused|causing)\b",
    re.I,
)
_OPINION_START = re.compile(
    r"^(?:in our opinion|we believe|we think|it is our view)\b",
    re.I,
)
_REC_START = re.compile(
    r"^(?:we recommend|we suggest|we advise|it is recommended|clinicians should|physicians should)\b",
    re.I,
)
_NOMINAL = re.compile(
    r"\b(reduction|increase|decrease|improvement|association)\b",
    re.I,
)
_SETTING_FIELD = re.compile(
    r"\b((?:a|an)\s+randomized(?:\s+controlled)?\s+trial)\b",
    re.I,
)
_ABBREV = frozenset({"vs", "dr", "mr", "mrs", "ms", "fig"})


class DecomposeError(ValueError):
    """The conclusion could not be split into schema-valid claims."""


class LiveDecompositionRefused(DecomposeError):
    """Live model decomposition is outside this slice."""


class DecomposeInput(BaseModel):
    """Proposer inputs. The conclusion is frozen; this module does not rewrite the report.

    Frozen conclusions use ``dataset="agentic"``. ``native_id`` and ``split_role``
    stay unset. Pass ``dataset="scifact"`` only with a real ``native_id``.
    """

    model_config = ConfigDict(extra="forbid")

    frozen_conclusion: str = Field(min_length=1)
    question: str | None = None
    question_id: str | None = None
    report_text: str | None = None
    report_id: str | None = None
    dataset: Literal["agentic", "scifact"] = "agentic"
    native_id: int | None = None
    split_role: SplitRole | None = None
    fixture_id: str | None = None

    @model_validator(mode="after")
    def scifact_source_needs_native_id(self) -> DecomposeInput:
        if self.dataset == "scifact" and self.native_id is None:
            raise ValueError('native_id is required when dataset is "scifact"')
        return self


class DecompositionResult(BaseModel):
    """Agentic Report plus coverage when the conclusion exceeds the claim budget."""

    model_config = ConfigDict(extra="forbid")

    fixture_id: str | None = None
    question: str | None = None
    report_id: str | None = None
    report: Report
    claims: list[Claim]
    partial: bool = False
    unchecked_spans: list[str] = Field(default_factory=list)
    dry_run: bool = True


@dataclass
class _Draft:
    sentence: str
    normalized: str
    subject: str | None
    relation: str | None
    obj: str | None
    population: str | None
    comparator: str | None
    time: str | None
    units: str | None
    modality: str | None
    question: str
    group: int | None


def decompose(
    spec: DecomposeInput,
    *,
    dry_run: bool = True,
    claim_budget: int = CLAIM_BUDGET,
) -> DecompositionResult:
    """Split one frozen conclusion into atomic claims.

    ``claim_budget`` defaults to the research-plan cap of 8 and cannot be raised.
    Extra source sentences are listed in ``unchecked_spans`` and ``partial`` is set.
    """
    if not dry_run:
        raise LiveDecompositionRefused(
            "Live decomposition is not part of this slice. "
            "The deterministic proposer runs with dry_run. No model was called."
        )
    if claim_budget < 1 or claim_budget > CLAIM_BUDGET:
        raise DecomposeError(f"claim_budget must be from 1 to {CLAIM_BUDGET}")
    conclusion = spec.frozen_conclusion.strip()
    if not conclusion:
        raise DecomposeError("frozen conclusion is required")

    drafts: list[_Draft] = []
    for index, sentence in enumerate(split_sentences(conclusion)):
        sentence_drafts = _claims_for_sentence(sentence, group_index=index)
        _enforce_preservation(sentence, sentence_drafts)
        drafts.extend(sentence_drafts)
    if not drafts:
        raise DecomposeError("frozen conclusion did not contain a claim sentence")

    kept: list[_Draft] = []
    unchecked: list[str] = []
    for draft in drafts:
        if len(kept) >= claim_budget:
            if draft.sentence not in unchecked:
                unchecked.append(draft.sentence)
            continue
        kept.append(draft)

    report_id = spec.report_id or spec.fixture_id or "agentic:decompose"
    claims = _assign_claims(spec, kept, report_id)
    for claim in claims:
        _require_exact_span(claim.exact_source_span, conclusion, spec.report_text)
        Claim.model_validate(claim.model_dump())
    report = Report(
        report_id=report_id,
        question_id=spec.question_id,
        frozen_conclusion=conclusion,
        claim_ids=[claim.claim_id for claim in claims],
        claims=claims,
        generator={
            "model_id": "fixture-proposer",
            "dry_run": True,
            "partial": bool(unchecked),
            "unchecked_spans": list(unchecked),
        },
    )
    return DecompositionResult(
        fixture_id=spec.fixture_id,
        question=spec.question,
        report_id=report_id,
        report=report,
        claims=claims,
        partial=bool(unchecked),
        unchecked_spans=unchecked,
        dry_run=True,
    )


def neutral_reader_input(claim: Claim) -> dict[str, str]:
    """Question-only payload. The asserted answer is not a field and not copied in."""
    if claim.neutral_question is None or not claim.neutral_question.strip():
        raise DecomposeError("neutral question is required")
    question = claim.neutral_question.strip()
    if claim.asserted_answer and claim.asserted_answer in question:
        raise DecomposeError("neutral question must not contain the asserted answer")
    return {"neutral_question": question}


def load_fixture(path: Path) -> DecomposeInput:
    return DecomposeInput.model_validate(json.loads(path.read_text(encoding="utf-8")))


def split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries. Decimal points and abbreviations stay inside."""
    spans: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if text[index] in ".!?;" and not _keeps_dot(text, index):
            sentence = text[start : index + 1].strip()
            if sentence and not sentence in {".", "!", "?", ";"}:
                spans.append(sentence)
            cursor = index + 1
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            start = cursor
            index = cursor
            continue
        index += 1
    tail = text[start:].strip()
    if tail:
        spans.append(tail)
    return spans


def _keeps_dot(text: str, index: int) -> bool:
    if text[index] != ".":
        return False
    if index > 0 and index + 1 < len(text) and text[index - 1].isdigit() and text[index + 1].isdigit():
        return True
    left = index - 1
    while left >= 0 and text[left].isalpha():
        left -= 1
    return text[left + 1 : index].casefold() in _ABBREV


def _claims_for_sentence(sentence: str, *, group_index: int) -> list[_Draft]:
    if _OPINION_START.search(sentence):
        return [_marked_draft(sentence, "opinion", "opinion")]
    if _REC_START.search(sentence):
        return [_marked_draft(sentence, "recommendation", "recommend")]

    body = sentence[:-1].strip() if sentence.endswith(".") else sentence.strip()
    prefixes, suffixes, core, shared = _peel(body)
    triples = _parse_core(core)
    if len(triples) <= 1:
        parsed = triples[0] if triples else (None, None, None)
        return [_verbatim_draft(sentence, parsed, shared)]
    drafts = []
    for subject, verb, obj in triples:
        local_pop, local_suffix, obj = _local_population(obj, shared)
        normalized = _assemble(prefixes, f"{subject} {verb} {obj}".strip(), local_suffix, suffixes)
        population = local_pop or shared.get("population")
        modality = _modality(verb, normalized)
        drafts.append(
            _Draft(
                sentence=sentence,
                normalized=normalized,
                subject=subject,
                relation=verb,
                obj=obj or None,
                population=population,
                comparator=shared.get("comparator"),
                time=shared.get("time"),
                units=_units(normalized),
                modality=modality,
                question=_question(
                    modality=modality,
                    subject=subject,
                    obj=obj,
                    population=population,
                    comparator=shared.get("comparator"),
                    setting=shared.get("setting"),
                    quantities_source=normalized,
                    sentence=sentence,
                ),
                group=group_index,
            )
        )
    return drafts


def _marked_draft(sentence: str, modality: str, relation: str) -> _Draft:
    mentions = _populations(sentence)
    population = mentions[0] if len(mentions) == 1 else None
    comparator = _comparator_target(sentence)
    return _Draft(
        sentence=sentence,
        normalized=sentence if sentence.endswith(".") else f"{sentence}.",
        subject="We" if sentence.casefold().startswith("we ") else None,
        relation=relation,
        obj=_residue(sentence) or None,
        population=population,
        comparator=comparator,
        time=_time_phrase(sentence),
        units=_units(sentence),
        modality=modality,
        question=_question(
            modality=modality,
            subject=None,
            obj=None,
            population=population,
            comparator=comparator,
            setting=_setting_phrase(sentence),
            quantities_source=sentence,
            sentence=sentence,
        ),
        group=None,
    )


def _verbatim_draft(
    sentence: str,
    parsed: tuple[str | None, str | None, str | None],
    shared: dict[str, str | None],
) -> _Draft:
    subject, verb, obj = parsed
    population = shared.get("population") or _only(_populations(sentence))
    normalized = sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."
    if verb is None:
        nominal = _NOMINAL.search(sentence)
        relation = nominal.group(1).casefold() if nominal else None
        modality = _modality_from_text(sentence, relation)
    else:
        relation = verb
        modality = _modality(verb, normalized)
    return _Draft(
        sentence=sentence,
        normalized=normalized,
        subject=subject,
        relation=relation,
        obj=obj,
        population=population,
        comparator=shared.get("comparator") or _comparator_target(sentence),
        time=shared.get("time") or _time_phrase(sentence),
        units=_units(normalized),
        modality=modality,
        question=_question(
            modality=modality,
            subject=subject,
            obj=obj,
            population=population,
            comparator=shared.get("comparator") or _comparator_target(sentence),
            setting=shared.get("setting") or _setting_phrase(sentence),
            quantities_source=normalized,
            sentence=sentence,
        ),
        group=None,
    )


def _peel(text: str) -> tuple[list[str], list[str], str, dict[str, str | None]]:
    pop_count = len(_populations(text))
    prefixes: list[str] = []
    suffixes: list[str] = []
    shared: dict[str, str | None] = {
        "population": None,
        "comparator": None,
        "time": None,
        "setting": None,
    }
    while True:
        peeled = False
        for kind, pattern in (
            ("comparator", _SUFFIX_COMP),
            ("time", _SUFFIX_TIME),
            ("population", _SUFFIX_POP),
        ):
            if kind == "population" and (pop_count != 1 or shared["population"]):
                continue
            if kind == "comparator" and shared["comparator"]:
                continue
            if kind == "time" and shared["time"]:
                continue
            match = pattern.match(text)
            if not match:
                continue
            body = match.group("body").strip()
            if not body or len(body) >= len(text.strip()):
                continue
            suffixes.append(match.group("suffix").strip())
            text = body
            if kind == "comparator":
                shared["comparator"] = _comparator_target(match.group("suffix"))
            elif kind == "population":
                shared["population"] = _only(_populations(match.group("suffix")))
            else:
                shared["time"] = match.group("suffix").strip()
            peeled = True
            break
        if not peeled:
            break

    setting = _PREFIX_SETTING.match(text)
    if setting:
        prefixes.append(setting.group("prefix"))
        shared["setting"] = _setting_phrase(setting.group("prefix"))
        text = setting.group("body").strip()
    if pop_count == 1 and shared["population"] is None:
        leading = _PREFIX_POP.match(text)
        if leading:
            prefixes.append(leading.group("prefix"))
            shared["population"] = _only(_populations(leading.group("prefix")))
            text = leading.group("body").strip()
    return prefixes, suffixes, text.strip(), shared


def _parse_core(core: str) -> list[tuple[str, str, str]]:
    if not core:
        return []
    match = _VERB.search(core)
    if not match:
        return []
    subject = core[: match.start()].strip(" ,;")
    verb = re.sub(r"\s+", " ", match.group(0)).strip()
    rest = core[match.end() :].strip()
    if not subject or not rest:
        return []
    parts = _split_coordination(rest)
    triples: list[tuple[str, str, str]] = []
    for index, part in enumerate(parts):
        if index == 0:
            triples.append((subject, verb, part.strip(" ,;")))
            continue
        verb_at_start = _VERB.match(part)
        if verb_at_start and verb_at_start.start() == 0:
            new_verb = re.sub(r"\s+", " ", verb_at_start.group(0)).strip()
            obj = part[verb_at_start.end() :].strip(" ,;")
            if obj:
                triples.append((subject, new_verb, obj))
                continue
        triples.append((subject, verb, part.strip(" ,;")))
    return [item for item in triples if item[2]]


def _split_coordination(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        if depth == 0:
            match = re.match(r"\s+(?:and|or)\s+", text[index:], re.I)
            if match:
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                index += match.end()
                continue
        buf.append(char)
        index += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _local_population(obj: str, shared: dict[str, str | None]) -> tuple[str | None, str, str]:
    if shared.get("population"):
        return None, "", obj
    match = _SUFFIX_POP.match(obj)
    if not match:
        return None, "", obj
    population = _only(_populations(match.group("suffix")))
    if population is None:
        return None, "", obj
    return population, match.group("suffix").strip(), match.group("body").strip()


def _assemble(prefixes: list[str], clause: str, local_suffix: str, suffixes: list[str]) -> str:
    text = "".join(prefixes) + clause
    if local_suffix:
        text += " " + local_suffix
    for suffix in reversed(suffixes):
        text += " " + suffix
    text = re.sub(r"\s+", " ", text).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _modality(verb: str, text: str) -> str:
    """Map a verb onto the §4 modality strings used by agentic claims.

    Association stays association. Negation stays negation. A measured
    quantity is magnitude. Confidence words stay in the relation text.
    """
    folded = verb.casefold()
    if any(token in folded for token in ("associated", "correlated", "linked")):
        return "association"
    if re.search(r"\bnot\b", folded):
        return "negation"
    if _CAUSAL_WORD.search(folded) or re.search(r"\b(?:led to|leads to|lead to)\b", folded):
        return "causal"
    if _quantities(text) or _units(text):
        return "magnitude"
    return "effect"


def _modality_from_text(sentence: str, relation: str | None) -> str:
    if _OPINION_START.search(sentence):
        return "opinion"
    if _REC_START.search(sentence):
        return "recommendation"
    if re.search(r"\b(?:associated|association|correlated|correlation|linked)\b", sentence, re.I):
        return "association"
    if re.search(r"\b(?:did|does|do)\s+not\b", sentence, re.I):
        return "negation"
    if _CAUSAL_WORD.search(sentence):
        return "causal"
    if _quantities(sentence) or _units(sentence):
        return "magnitude"
    if relation or re.search(r"\b(?:reduction|increase|decrease|improvement)\b", sentence, re.I):
        return "effect"
    return "descriptive"


def _question(
    *,
    modality: str | None,
    subject: str | None,
    obj: str | None,
    population: str | None,
    comparator: str | None,
    setting: str | None,
    quantities_source: str,
    sentence: str,
) -> str:
    if modality == "recommendation":
        topic = _residue(sentence)
        text = f"What did the report state about the recommendation regarding {topic}?"
        return _ensure_quantities(text, quantities_source)
    if modality == "opinion":
        topic = _residue(sentence)
        text = f"What did the report state about the stated opinion that {topic}?"
        return _ensure_quantities(text, quantities_source)

    head = "What did the report state about"
    if modality in {"association", "hedged_association"}:
        head = "What did the report state about the association between"
    bits = [head]
    if subject:
        bits.append(subject.strip())
    neutral_obj = _neutralize_object(obj or "")
    if neutral_obj:
        if subject:
            bits.append("and")
        bits.append(neutral_obj)
    if not subject and not neutral_obj:
        residue = _residue(sentence)
        if residue:
            bits.append(residue)
    text = " ".join(bits)
    text = _append_scope(text, population=population, comparator=comparator, setting=setting)
    if not text.endswith("?"):
        text += "?"
    return _ensure_quantities(re.sub(r"\s+", " ", text).strip(), quantities_source)


def _append_scope(
    text: str,
    *,
    population: str | None,
    comparator: str | None,
    setting: str | None,
) -> str:
    folded = text.casefold()
    if population and population.casefold() not in folded:
        text = f"{text} in {population}"
        folded = text.casefold()
    if setting and setting.casefold() not in folded:
        text = f"{text} in {setting}"
        folded = text.casefold()
    if comparator and comparator.casefold() not in folded:
        text = f"{text} compared with {comparator}"
    return text


def _neutralize_object(text: str) -> str:
    cleaned = _DIRECTION.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;")
    cleaned = re.sub(r"\s+(?:,|and|or)$", "", cleaned, flags=re.I).strip()
    return cleaned


def _ensure_quantities(question: str, source: str) -> str:
    missing = [item for item in _quantities(source) if item.casefold() not in question.casefold()]
    if not missing:
        return question
    extra = " and ".join(missing)
    if question.endswith("?"):
        question = question[:-1]
    return f"{question}, including {extra}?"


def _residue(sentence: str) -> str:
    text = sentence.strip()
    if text.endswith("."):
        text = text[:-1]
    text = re.sub(
        r"^(?:we recommend|we suggest|we advise|it is recommended(?:\s+that)?|"
        r"clinicians should|physicians should)\s+",
        "",
        text,
        count=1,
        flags=re.I,
    )
    text = re.sub(
        r"^(?:in our opinion|we believe|we think|it is our view)\s*,?\s*",
        "",
        text,
        count=1,
        flags=re.I,
    )
    text = re.sub(
        r"^(?:the trial|this study|the study)\s+(?:found|reported|showed|observed)\s+(?:that\s+)?",
        "",
        text,
        count=1,
        flags=re.I,
    )
    return text.strip(" ,")


def _populations(text: str) -> list[str]:
    return [match.group("pop") for match in _POP_MENTION.finditer(text)]


def _only(values: list[str]) -> str | None:
    if len(values) == 1:
        return values[0]
    return None


def _comparator_target(text: str) -> str | None:
    match = _COMP_TARGET.search(text)
    if not match:
        return None
    return match.group("target").strip()


def _time_phrase(text: str) -> str | None:
    match = _TIME_FIELD.search(text)
    if not match:
        return None
    return match.group(0)


def _setting_phrase(text: str) -> str | None:
    match = _SETTING_FIELD.search(text)
    if not match:
        return None
    return match.group(1)


def _units(text: str) -> str | None:
    if re.search(r"%|\bpercent\b", text, re.I):
        return "%"
    match = re.search(r"\b(mg|kg|mmHg)\b", text)
    if match:
        return match.group(1)
    return None


def _quantities(text: str) -> list[str]:
    return _QUANTITY.findall(text)


def _enforce_preservation(sentence: str, drafts: list[_Draft]) -> None:
    if not drafts:
        raise DecomposeError("a source sentence produced no claims")
    combined = "\n".join(draft.normalized for draft in drafts)
    for quantity in _quantities(sentence):
        if quantity.casefold() not in combined.casefold():
            raise DecomposeError(f"quantity {quantity!r} was dropped from {sentence!r}")
    for draft in drafts:
        for quantity in _quantities(draft.normalized):
            if quantity.casefold() not in sentence.casefold():
                raise DecomposeError(f"quantity {quantity!r} was added beyond the source sentence")
        if draft.normalized in draft.question:
            raise DecomposeError("neutral question contains the asserted answer")
        if draft.sentence != sentence:
            raise DecomposeError("claim span is not the source sentence")
    if _CAUSAL_WORD.search(sentence) is None:
        for draft in drafts:
            blob = " ".join(
                part
                for part in (draft.normalized, draft.relation or "", draft.question)
                if part
            )
            if "causal" in (draft.modality or "").casefold() or _CAUSAL_WORD.search(blob):
                raise DecomposeError("association or descriptive text was upgraded to a causal claim")
    mentions = _populations(sentence)
    if len(mentions) == 1:
        for draft in drafts:
            if mentions[0].casefold() not in draft.normalized.casefold():
                raise DecomposeError(f"population {mentions[0]!r} was dropped")
    else:
        for mention in mentions:
            if mention.casefold() not in combined.casefold():
                raise DecomposeError(f"population {mention!r} was dropped")
    for hedge in _HEDGE.findall(sentence):
        if hedge.casefold() not in combined.casefold():
            raise DecomposeError(f"confidence language {hedge!r} was dropped")
    comparator = _comparator_target(sentence)
    if comparator:
        for draft in drafts:
            if comparator.casefold() not in draft.normalized.casefold():
                raise DecomposeError(f"comparator {comparator!r} was removed")
    time_phrase = _time_phrase(sentence)
    if time_phrase:
        for draft in drafts:
            if time_phrase.casefold() not in draft.normalized.casefold():
                raise DecomposeError(f"time phrase {time_phrase!r} was dropped")
    setting = _setting_phrase(sentence)
    if setting:
        for draft in drafts:
            if setting.casefold() not in draft.normalized.casefold():
                raise DecomposeError(f"experimental setting {setting!r} was dropped")


def _assign_claims(spec: DecomposeInput, drafts: list[_Draft], report_id: str) -> list[Claim]:
    anchors: dict[int, str] = {}
    claims: list[Claim] = []
    source = ClaimSource(
        dataset=spec.dataset,
        native_id=spec.native_id,
        split_role=spec.split_role,
    )
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", report_id.removeprefix("agentic:")).strip("-")
    slug = slug or "decompose"
    for number, draft in enumerate(drafts, start=1):
        claim_id = f"agentic:{slug}:{number}"
        dependencies: list[str] = []
        if draft.group is not None:
            anchor = anchors.get(draft.group)
            if anchor is None:
                anchors[draft.group] = claim_id
            else:
                dependencies = [anchor]
        normalized = draft.normalized
        question = draft.question
        if normalized in question:
            raise DecomposeError("neutral question contains the asserted answer")
        claims.append(
            Claim(
                claim_id=claim_id,
                report_id=report_id,
                exact_source_span=draft.sentence,
                normalized_claim=normalized,
                subject=draft.subject,
                relation=draft.relation,
                object=draft.obj,
                population=draft.population,
                comparator=draft.comparator,
                time=draft.time,
                units=draft.units,
                modality=draft.modality,
                neutral_question=question,
                asserted_answer=normalized,
                dependencies=dependencies,
                source=source,
            )
        )
    return claims


def _require_exact_span(span: str | None, conclusion: str, report_text: str | None) -> None:
    if not span:
        raise DecomposeError("exact source span is required")
    in_conclusion = span in conclusion
    in_report = report_text is not None and span in report_text
    if not in_conclusion and not in_report:
        raise DecomposeError("exact source span is not in the conclusion or the report")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Decompose a frozen conclusion into atomic claims. "
            "The proposer is deterministic and offline. "
            "It does not retrieve passages, build a BM25 index, or call LM Studio. "
            f"At most {CLAIM_BUDGET} claims are emitted; further source spans are listed as unchecked."
        )
    )
    parser.add_argument("--fixture", type=Path, help="JSON file with a frozen conclusion.")
    parser.add_argument("--conclusion", help="Frozen conclusion text. Not combined with --fixture.")
    parser.add_argument("--question", help="Upstream question. Stored on the result, not asserted as a claim.")
    parser.add_argument("--report-text", help="Optional report text used to check exact spans.")
    parser.add_argument("--report-id", help="Report id copied onto the Report and each claim.")
    parser.add_argument("--question-id", help="Optional question id stored on the Report.")
    parser.add_argument(
        "--dataset",
        choices=["agentic", "scifact"],
        default="agentic",
        help="Claim source dataset. Frozen conclusions use agentic. scifact requires --native-id.",
    )
    parser.add_argument(
        "--native-id",
        type=int,
        help="SciFact native id. Required only with --dataset scifact.",
    )
    parser.add_argument(
        "--split-role",
        choices=[item.value for item in SplitRole],
        help="Optional split role. Agentic conclusions usually leave this unset.",
    )
    parser.add_argument("--output", type=Path, help="Write Decomposition JSON here. Omit to write stdout.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the deterministic proposer. This is the default.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Refused in this slice. Live model prompts are not called.",
    )
    args = parser.parse_args(argv)
    if args.live:
        print(
            "Live decomposition is not part of this slice. "
            "The deterministic proposer runs with dry_run. No model was called.",
            file=sys.stderr,
        )
        return 2
    try:
        spec = _spec_from_args(args)
        result = decompose(spec, dry_run=True)
    except DecomposeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    text = result.model_dump_json(indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0


def _spec_from_args(args: argparse.Namespace) -> DecomposeInput:
    if args.fixture is not None and args.conclusion is not None:
        raise DecomposeError("pass either --fixture or --conclusion")
    if args.fixture is None and args.conclusion is None:
        raise DecomposeError("pass --fixture or --conclusion")
    if args.fixture is not None:
        if any(
            value is not None
            for value in (
                args.native_id,
                args.report_text,
                args.question,
                args.question_id,
                args.report_id,
                args.split_role,
            )
        ) or args.dataset != "agentic":
            raise DecomposeError("--fixture already carries conclusion inputs")
        return load_fixture(args.fixture)
    if args.dataset == "scifact" and args.native_id is None:
        raise DecomposeError("--native-id is required when --dataset scifact")
    payload: dict[str, object] = {
        "frozen_conclusion": args.conclusion,
        "question": args.question,
        "question_id": args.question_id,
        "report_text": args.report_text,
        "report_id": args.report_id,
        "dataset": args.dataset,
    }
    if args.native_id is not None:
        payload["native_id"] = args.native_id
    if args.split_role:
        payload["split_role"] = SplitRole(args.split_role)
    return DecomposeInput.model_validate(payload)


if __name__ == "__main__":
    raise SystemExit(main())
