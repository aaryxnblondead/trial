from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping
from uuid import uuid4


AUTO_APPROVE_THRESHOLD = 0.95
REVIEW_THRESHOLD = 0.80


@dataclass(frozen=True)
class MatchCandidate:
    left_entity_type: str
    left_entity_id: str | None
    left_entity_name: str
    right_entity_type: str
    right_entity_id: str | None
    right_entity_name: str
    match_type: str
    confidence_score: float
    match_reason: str
    source_document_id: str | None = None
    citation_locator: str | None = None


def name_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left.casefold(), right.casefold()).ratio()


def canonical_key(value: str) -> str:
    return " ".join(value.casefold().split())


def build_person_institution_candidates(person_rows: Iterable[Mapping[str, Any]], institution_rows: Iterable[Mapping[str, Any]]) -> list[MatchCandidate]:
    candidates: list[MatchCandidate] = []
    for person in person_rows:
        person_name = str(person["canonical_name"]).strip()
        person_key = canonical_key(person_name)
        if not person_key:
            continue
        for institution in institution_rows:
            institution_name = str(institution["canonical_name"]).strip()
            institution_key = canonical_key(institution_name)
            if not institution_key:
                continue

            direct_match = person_key == institution_key
            similarity = name_similarity(person_key, institution_key)
            role_bonus = 0.0
            role = str(person["person_role"]).casefold()
            if role in {"director", "trustee"} and "trust" in institution_key:
                role_bonus = 0.07
            elif role in {"director", "politician", "member"} and any(token in institution_key for token in ("school", "college", "university", "coaching", "academy", "education")):
                role_bonus = 0.05

            score = min(1.0, similarity + role_bonus)
            if direct_match:
                score = 1.0

            if score < REVIEW_THRESHOLD:
                continue

            if direct_match:
                reason = "exact_normalized_name"
                match_type = "deterministic_name"
            elif similarity >= 0.90:
                reason = f"high_name_similarity_{similarity:.3f}"
                match_type = "fuzzy_name"
            else:
                reason = f"role_context_plus_similarity_{similarity:.3f}"
                match_type = "contextual_fuzzy"

            candidates.append(
                MatchCandidate(
                    left_entity_type="person",
                    left_entity_id=person.get("person_id"),
                    left_entity_name=person_name,
                    right_entity_type="institution",
                    right_entity_id=institution.get("institution_id"),
                    right_entity_name=institution_name,
                    match_type=match_type,
                    confidence_score=score,
                    match_reason=reason,
                    source_document_id=person.get("source_document_id") or institution.get("source_document_id"),
                    citation_locator=person.get("citation_locator") or institution.get("citation_locator"),
                )
            )
    return candidates


def classify_match(candidate: MatchCandidate) -> str:
    if candidate.confidence_score >= AUTO_APPROVE_THRESHOLD:
        return "approved"
    if candidate.confidence_score >= REVIEW_THRESHOLD:
        return "review"
    return "rejected"


def review_priority(confidence_score: float) -> str:
    if confidence_score >= 0.92:
        return "high"
    if confidence_score >= 0.86:
        return "medium"
    return "low"


def generate_documentable_candidates(person_rows: Iterable[Mapping[str, Any]], institution_rows: Iterable[Mapping[str, Any]]) -> list[MatchCandidate]:
    return build_person_institution_candidates(person_rows, institution_rows)
