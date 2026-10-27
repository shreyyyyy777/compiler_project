#!/usr/bin/env python3
"""Run the fixed V2 benchmark set or one explicit pattern/input pair."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from regex_engine.analysis import DEFAULT_REPEATS, analyze

FIXED_WORKLOADS = [
    {"name": "suffix-language", "pattern": "(a|b)*abb", "text": "ab" * 2_000 + "abb"},
    {"name": "class-and-range", "pattern": "[A-Za-z0-9_]{4,32}", "text": "RegexEngineV2_2026"},
    {"name": "negated-class", "pattern": "[^,]{1,1000}", "text": "x" * 1_000},
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern")
    parser.add_argument("--text")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if (args.pattern is None) != (args.text is None):
        parser.error("--pattern and --text must be supplied together")

    workloads = (
        [{"name": "custom", "pattern": args.pattern, "text": args.text}]
        if args.pattern is not None
        else FIXED_WORKLOADS
    )
    payload = {
        "command": "./.venv/bin/python scripts/benchmark.py --repeats " + str(args.repeats),
        "workloads": [
            {"name": item["name"], **analyze(item["pattern"], item["text"], args.repeats)}
            for item in workloads
        ],
    }
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
