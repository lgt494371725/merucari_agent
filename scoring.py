import re
from typing import Dict, Iterable, List


MIN_DESCRIPTION_LENGTH = 30
SHORT_DESCRIPTION_PENALTY = 0.2
LENGTH_WEIGHT = 0.6
COVERAGE_WEIGHT = 0.4


def tokenize_keywords(keyword: str) -> List[str]:
    tokens = re.split(r"\s+", keyword.strip().lower())
    return [token for token in tokens if token]


def keyword_coverage(text: str, tokens: Iterable[str]) -> float:
    token_list = list(tokens)
    if not token_list:
        return 0.0
    lowered = text.lower()
    hits = sum(1 for token in token_list if token in lowered)
    return hits / len(token_list)


def normalize_lengths(lengths: List[int]) -> List[float]:
    if not lengths:
        return []
    max_len = max(lengths)
    if max_len <= 0:
        return [0.0 for _ in lengths]
    return [length / max_len for length in lengths]


def score_items(items: List[Dict[str, str]], keyword: str) -> List[Dict]:
    tokens = tokenize_keywords(keyword)
    lengths = [len((item.get("description") or "").strip()) for item in items]
    length_scores = normalize_lengths(lengths)

    scored_items: List[Dict] = []
    for idx, item in enumerate(items):
        title = item.get("title", "") or ""
        description = item.get("description", "") or ""
        combined = f"{title} {description}".strip()
        coverage_score = keyword_coverage(combined, tokens)
        length_score = length_scores[idx] if idx < len(length_scores) else 0.0
        final_score = (LENGTH_WEIGHT * length_score) + (COVERAGE_WEIGHT * coverage_score)

        description_length = len(description.strip())
        if description_length < MIN_DESCRIPTION_LENGTH:
            final_score *= SHORT_DESCRIPTION_PENALTY

        scored = {
            **item,
            "description_length": description_length,
            "length_score": round(length_score, 6),
            "coverage_score": round(coverage_score, 6),
            "final_score": round(final_score, 6),
        }
        scored_items.append(scored)

    return sorted(scored_items, key=lambda x: x["final_score"], reverse=True)
