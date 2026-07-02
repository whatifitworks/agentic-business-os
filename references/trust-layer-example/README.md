# Trust Layer — Worked Example

Lumen Candle Studio is a **fictional** one-person business used to show what the trust layer looks like after eight weeks of real use: an approval contract that graduated from observe to enforce, a ledger you can audit, and a memory benchmark that visibly improved. Every file here is in the exact format the live system writes.

## The eight weeks, briefly

- **May 4** — onboarding produced [approval-boundaries.yaml](approval-boundaries.yaml) in `observe` mode. Nothing blocked; every match logged.
- **May 12** — the observe log caught the agent about to send a campaign draft; the `ask` rule fired, confirming the contract matched a real risk (entry `led-000002` in [ledger.jsonl](ledger.jsonl)).
- **May 18** — two clean weeks later, the owner flipped `mode: enforce` (`led-000003`). From here ask/deny actually gate calls.
- **May 25 → June 29** — a supplier switch shows the full decision loop: decision with quoted evidence (`led-000004`), the owner-approved notice that went out (`led-000005`), and the outcome that validated it five weeks later (`led-000010`). "Why did we switch to NordWax?" is now answerable with `ledger.py query --contains nordwax`.
- **June 2** — enforce mode earning its keep: a credential read hit the `deny` rule (`led-000006`).
- **May 11 → June 29** — the memory benchmark climbed from 3/5 (with one contradiction — an old supplier claim still lurking in the wiki) to 5/5 clean: [golden-question-runs.jsonl](golden-question-runs.jsonl). The questions themselves are in [golden-questions.json](golden-questions.json); canonical paths like `wiki/entities/nordwax.md` refer to the fictional studio's vault.

## Things worth noticing

- The boundary rules are **business-specific**: campaign sends need eyes, supplier messages need eyes, refunds are owner-only at any amount. That specificity is what onboarding is for — compare with the generic starter contract in [rules/approval-boundaries.yaml](../../rules/approval-boundaries.yaml).
- The ledger chain in [ledger.jsonl](ledger.jsonl) is genuinely valid — the hashes were produced by `system/tools/ledger.py`. Copy it over a scratch `state/ledger.jsonl` and `verify` passes; edit any byte of a past entry and verify names the exact line.
- Outcomes reference the entries they close (`led-000008` → the newsletter action, `led-000010` → the supplier decision). That back-linking is what turns a log into an audit trail.
- The benchmark's first run **failing** was the system working: a stale claim ("wax comes from CandleCraft") was still findable, and the contradiction check caught it. The trend line records the cleanup, not just the happy end state.

## Reproduce the mechanics yourself

From the repo root, stage the example as a scratch project and poke it:

```bash
mkdir -p /tmp/lumen/rules /tmp/lumen/state
cp references/trust-layer-example/approval-boundaries.yaml /tmp/lumen/rules/
cp references/trust-layer-example/ledger.jsonl /tmp/lumen/state/

# a campaign send hits the ask rule (enforce mode)
python3 system/tools/approval_gate.py --root /tmp/lumen --check \
    --tool mcp__mailerlite__send_campaign --input '{"campaign_id": 3}'

# ...and that very check just logged itself; the chain still verifies
python3 system/tools/ledger.py --root /tmp/lumen verify
python3 system/tools/ledger.py --root /tmp/lumen show --limit 3
```

Then edit any byte of an old entry in `/tmp/lumen/state/ledger.jsonl` and run `verify` again — it names the exact line you touched. (On a machine without PyYAML, compile a JSON mirror first: `approval_boundaries_audit.py --compile`.)
