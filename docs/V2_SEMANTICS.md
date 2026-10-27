# V2 semantics and safety budgets

## Matching model

The engine performs full-string matching. It does not search for a
matching substring. V1 syntax remains unchanged: literals, `.`, `|`,
concatenation, grouping, `*`, `+`, `?`, escapes, and the empty pattern.

## Character classes

- `[abc]` matches one listed Unicode code point.
- `[a-z]` expands an inclusive Unicode code-point range.
- `[^abc]` matches one code point not in the listed set. `^` negates only
  when it is the first character after `[`.
- Multiple entries and ranges may be combined, as in `[A-Za-z0-9_]`.
- `.`, `*`, `+`, `?`, `{`, `}`, `(`, `)`, and `|` are literals inside a
  class. Escape `\`, `[`, `]`, `^`, or `-` to use it literally.
- Empty, unterminated, descending, and incomplete ranges are rejected.
- Shorthand and set algebra (`\d`, `\w`, intersections, subtraction) are
  intentionally unsupported.

## Numeric quantifiers

- `x{m}` matches exactly `m` copies.
- `x{m,n}` matches between `m` and `n` copies, inclusive.
- `x{m,}` matches at least `m` copies with no syntax-level upper bound.
- `x{0}` matches the empty string and `x{0,1}` is equivalent to `x?`.
- Quantifiers operate on the immediately preceding atom or group. Only one
  postfix quantifier is permitted per atom. Because the engine is an
  automaton, greedy-versus-lazy ordering does not affect its boolean result.

Thompson construction expands numeric repetitions into required copies,
optional copies, and (for `{m,}`) one trailing Kleene star. Expansion is
bounded by both the per-quantifier and total-NFA limits below.

## DFA minimization

Normal matching still uses the existing on-demand `LazyDFA`. The minimized
view explicitly builds the reachable complete DFA, including its dead state,
over symbolic input-equivalence classes and then refines accepting and
non-accepting partitions until stable. This preserves V1's safe default while
making minimization inspectable and measurable on demand.

## Simulation

The NFA simulator reports the initial epsilon closure and, for each consumed
character, the previous active set, matching symbol transitions, move set,
next epsilon closure, and acceptance. The DFA simulator reports the current
DFA state and its underlying NFA subset. State numbering is deterministic for
a fixed pattern/input. Display traces are capped; matching continues after
the display cap so the final result remains correct.

## Performance procedure

`regex_engine.analysis.analyze` compiles a fresh AST/NFA, attempts bounded
complete-DFA minimization, warms one lazy DFA five times, then measures 1–100
matches with `time.perf_counter_ns`. It reports minimum, median, p95, maximum,
environment metadata, and a SHA-256 checksum of `pattern + NUL + input`.

Run the checked-in workloads with:

```bash
./.venv/bin/python scripts/benchmark.py --repeats 25 --output benchmarks/v2_baseline.json
```

Timings are observations for the recorded machine and are not portable
performance guarantees. The workload checksum and procedure metadata make
two runs comparable.

## Diagnostics

Malformed patterns return a stable error code, zero-based start/end position,
local context, caret pointer, and an optional repair hint. The public
`match()` function still never raises for malformed user input.

## Budgets

| Budget | Limit | Purpose |
|---|---:|---|
| Pattern length | 20,000 code points | Bound parsing work |
| Group nesting | 200 levels | Bound recursive grouping |
| Expanded class members | 4,096 per class | Bound range expansion |
| Numeric repeat count | 1,000 per bound | Reject huge `{m,n}` early |
| Expanded NFA | 50,000 states | Bound nested repeat expansion |
| Lazy DFA | 20,000 discovered states | Bound matching cache |
| Minimized-DFA input | 5,000 reachable states | Bound complete construction |
| Symbolic alphabet | 2,048 distinguishable classes | Bound minimization fan-out |
| Input length | 2,000,000 code points | Bound matching work |
| Simulation display | 500 steps | Bound API/UI payload |
| NFA transitions per displayed step | 200 | Bound simulation payload |
| NFA/DFA graph display | 500 / 300 states | Keep SVG usable |
| Analysis repetitions | 100 | Bound interactive benchmark time |
