"""Utilities for logging OpenAI usage/costs in a single CSV file.

The challenge impõe limites de custo, por isso precisamos de guardar
tokens e custo estimado de cada chamada.
"""

from __future__ import annotations

import csv
import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional


LOG_PATH = os.getenv("USAGE_LOG_PATH", "usage_log.csv")
_lock = threading.Lock()


PRICING_USD_PER_1K = {
    "text-embedding-3-small": {"prompt": 0.00002, "completion": 0.0},
    # Valores oficiais OpenAI em Dez/2024
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.00060},
    "gpt-4o-mini-128k": {"prompt": 0.00015, "completion": 0.00060},
}


def _ensure_header(path: str) -> None:
    if os.path.exists(path):
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "timestamp",
                "source",
                "model",
                "prompt_tokens",
                "completion_tokens",
                "estimated_cost_usd",
                "metadata_json",
            ],
        )
        writer.writeheader()


def estimate_cost(model: str, prompt_tokens: int = 0, completion_tokens: int = 0) -> float:
    pricing = PRICING_USD_PER_1K.get(model)
    if not pricing:
        return 0.0
    prompt_cost = (prompt_tokens / 1000.0) * pricing["prompt"]
    completion_cost = (completion_tokens / 1000.0) * pricing["completion"]
    return round(prompt_cost + completion_cost, 8)


def log_usage(
    source: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Regista uso num CSV simples.

    Args:
        source: Nome do script ou endpoint (ex.: "embed_companies").
        model: Nome do modelo OpenAI usado.
        prompt_tokens: Tokens de input.
        completion_tokens: Tokens de output.
        metadata: Dict opcional com informação extra (ex.: batch, incentivo).
    """

    total_cost = estimate_cost(model, prompt_tokens, completion_tokens)

    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": source,
        "model": model,
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "estimated_cost_usd": total_cost,
        "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
    }

    with _lock:
        _ensure_header(LOG_PATH)
        with open(LOG_PATH, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(payload.keys()))
            writer.writerow(payload)


def extract_usage_fields(resp: Any) -> Dict[str, int]:
    """Helper para apanhar tokens a partir da resposta OpenAI."""

    usage = getattr(resp, "usage", None)
    if usage:
        prompt = getattr(usage, "prompt_tokens", 0) or usage.get("prompt_tokens", 0)
        completion = (
            getattr(usage, "completion_tokens", 0)
            or usage.get("completion_tokens", 0)
        )
        total = getattr(usage, "total_tokens", 0) or usage.get("total_tokens", 0)

        if prompt and not completion and total:
            completion = max(total - prompt, 0)

        return {
            "prompt_tokens": int(prompt or 0),
            "completion_tokens": int(completion or 0),
        }

    # Embeddings nem sempre devolvem usage -> devolve zeros
    return {"prompt_tokens": 0, "completion_tokens": 0}


__all__ = ["log_usage", "estimate_cost", "extract_usage_fields"]


