# Readiness and Recording Preflight Proof — 2026-10-10

## Summary

This document records the readiness verification for the Cribl log-triage demo (`demo-expanso-jev`, `demos/01-log-triage`), with deterministic Expanso Edge pre-filtering and local open-weight Cribl `cribl-decision-1.0` classification.

All automated mechanical checks, UI linting, media licensing, headless browser layout invariants, and recording preflight gates have passed.

---

## Checks Executed and Results

### 1. Repository Pipeline Validation (`just validate`)
- Command: `expanso-edge validate <pipeline>` across all 13 pipeline configs in `demos/`.
- Result: **PASS** (13/13 valid).

### 2. Unit and Integration Test Suites (`just test`, `just ui-test`)
- Pod labels suite (`demos/11-pod-labels/test_*.py`): **PASS** (93 unit & scenario tests passed).
- Dashboard server security & integrity (`demos/01-log-triage/tests/ui_server_tests.py`): **PASS** (72/72 tests passed).
- Log safety and operational processor constraints (`demos/01-log-triage/tests/log_safety_test.py`): **PASS** (46/46 tests passed).

### 3. Shared Public Bar Static Lane (`just public-bar static`)
- Command: `NODE_ID=edge-1 uv run -s .demo-kit/public-bar.py --repo . --manifest public-bar.toml --report artifacts/public-bar.md --lane static`
- Criterion 1 (Runs): **PASS** (12 static/recorded replays succeeded).
- Criterion 2 (Platform): **PASS** (macOS Darwin arm64).
- Criterion 3 (Structure): **PASS** (`public-bar.toml` matches repository structure).
- Criterion 4 (Accessibility): Skipped for static lane as designed.
- Criterion 5 (Regressions): **PASS** (retained features matched).
- Report: Saved to `artifacts/public-bar.md`.

### 4. Demo UI & Video Presentation Lint (`just lint-ui`)
- Command: `uv run -s .demo-kit/lint-demo-ui.py demos/01-log-triage --video`
- Radius scale: Adheres strictly to kit tokens (`[0, 2px, 4px, 8px, 16px, 50%, 9999px]`).
- Internal scrollbars: Zero internal overflow scrollbars (`overflow: visible` with pre-wrap on data views).
- Typography: All visible text font sizes $\ge$ 13px.
- Callouts: All declared regions (`masthead`, `stage`, `destination`, `shelf-accounting`) have explicit `.callout` elements.
- Media licenses: Every vector SVG in `media/` is licensed and documented in `media/LICENSES.md`.
- Result: **PASS** (`=== 01-log-triage: clean`, 0 errors, 0 warnings).

### 5. Isolated Headless Browser Proof (`just record-check`)
- Command: `uv run --with playwright python tools/prove_board.py`
- Headless Chromium browser automation via Playwright.
- Viewports tested:
  - **1440x900**: Verified `scrollWidth <= innerWidth` (zero horizontal overflow), masthead brand layout (`LOG TRIAGE PIPELINE` eyebrow over `EXPANSO × CRIBL`), model node branding (`CRIBL (LOCAL 4B)`), and region callouts.
  - **1920x1080**: Verified `scrollWidth <= innerWidth`, stage layout geometry, and evidence strip rendering.
- Screenshots committed:
  - `docs/proof/1440x900-triage-board.png`
  - `docs/proof/1920x1080-triage-board.png`
- Result: **PASS** (`ALL HEADLESS PROOF CHECKS PASSED`).

### 6. Recording Preflight Declaration (`just recording-preflight`)
- Command: `uv run -s .demo-kit/recording-preflight.py .`
- Required frontmatter fields (`status`, `record_check`, `record_check_evidence`, `accepted_warnings`) validated.
- All 9 required sections present and non-placeholder.
- Result: **PASS** (`PASS: recording preflight declared ready: RECORDING_PREFLIGHT.md`).

---

## Cloud Rehearsal & Model Boundary

1. **Expanso Cloud Connectivity**:
   - The permanent repository checkout (`/Users/daaronch/code/second-brain/projects/demos/demo-expanso-jev`) possesses verified project-local credentials in its `.env` (`EXPANSO_CLI_ENDPOINT`, `EXPANSO_CLI_AUTH_API_KEY`, `EXPANSO_EDGE_BOOTSTRAP_TOKEN`).
   - Verified reachable via `just doctor` in the permanent folder.
   - Worktree isolation preserved: `.env` and `.cloud-state` are never copied into this disposable worktree, and no secrets appear in flags or command arguments.

2. **Model Boundary & Inference**:
   - The primary decision backend for this demo is Cribl's open-weight `cribl-decision-1.0` (4B LoRA adapter on Qwen3.5-4B-Base) served on-machine via `shared/cribl-decision-server.py` on `:8100`.
   - Conforms strictly to the zero-metered-API policy: all model calls are served locally on-machine with zero external cloud API metering or external data transmission.
