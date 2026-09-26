"""Cited-document connected components used as bootstrap families.

Two claims share a family when their SciFact ``cited_doc_ids`` overlap,
transitively. Isolated claims are singleton families. This is the clustering
used for the paired 2000-resample interval when rows do not already carry
``question_family``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence


class FamilyError(ValueError):
    """Cited-document families cannot be built from the supplied claims."""


def connected_components(claim_to_docs: Mapping[str, Sequence[int]]) -> dict[str, str]:
    """Map each claim_id to a family id ``cited:{root}``.

    ``root`` is the lexicographically smallest claim id in the component.
    Claims with an empty citation list stay singletons.
    """
    if not claim_to_docs:
        raise FamilyError("no claims to cluster")
    parent = {claim_id: claim_id for claim_id in claim_to_docs}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        root_left, root_right = find(left), find(right)
        if root_left == root_right:
            return
        if root_left < root_right:
            parent[root_right] = root_left
        else:
            parent[root_left] = root_right

    by_doc: dict[int, list[str]] = defaultdict(list)
    for claim_id, docs in claim_to_docs.items():
        if not isinstance(claim_id, str) or not claim_id:
            raise FamilyError("claim_id must be a non-empty string")
        seen: set[int] = set()
        for doc_id in docs:
            if not isinstance(doc_id, int) or isinstance(doc_id, bool):
                raise FamilyError(f"{claim_id} has a non-integer cited doc id {doc_id!r}")
            if doc_id in seen:
                continue
            seen.add(doc_id)
            by_doc[doc_id].append(claim_id)
    for members in by_doc.values():
        head = members[0]
        for other in members[1:]:
            union(head, other)
    families: dict[str, str] = {}
    for claim_id in claim_to_docs:
        families[claim_id] = f"cited:{find(claim_id)}"
    return families


def families_from_split(split: str, claim_ids: Iterable[str] | None = None) -> dict[str, str]:
    """Build families from locked SciFact ``cited_doc_ids`` for ``split``."""
    from data.scifact_loader import load_split

    wanted = set(claim_ids) if claim_ids is not None else None
    claim_to_docs: dict[str, list[int]] = {}
    for bundle in load_split(split):
        claim_id = bundle.claim.claim_id
        if wanted is not None and claim_id not in wanted:
            continue
        native = bundle.native_claim
        cited = native.get("cited_doc_ids") if isinstance(native, dict) else None
        docs = [int(doc_id) for doc_id in cited] if isinstance(cited, list) else []
        claim_to_docs[claim_id] = docs
    if wanted is not None:
        missing = sorted(wanted - set(claim_to_docs))
        if missing:
            raise FamilyError(f"{len(missing)} claim ids are not in {split}: {missing[:5]}")
    return connected_components(claim_to_docs)


def attach_claim_families(
    rows: Sequence[Mapping[str, Any]],
    families: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Copy ``claim_family`` onto each row. Existing family fields are kept."""
    attached: list[dict[str, Any]] = []
    missing: list[str] = []
    for row in rows:
        claim_id = row.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            raise FamilyError("prediction row is missing claim_id")
        copied = dict(row)
        if not isinstance(copied.get("claim_family"), str) and not isinstance(
            copied.get("question_family"), str
        ):
            family = families.get(claim_id)
            if family is None:
                missing.append(claim_id)
            else:
                copied["claim_family"] = family
        attached.append(copied)
    if missing:
        raise FamilyError(f"{len(missing)} rows have no cited-doc family: {missing[:5]}")
    return attached
