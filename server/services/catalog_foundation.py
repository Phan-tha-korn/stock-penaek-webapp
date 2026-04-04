from __future__ import annotations

import re
import unicodedata


MAX_PRODUCT_ALIASES = 5


def normalize_lookup_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("M"))
    text = re.sub(r"\s+", " ", text)
    return text


def validate_product_aliases(aliases: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in aliases:
        alias = unicodedata.normalize("NFKC", raw or "").strip()
        if not alias:
            continue
        normalized = normalize_lookup_text(alias)
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(alias)

    if len(cleaned) > MAX_PRODUCT_ALIASES:
        raise ValueError("too_many_aliases")
    return cleaned


def normalize_supplier_key(value: str) -> str:
    return normalize_lookup_text(value).replace(" ", "-")
