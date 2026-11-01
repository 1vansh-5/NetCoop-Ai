# Verification record

Verified locally on 31 October 2026 with Python 3.14 and the pinned dependency versions in `requirements.txt`.

## Automated checks

- **32 tests passed** in the final test run (13.88 seconds).
- Python source compilation completed successfully.
- JavaScript syntax check (`node --check static/app.js`) completed successfully.
- Actual MCP subprocess connections, tool discovery and specialist calls completed successfully.
- Streamed HTTP diagnosis and SQLite save/retrieve behavior passed integration tests.
- Mixed-fault end-to-end check returned `insufficient_evidence` with competing support scores of 1.45 for congestion and 1.35 for interface fault.

The test runner needed a workspace-local temporary directory in the verification environment. A normal installation can use `python -m pytest -q`. If temporary-directory permissions are restricted, pass `--basetemp` with a new empty writable path.

## Browser checks

- Dashboard loaded in a narrow view and a desktop view with responsive navigation, scenario controls and telemetry cards.
- A browser-triggered congestion investigation completed through real MCP in approximately 4.4 seconds.
- The displayed report correctly identified `HOSTEL_CORE_SW_01`, 94% utilization, 160 packets/second queue drops, and a 91% heuristic confidence score.
- The visible trace contained 21 structured events and the evidence ledger contained five findings.
- The 3D spatial workflow and diagnostic report were visually inspected together; the layout displayed without overlapping panels.
- Incident API retrieval confirmed the completed investigation was persisted.

## Google integration boundary

No user Google key was supplied. **No live Google API success is claimed.** Tests simulate model responses to verify the multi-turn tool loop, tool invocation, opaque thought-signature preservation, matching function IDs, and safe provider-failure fallback. Verify your account, chosen model and quota with your own key before the presentation.

## Remaining submission steps

The source package is runnable and repository-ready. Publishing it to your own GitHub account and recording the requested demonstration video are separate submission steps. `DEMO_SCRIPT.md` provides the recording plan. Production telemetry collection, authenticated multi-user deployment, calibrated confidence and automatic remediation are outside this prototype.
