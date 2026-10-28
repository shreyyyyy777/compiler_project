# DFA Minimization Live Demonstration

## Demonstration goal

Show that minimization merges equivalent complete-DFA states without changing the accepted language. The pattern `(ab|ac|db|dc)` is deliberately redundant: after reading `a` or `d`, the remaining legal suffixes are identical (`b` or `c`). Its reachable complete DFA has 8 states, including the dead state. Partition refinement reduces it to 4 states, a 50.0% reduction.

## Fast command-line proof

Run:

```bash
cd /Users/shrey/Documents/compiler/project
./.venv/bin/python scripts/dfa_minimization_demo.py
```

Expected output:

```text
Pattern: (ab|ac|db|dc)
NFA states: 18
Reachable complete DFA states: 8
Minimized DFA states: 4
Reduction: 4 states (50.0%)
Symbolic input classes: 5
Partitions:
  M0 <- D0 (start)
  M1 <- D1, D3
  M2 <- D2 (dead)
  M3 <- D4, D5, D6, D7 (accept)
Input checks:
  'ab'     MATCH
  'ac'     MATCH
  'db'     MATCH
  'dc'     MATCH
  'aa'     NO MATCH
  'cb'     NO MATCH
  'abc'    NO MATCH
  ''       NO MATCH
```

## Dashboard flow

Start the server:

```bash
cd /Users/shrey/Documents/compiler/project
./.venv/bin/python -m uvicorn server.main:app --reload --port 8008
```

Open `http://127.0.0.1:8008` and follow this sequence:

1. Enter `(ab|ac|db|dc)` in **Regular Expression**.
2. Open **Automaton** and select **DFA (lazy)**. Point out the separate branches reached by `a` and `d`, and the four accepting endpoints.
3. Select **DFA (minimized)**. Read the dashboard result: `Minimized 8 reachable complete-DFA states to 4.`
4. Explain that the drawing shows 3 states because the dashboard deliberately omits the dead state and dead-state-only edges for readability. The complete minimized automaton still has 4 states.
5. Open **Match** and test the strings below.

| Input | Expected result | Reason |
|---|---|---|
| `ab` | MATCH | First symbol `a`, second symbol `b` |
| `ac` | MATCH | First symbol `a`, second symbol `c` |
| `db` | MATCH | First symbol `d`, second symbol `b` |
| `dc` | MATCH | First symbol `d`, second symbol `c` |
| `aa` | NO MATCH | Second symbol is outside `{b,c}` |
| `cb` | NO MATCH | First symbol is outside `{a,d}` |
| `abc` | NO MATCH | Matching uses the full string, so the extra `c` rejects |
| empty input | NO MATCH | The pattern requires exactly two characters |

## Algorithm explanation for the review

The engine first builds every reachable complete-DFA state over symbolic input classes. It starts with two partitions: accepting and non-accepting states. For each partition, it compares where every state goes for each input class. States with different transition signatures split into separate partitions. Refinement stops when no partition changes. Each final partition becomes one minimized state.

For this pattern, states reached after `a` and `d` are equivalent because both accept exactly the same remaining suffixes: `b` or `c`. All four accepting endpoints are also equivalent because they have the same acceptance status and the same outgoing behavior. The dead state remains separate.

## API fallback

If the graph does not render, keep the server running and use:

```bash
curl -sS -X POST http://127.0.0.1:8008/api/automaton \
  -H 'Content-Type: application/json' \
  -d '{"regex":"(ab|ac|db|dc)","kind":"min_dfa"}' \
  | ./.venv/bin/python -m json.tool
```

The key fields must be:

```json
{
  "reachable_states_before": 8,
  "states_after": 4,
  "states_drawn": 3,
  "dead_state_omitted": true
}
```

## Verified fallback images

- Before minimization: [lazy DFA](assets/dashboard_lazy_dfa.jpg)
- After minimization: [minimized DFA](assets/dashboard_minimized_dfa.jpg)

The screenshots were captured from the local dashboard with the demonstration pattern on the verified V2 branch.
