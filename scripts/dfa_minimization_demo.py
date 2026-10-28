#!/usr/bin/env python3
"""Deterministic command-line demonstration of complete-DFA minimization."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from regex_engine import match
from regex_engine.dfa import build_minimized_dfa
from regex_engine.nfa import build_nfa
from regex_engine.parser import parse


DEFAULT_PATTERN = "(ab|ac|db|dc)"
DEFAULT_INPUTS = ["ab", "ac", "db", "dc", "aa", "cb", "abc", ""]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", default=DEFAULT_PATTERN)
    parser.add_argument("inputs", nargs="*", default=DEFAULT_INPUTS)
    args = parser.parse_args()

    nfa = build_nfa(parse(args.pattern))
    minimized = build_minimized_dfa(nfa)
    before = sum(len(state.original_state_ids) for state in minimized.states)
    after = len(minimized.states)
    removed = before - after
    percent = 100.0 * removed / before if before else 0.0

    print(f"Pattern: {args.pattern}")
    print(f"NFA states: {len(nfa.states)}")
    print(f"Reachable complete DFA states: {before}")
    print(f"Minimized DFA states: {after}")
    print(f"Reduction: {removed} states ({percent:.1f}%)")
    print(f"Symbolic input classes: {len(minimized.classes)}")
    print("Partitions:")
    for state in minimized.states:
        originals = ", ".join(f"D{item}" for item in sorted(state.original_state_ids))
        flags = []
        if state.id == minimized.start.id:
            flags.append("start")
        if state.is_accept:
            flags.append("accept")
        if state.is_dead:
            flags.append("dead")
        suffix = f" ({', '.join(flags)})" if flags else ""
        print(f"  M{state.id} <- {originals}{suffix}")
    print("Input checks:")
    for text in args.inputs:
        result = match(args.pattern, text)
        label = "MATCH" if result.matches else "NO MATCH"
        shown = repr(text)
        print(f"  {shown:<8} {label}")


if __name__ == "__main__":
    main()
