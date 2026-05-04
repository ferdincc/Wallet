"""Helpers for symbol lists from query strings (comma-separated vs repeated params)."""
from typing import List


def expand_symbol_list(symbols: List[str]) -> List[str]:
    if not symbols:
        return []
    if len(symbols) == 1 and "," in symbols[0]:
        return [s.strip() for s in symbols[0].split(",") if s.strip()]
    return symbols
