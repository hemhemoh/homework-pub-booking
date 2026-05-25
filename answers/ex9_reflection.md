# Ex9 — Reflection

## Q1 — Planner handoff decision

### Your answer

In my Ex7 run (session `sess_845852e2c1b3`), round 1 shows how control
moves from the loop half to the structured half. The planner's first
subgoal (`sg_1` in ticket `tk_aea131fd`) is assigned to the loop half:
"find venue near haymarket for 12" with `assigned_half: "loop"`. The
planner does not directly assign a structured subgoal here — research
stays on the stochastic side.

The handoff trigger appears one step later, when the executor calls
`handoff_to_structured` (trace line 5, ticket `tk_7f9c7676`). The tool
reason is explicit: "loop half identified a candidate venue; passing to
structured half for confirmation under policy rules." The signal is the
shift from open-ended venue search to deterministic policy enforcement
(party-size cap, deposit ceiling) — work the loop half should not
self-certify.

The bridge then writes `ipc/handoff_to_structured.json` and emits
`session.state_changed` from `loop` to `structured` (trace line 6).
Rasa rejects the party of 12 (`party_too_large`, trace line 7), and the
bridge reverses to the loop with the rejection reason preserved — which
is exactly the bidirectional pattern Ex7 teaches.

The lesson: planner prose assigns *which half owns the subgoal*, but the
actual cross-process handoff is an executor tool call plus IPC file
write. Policy-bound confirmation must land in structured Python, not in
planner reasoning alone.

### Citation

- `sessions/sess_845852e2c1b3/logs/tickets/tk_aea131fd/raw_output.json` (planner subgoal, `assigned_half: "loop"`)
- `sessions/sess_845852e2c1b3/logs/tickets/tk_7f9c7676/raw_output.json` (`handoff_to_structured` call)
- `sessions/sess_845852e2c1b3/logs/trace.jsonl:5-7`

---

## Q2 — Dataflow integrity catch

### Your answer

My offline Ex5 runs passed integrity (`verify_dataflow` reported four
verified facts), so I never saw a live catch in my own session dirs.
However, the check is designed for a failure mode I would definitely
miss manually: plausible-but-wrong numbers in the flyer.

Concrete test case someone else could build: run Ex5 offline with a
scripted executor that calls `calculate_cost` returning
`total_gbp=540` and `deposit_gbp=0`, then call `generate_flyer` with
HTML containing `<dd>£560</dd>` and `<dd>£112</dd>`. A human reviewer
sees internally consistent figures (20% deposit of £560 is £112) and
approves. `verify_dataflow` in `integrity.py` extracts every `£` fact
from the flyer and checks each against `_TOOL_CALL_LOG` via
`fact_appears_in_log`. £560 and £112 never appeared in any tool output,
so the check returns `ok=False` with `unverified_facts=['£560','£112']`
even though the prose looks reasonable.

The grader's own comments in `integrity.py` mention planting £9999 for
the same reason — facts that "look wrong" are easy; facts that "look
right" are the point. Manual review compares narrative coherence; integrity
compares against ground-truth tool outputs. That gap is where production
agents silently lie.

To reproduce locally: after a green `make ex5`, edit `workspace/flyer.html`
to swap one verified total for £9999 and re-run only the integrity step —
it should fail while the HTML still renders fine in a browser.

### Citation

- `starter/edinburgh_research/integrity.py:118-157` (`verify_dataflow` logic)
- `starter/edinburgh_research/integrity.py:7-9` (grader plants £9999 comment)
- Offline Ex5 run output: `dataflow OK: verified 4 fact(s) against tool outputs`

---

## Q3 — Production failure

### Your answer

The first production failure I would expect is a **stale or duplicate
handoff file in `ipc/`** after a partial round-trip — e.g. the loop half
writes `handoff_to_structured.json`, Rasa rejects or crashes mid-flow, and
a retry leaves two handoff files visible at once. I hit a mild version of
this coordination problem running Ex6: `make ex6-real` probed
`localhost:5005` and `5055` before both Rasa processes were up and got
connection refused — the structured half was unreachable even though my
Python bridge was ready to send.

In production that becomes: loop enqueues work, structured half is down
for a deploy, handoff JSON sits in `ipc/` while the loop half tries again.
The sovereign-agent **IPC atomic rename** primitive (fail-closed rule: at
most one handoff file in `ipc/` at any time) is what surfaces this — not
as a subtle wrong booking, but as `SA_IO_MALFORMED_HANDOFF_STATE` before
any bad commit reaches a customer. Ex7's bridge already archives the
forward handoff on reverse (`bridge.py` moves `handoff_to_structured.json`
into `logs/handoffs/` before round 2); without that discipline, a human
operator would see "booking confirmed" in loop logs while structured never
ran.

One primitive: **IPC atomic rename / fail-closed handoff state**. One
failure mode: **duplicate or orphaned handoff files after structured-half
unavailability**.

### Citation

- `sessions/sess_845852e2c1b3/logs/trace.jsonl:6-7` (forward handoff then structured rejection)
- `starter/handoff_bridge/bridge.py:147-151` (archive stale forward handoff on reverse)
- Ex6-real terminal output: connection refused on `:5005` / `:5055` before Rasa was ready
