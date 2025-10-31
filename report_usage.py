"""Resumo rápido dos custos/tokens registados em usage_log.csv."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict


def main(path: str) -> None:
    totals = defaultdict(lambda: {"prompt": 0, "completion": 0, "cost": 0.0, "count": 0})
    overall = {"prompt": 0, "completion": 0, "cost": 0.0, "count": 0}

    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                source = row.get("source", "unknown")
                prompt = int(row.get("prompt_tokens", 0) or 0)
                completion = int(row.get("completion_tokens", 0) or 0)
                cost = float(row.get("estimated_cost_usd", 0) or 0.0)

                totals[source]["prompt"] += prompt
                totals[source]["completion"] += completion
                totals[source]["cost"] += cost
                totals[source]["count"] += 1

                overall["prompt"] += prompt
                overall["completion"] += completion
                overall["cost"] += cost
                overall["count"] += 1
    except FileNotFoundError:
        print(f"❌ ficheiro '{path}' não encontrado. Corre um dos scripts primeiro.")
        return

    print(f"Relatório de custos — origem: {path}\n")
    print(f"Total de registos: {overall['count']}")
    print(f"Tokens prompt: {overall['prompt']:,}")
    print(f"Tokens completion: {overall['completion']:,}")
    print(f"Custo estimado: ${overall['cost']:.4f}\n")

    print("Por origem:")
    for source, data in sorted(totals.items(), key=lambda kv: kv[0]):
        print(
            f"- {source}: chamadas={data['count']}, prompt={data['prompt']:,}, "
            f"completion={data['completion']:,}, custo=${data['cost']:.4f}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default="usage_log.csv", help="caminho para o log (default: usage_log.csv)")
    args = parser.parse_args()
    main(args.path)


