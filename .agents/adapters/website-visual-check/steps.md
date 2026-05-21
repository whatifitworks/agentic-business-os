# Website Visual Check Steps

Legacy Browser contract. Do not use this for new adapter recording. New flows should use Computer Use through the named app.

## Inputs

- `url`: page to inspect.
- `viewport`: desktop, mobile, or exact dimensions.
- `checklist`: comma-separated checks, such as hero visible, CTA visible, no overlap, store buttons visible.
- `expected_signals`: specific text, link, element, or visual state expected on the page.

## Procedure

1. Open the target URL in Browser.
2. Set or note the viewport.
3. Wait for network and visible layout to settle.
4. Capture screenshot or browser evidence.
5. Check each requested signal against visible evidence.
6. Record the run with:

   ```bash
   python3 system/tools/browser_computer_adapter.py record \
     --adapter website-visual-check \
     --tool-type Computer \
     --target "<url>" \
     --input viewport="<viewport>" \
     --input checklist="<checklist>" \
     --field result="<short result>" \
     --evidence-artifact "<screenshot-or-artifact-path>"
   ```

7. Use `--create-inbox-envelope` only when the result has durable business or product value.

## Failure Behavior

Record `blocked` or `failed` instead of guessing when:

- Browser cannot load the page.
- Login or manual verification appears.
- Screenshot/evidence is missing.
- A checklist item is ambiguous.
- The UI differs from the recorded steps.
