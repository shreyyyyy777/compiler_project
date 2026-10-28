#!/usr/bin/env python3
"""Fair, reproducible V1-versus-V2 benchmark for the project review.

The controller launches a fresh interpreter for every version/workload/round
combination.  The worker imports the selected checkout directly, builds the
same shared-syntax workload, warms the lazy DFA, and records raw samples.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import importlib
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path


WORKLOADS = [
    {
        "name": "suffix-language",
        "pattern": "(a|b)*abb",
        "text": "ab" * 2_000 + "abb",
        "description": "Classic suffix language over a two-symbol alphabet",
    },
    {
        "name": "wildcard-scan",
        "pattern": "a.*z",
        "text": "a" + "x" * 4_000 + "z",
        "description": "Long wildcard scan with fixed start and end literals",
    },
    {
        "name": "alternation-loop",
        "pattern": "(ab|ac|db|dc)*",
        "text": "abacdbdc" * 500,
        "description": "Repeated alternation with equivalent DFA prefixes",
    },
]


def percentile(values: list[int], percent: int) -> int:
    ordered = sorted(values)
    index = min(len(ordered) - 1, (percent * len(ordered) + 99) // 100 - 1)
    return ordered[index]


def summary(values: list[int]) -> dict[str, int]:
    return {
        "minimum_ns": min(values),
        "median_ns": int(statistics.median(values)),
        "p95_ns": percentile(values, 95),
        "maximum_ns": max(values),
    }


def sha256_workload(pattern: str, text: str) -> str:
    return hashlib.sha256((pattern + "\0" + text).encode("utf-8")).hexdigest()


def count_transitions(nfa) -> tuple[int, int]:
    symbols = sum(
        len(targets)
        for state in nfa.states.values()
        for targets in state.transitions.values()
    )
    epsilon = sum(len(state.epsilon) for state in nfa.states.values())
    return symbols, epsilon


def run_dfa(dfa, text: str) -> bool:
    state = dfa.start
    for char in text:
        state = dfa.step(state, char)
        if state is None:
            return False
    return state.is_accept


def max_rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return int(value * 1024)
    return int(value)


def worker(args: argparse.Namespace) -> None:
    engine_root = Path(args.engine_root).resolve()
    sys.path.insert(0, str(engine_root))
    parser_module = importlib.import_module("regex_engine.parser")
    nfa_module = importlib.import_module("regex_engine.nfa")
    dfa_module = importlib.import_module("regex_engine.dfa")

    parse = parser_module.parse
    build_nfa = nfa_module.build_nfa
    LazyDFA = dfa_module.LazyDFA
    workload = next(item for item in WORKLOADS if item["name"] == args.workload)
    pattern = workload["pattern"]
    text_value = workload["text"]

    compile_samples: list[int] = []
    for index in range(args.compile_warmups + args.compile_repeats):
        started = time.perf_counter_ns()
        tree = parse(pattern)
        nfa = build_nfa(tree)
        LazyDFA(nfa)
        elapsed = time.perf_counter_ns() - started
        if index >= args.compile_warmups:
            compile_samples.append(elapsed)

    gc.collect()
    tracemalloc.start()
    started = time.perf_counter_ns()
    tree = parse(pattern)
    nfa = build_nfa(tree)
    dfa = LazyDFA(nfa)
    compile_memory_elapsed_ns = time.perf_counter_ns() - started
    compile_current, compile_peak = tracemalloc.get_traced_memory()

    expected = run_dfa(dfa, text_value)
    for _ in range(args.warmups):
        if run_dfa(dfa, text_value) is not expected:
            raise RuntimeError("warmup result changed")

    gc.collect()
    match_base, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    if run_dfa(dfa, text_value) is not expected:
        raise RuntimeError("memory probe result changed")
    _, match_peak = tracemalloc.get_traced_memory()
    match_peak_incremental = max(0, match_peak - match_base)
    tracemalloc.stop()

    samples: list[int] = []
    for _ in range(args.repeats):
        started = time.perf_counter_ns()
        actual = run_dfa(dfa, text_value)
        samples.append(time.perf_counter_ns() - started)
        if actual is not expected:
            raise RuntimeError("measured result changed")

    symbol_transitions, epsilon_transitions = count_transitions(nfa)
    minimization = {"supported": False}
    build_minimized_dfa = getattr(dfa_module, "build_minimized_dfa", None)
    if build_minimized_dfa is not None:
        minimized = build_minimized_dfa(nfa)
        minimization = {
            "supported": True,
            "reachable_complete_dfa_states": sum(
                len(state.original_state_ids) for state in minimized.states
            ),
            "minimized_dfa_states": len(minimized.states),
            "alphabet_classes": len(minimized.classes),
        }

    payload = {
        "version": args.version,
        "engine_root": str(engine_root),
        "round": args.round,
        "workload": {
            "name": workload["name"],
            "description": workload["description"],
            "pattern": pattern,
            "pattern_length": len(pattern),
            "input_length": len(text_value),
            "sha256": sha256_workload(pattern, text_value),
        },
        "parameters": {
            "compile_warmups": args.compile_warmups,
            "compile_repeats": args.compile_repeats,
            "match_warmups": args.warmups,
            "match_repeats": args.repeats,
            "timer": "time.perf_counter_ns",
            "memory_probe": "tracemalloc peak Python allocations",
            "matching_mode": "warm lazy DFA, direct full-string DFA traversal",
        },
        "result": {
            "matches": expected,
            "compile_samples_ns": compile_samples,
            "compile_memory_probe_elapsed_ns": compile_memory_elapsed_ns,
            "compile_current_python_bytes": compile_current,
            "compile_peak_python_bytes": compile_peak,
            "match_samples_ns": samples,
            "match_peak_incremental_python_bytes": match_peak_incremental,
            "process_max_rss_bytes": max_rss_bytes(),
            "nfa_states": len(nfa.states),
            "nfa_symbol_transitions": symbol_transitions,
            "nfa_epsilon_transitions": epsilon_transitions,
            "lazy_dfa_states_explored": dfa.explored_state_count,
            "minimization": minimization,
        },
    }
    print(json.dumps(payload, separators=(",", ":")))


def git_value(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_worker(
    script: Path,
    python: Path,
    version: str,
    root: Path,
    workload: str,
    round_number: int,
    args: argparse.Namespace,
) -> dict:
    command = [
        str(python),
        str(script),
        "--worker",
        "--version",
        version,
        "--engine-root",
        str(root),
        "--workload",
        workload,
        "--round",
        str(round_number),
        "--warmups",
        str(args.warmups),
        "--repeats",
        str(args.repeats),
        "--compile-warmups",
        str(args.compile_warmups),
        "--compile-repeats",
        str(args.compile_repeats),
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"},
    )
    return json.loads(completed.stdout)


def aggregate(raw_runs: list[dict], versions: list[str]) -> list[dict]:
    rows = []
    for workload in WORKLOADS:
        for version in versions:
            selected = [
                run
                for run in raw_runs
                if run["version"] == version
                and run["workload"]["name"] == workload["name"]
            ]
            match_samples = [
                sample
                for run in selected
                for sample in run["result"]["match_samples_ns"]
            ]
            compile_samples = [
                sample
                for run in selected
                for sample in run["result"]["compile_samples_ns"]
            ]
            first = selected[0]
            rows.append(
                {
                    "version": version,
                    "workload": workload["name"],
                    "description": workload["description"],
                    "pattern": workload["pattern"],
                    "input_length": len(workload["text"]),
                    "workload_sha256": first["workload"]["sha256"],
                    "matches": first["result"]["matches"],
                    "match_samples": len(match_samples),
                    **{f"match_{key}": value for key, value in summary(match_samples).items()},
                    **{f"compile_{key}": value for key, value in summary(compile_samples).items()},
                    "compile_peak_python_bytes_median": int(
                        statistics.median(
                            run["result"]["compile_peak_python_bytes"] for run in selected
                        )
                    ),
                    "match_peak_incremental_python_bytes_median": int(
                        statistics.median(
                            run["result"]["match_peak_incremental_python_bytes"]
                            for run in selected
                        )
                    ),
                    "process_max_rss_bytes_median": int(
                        statistics.median(
                            run["result"]["process_max_rss_bytes"] for run in selected
                        )
                    ),
                    "nfa_states": first["result"]["nfa_states"],
                    "lazy_dfa_states_explored": first["result"]["lazy_dfa_states_explored"],
                    "minimization": first["result"]["minimization"],
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "version",
        "workload",
        "pattern",
        "input_length",
        "workload_sha256",
        "matches",
        "match_samples",
        "match_minimum_ns",
        "match_median_ns",
        "match_p95_ns",
        "match_maximum_ns",
        "compile_minimum_ns",
        "compile_median_ns",
        "compile_p95_ns",
        "compile_maximum_ns",
        "compile_peak_python_bytes_median",
        "match_peak_incremental_python_bytes_median",
        "process_max_rss_bytes_median",
        "nfa_states",
        "lazy_dfa_states_explored",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def controller(args: argparse.Namespace) -> None:
    script = Path(__file__).resolve()
    python = Path(args.python).resolve()
    roots = {"V1": Path(args.v1_root).resolve(), "V2": Path(args.v2_root).resolve()}
    revisions = {
        "V1": args.v1_revision,
        "V2": git_value(roots["V2"], "rev-parse", "HEAD"),
    }
    raw_runs = []
    for round_number in range(1, args.rounds + 1):
        order = ["V1", "V2"] if round_number % 2 else ["V2", "V1"]
        for workload in WORKLOADS:
            for version in order:
                raw_runs.append(
                    run_worker(
                        script,
                        python,
                        version,
                        roots[version],
                        workload["name"],
                        round_number,
                        args,
                    )
                )

    rows = aggregate(raw_runs, ["V1", "V2"])
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "procedure_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "comparison_scope": (
            "Only syntax supported by both V1 and V2; V2-only character classes "
            "and numeric quantifiers are excluded from version ratios."
        ),
        "revisions": revisions,
        "environment": {
            "python_executable": str(python),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "pythonhashseed": "0",
        },
        "protocol": {
            "fresh_process_per_version_workload_round": True,
            "rounds": args.rounds,
            "alternating_version_order": True,
            "compile_warmups_per_round": args.compile_warmups,
            "compile_repeats_per_round": args.compile_repeats,
            "match_warmups_per_round": args.warmups,
            "match_repeats_per_round": args.repeats,
            "timer": "time.perf_counter_ns",
            "memory": (
                "tracemalloc peak Python allocations plus process maximum RSS; "
                "RSS is coarse and includes interpreter/module overhead"
            ),
        },
        "summary": rows,
        "raw_runs": raw_runs,
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_csv(output.with_suffix(".csv"), rows)
    print(json.dumps({"json": str(output), "csv": str(output.with_suffix('.csv'))}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--version")
    parser.add_argument("--engine-root")
    parser.add_argument("--workload", choices=[item["name"] for item in WORKLOADS])
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--v1-root")
    parser.add_argument("--v2-root")
    parser.add_argument("--v1-revision", default="09de2a6030aae192d5d46337ba921fc51e2aa3f5")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", default="benchmarks/review_2026_10_27/v1_v2_comparison.json")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=40)
    parser.add_argument("--compile-warmups", type=int, default=5)
    parser.add_argument("--compile-repeats", type=int, default=20)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.worker:
        worker(args)
    else:
        missing = [name for name in ("v1_root", "v2_root") if not getattr(args, name)]
        if missing:
            raise SystemExit("controller requires --v1-root and --v2-root")
        controller(args)


if __name__ == "__main__":
    main()
