# Computer Use Adapter Fixture Steps

Use this adapter only to verify the adapter contract machinery.

1. Define a workflow name, target, expected fields, and caveats.
2. Run `python3 system/tools/browser_computer_adapter.py record`.
3. Confirm a JSON run record and Markdown evidence note appear under `sources/adapters/runs/`.
4. Run `python3 system/tools/browser_computer_adapter.py validate`.
5. Treat this as contract evidence, not live UI evidence.
