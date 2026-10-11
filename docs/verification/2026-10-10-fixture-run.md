# Fixture run, 2026-10-10

Every shipped pipeline was deployed unmodified to a local `expanso-edge run --local` agent and fed its shipped input one record at a time. Jev answers were replayed from each example's recorded file; nothing called a model, and the agent had no Expanso Cloud credentials. What each pipeline wrote was compared with the committed expected output (`received_at`-style fields removed from both sides).

- Date: 2026-10-10
- Agent: v2.1.22
- Command: `uv run -s tools/fixture-runner.py run`
- Result: **23 of 23 cases passed** across 13 pipelines

| Case | Pipeline | Inputs | Jev calls | Queues written | File-in replay | Seconds | Result |
|---|---|---|---|---|---|---|---|
| 01-log-triage:logging | `demos/01-log-triage/pipeline-logging.yaml` | 16 | 0 | logs 16 | 16 records | 5.5 | pass |
| 01-log-triage:recurrence | `demos/01-log-triage/pipeline-recurrence.yaml` | 16 | 11 | archive 5, notify 2, page 1, review 8 | 16 records | 10.2 | pass |
| 01-log-triage:outage | `demos/01-log-triage/pipeline-recurrence.yaml` | 3 | 64 | archive 2, held 1, review 1 | not run | 99.9 | pass |
| 02-ticket-router:main | `demos/02-ticket-router/pipeline.yaml` | 6 | 6 | page 1, priority 1, routed-billing 1, routed-sales 1, routed-technical 2 | 6 records | 4.8 | pass |
| 02-ticket-router:jev_down | `demos/02-ticket-router/pipeline.yaml` | 6 | 12 | triage 6 | not run | 8.1 | pass |
| 03-sensitivity-masking:main | `demos/03-sensitivity-masking/pipeline.yaml` | 5 | 5 | forwarded 3, quarantine 2 | 5 records | 5.0 | pass |
| 03-sensitivity-masking:jev_down | `demos/03-sensitivity-masking/pipeline.yaml` | 5 | 10 | quarantine 5 | not run | 7.1 | pass |
| 04-sensor-triage:main | `demos/04-sensor-triage/pipeline.yaml` | 5 | 5 | dispatch 1, flagged 1, rollup 3 | 5 records | 4.9 | pass |
| 04-sensor-triage:jev_down | `demos/04-sensor-triage/pipeline.yaml` | 5 | 10 | flagged 5 | not run | 7.1 | pass |
| 05-agent-guardrail:main | `demos/05-agent-guardrail/pipeline.yaml` | 5 | 5 | allowed 2, blocked 3 | 5 records | 5.0 | pass |
| 05-agent-guardrail:jev_down | `demos/05-agent-guardrail/pipeline.yaml` | 5 | 10 | blocked 5 | not run | 6.9 | pass |
| 06-smart-sampling:main | `demos/06-smart-sampling/pipeline.yaml` | 8 | 8 | kept 2 | 2 records | 5.1 | pass |
| 06-smart-sampling:jev_down | `demos/06-smart-sampling/pipeline.yaml` | 8 | 16 | kept 8 | not run | 9.9 | pass |
| 07-soc-prefilter:main | `demos/07-soc-prefilter/pipeline.yaml` | 5 | 5 | cold 2, siem 1, warm 2 | 5 records | 4.8 | pass |
| 07-soc-prefilter:jev_down | `demos/07-soc-prefilter/pipeline.yaml` | 5 | 10 | warm 5 | not run | 6.9 | pass |
| 08-data-quality:main | `demos/08-data-quality/pipeline.yaml` | 5 | 5 | quarantine 3, warehouse 2 | 5 records | 4.8 | pass |
| 08-data-quality:jev_down | `demos/08-data-quality/pipeline.yaml` | 5 | 10 | quarantine 5 | not run | 6.9 | pass |
| 09-moderation:main | `demos/09-moderation/pipeline.yaml` | 5 | 5 | allowed 2, review 3 | 5 records | 5.0 | pass |
| 09-moderation:jev_down | `demos/09-moderation/pipeline.yaml` | 5 | 10 | review 5 | not run | 7.1 | pass |
| 10-feedback-miner:main | `demos/10-feedback-miner/pipeline.yaml` | 5 | 5 | alert 1, analytics 3, eng 1 | 5 records | 4.6 | pass |
| 10-feedback-miner:jev_down | `demos/10-feedback-miner/pipeline.yaml` | 5 | 10 | analytics 5 | not run | 6.9 | pass |
| 11-pod-labels | `demos/11-pod-labels/pipeline.yaml` | 6 | 6 | events 33, labels 7, receipts 6 | 6 records | 58.1 | pass |
| 12-ade-schedule | `demos/12-ade-schedule/pipeline.yaml` | 29 | 0 | must-see 4, pass 2, worth-it 23 | 29 records | 4.5 | pass |

## Files exercised

| File | sha256 |
|---|---|
| `demos/01-log-triage/pipeline-logging.yaml` | `aaa7614cd053a34e48140855e44a4560f8664bd23ec0f1ef1e9bfdf5bfcf47c3` |
| `demos/01-log-triage/input.jsonl` | `f7a8afd40dc7e3f26f40de9a1e71deb39486d945b7d539cac7d226f898ceafcc` |
| `demos/01-log-triage/pipeline-recurrence.yaml` | `c6eafe748be3060d7a5efb572ab87812a0a4528f3e04e05956f880c0a7352680` |
| `demos/01-log-triage/input.jsonl` | `f7a8afd40dc7e3f26f40de9a1e71deb39486d945b7d539cac7d226f898ceafcc` |
| `demos/01-log-triage/pipeline-recurrence.yaml` | `c6eafe748be3060d7a5efb572ab87812a0a4528f3e04e05956f880c0a7352680` |
| `demos/01-log-triage/input-outage.jsonl` | `a51bf3310cf8513fa027ae1f92b12f389d7b0faad0abafaaef411a3c9d0c66db` |
| `demos/02-ticket-router/pipeline.yaml` | `0ce9346a98bcace4355cae50b008f1a50ebedf22ce6fd4e0acfc616f0311214c` |
| `demos/02-ticket-router/input.jsonl` | `e420978e2a39aa7175bbfa047e882f563aba64029bd55a8d540543b18d494e7b` |
| `demos/02-ticket-router/pipeline.yaml` | `0ce9346a98bcace4355cae50b008f1a50ebedf22ce6fd4e0acfc616f0311214c` |
| `demos/02-ticket-router/input.jsonl` | `e420978e2a39aa7175bbfa047e882f563aba64029bd55a8d540543b18d494e7b` |
| `demos/03-sensitivity-masking/pipeline.yaml` | `84c870f9ecd4895748fadc75eeb871590f2155b16abce17d3dabee255e7b5da5` |
| `demos/03-sensitivity-masking/input.jsonl` | `5b100482ea7e7ca7a8984b91992c97b362aec62f9a604234a3ddc00d369af555` |
| `demos/03-sensitivity-masking/pipeline.yaml` | `84c870f9ecd4895748fadc75eeb871590f2155b16abce17d3dabee255e7b5da5` |
| `demos/03-sensitivity-masking/input.jsonl` | `5b100482ea7e7ca7a8984b91992c97b362aec62f9a604234a3ddc00d369af555` |
| `demos/04-sensor-triage/pipeline.yaml` | `fad857843fdabc51bd0344b8048a1dbaaaf492feac89d5f2168522a27e4701bc` |
| `demos/04-sensor-triage/input.jsonl` | `604de9d43f0a88d4a972a4ae6e63de6ee3495ea882ca1dee9a8d70bbb6b2f2af` |
| `demos/04-sensor-triage/pipeline.yaml` | `fad857843fdabc51bd0344b8048a1dbaaaf492feac89d5f2168522a27e4701bc` |
| `demos/04-sensor-triage/input.jsonl` | `604de9d43f0a88d4a972a4ae6e63de6ee3495ea882ca1dee9a8d70bbb6b2f2af` |
| `demos/05-agent-guardrail/pipeline.yaml` | `fb93b2539188d08d09011a9cf740d7e53229d65d6a9b3f38580d5e51cf980096` |
| `demos/05-agent-guardrail/input.jsonl` | `df9bfea14e7f837813075e071cb2d119c8388e9e63097b737f8d4409476efd79` |
| `demos/05-agent-guardrail/pipeline.yaml` | `fb93b2539188d08d09011a9cf740d7e53229d65d6a9b3f38580d5e51cf980096` |
| `demos/05-agent-guardrail/input.jsonl` | `df9bfea14e7f837813075e071cb2d119c8388e9e63097b737f8d4409476efd79` |
| `demos/06-smart-sampling/pipeline.yaml` | `e98644ed25aef1b5290345b3bcbba4aa8acb17e8d9796746aa2f8584cae0bdfe` |
| `demos/06-smart-sampling/input.jsonl` | `4d34a2b82fbe61597f4db2a89fa25041855665d529df9957fea1db707712fce2` |
| `demos/06-smart-sampling/pipeline.yaml` | `e98644ed25aef1b5290345b3bcbba4aa8acb17e8d9796746aa2f8584cae0bdfe` |
| `demos/06-smart-sampling/input.jsonl` | `4d34a2b82fbe61597f4db2a89fa25041855665d529df9957fea1db707712fce2` |
| `demos/07-soc-prefilter/pipeline.yaml` | `5da1f0225c3dd882e01b9fa2dc57d9cb9e97067e5f0c959f76f1853b4d07047b` |
| `demos/07-soc-prefilter/input.jsonl` | `3a452f0d6ba10fae25eecb62727a5120542be8eb36ab9d4ecbdc5a12b9a99b55` |
| `demos/07-soc-prefilter/pipeline.yaml` | `5da1f0225c3dd882e01b9fa2dc57d9cb9e97067e5f0c959f76f1853b4d07047b` |
| `demos/07-soc-prefilter/input.jsonl` | `3a452f0d6ba10fae25eecb62727a5120542be8eb36ab9d4ecbdc5a12b9a99b55` |
| `demos/08-data-quality/pipeline.yaml` | `4e8e6b8fedd20d9614967f6284d8ed9e1c2ad89ebde678534b398db599f19afa` |
| `demos/08-data-quality/input.jsonl` | `41811e520fb4b0904b6f0aefd78d08f4207a103dd3ebb3311dcf318d8b97a8e5` |
| `demos/08-data-quality/pipeline.yaml` | `4e8e6b8fedd20d9614967f6284d8ed9e1c2ad89ebde678534b398db599f19afa` |
| `demos/08-data-quality/input.jsonl` | `41811e520fb4b0904b6f0aefd78d08f4207a103dd3ebb3311dcf318d8b97a8e5` |
| `demos/09-moderation/pipeline.yaml` | `d4c1da215d07489d0e261a60e4e066dc8ecc925bd58e8abc20deffd4769f6e57` |
| `demos/09-moderation/input.jsonl` | `3132e125d8afcf6db845e2d84d58629b68f05452c6b82ce966aec0f4d206b8e8` |
| `demos/09-moderation/pipeline.yaml` | `d4c1da215d07489d0e261a60e4e066dc8ecc925bd58e8abc20deffd4769f6e57` |
| `demos/09-moderation/input.jsonl` | `3132e125d8afcf6db845e2d84d58629b68f05452c6b82ce966aec0f4d206b8e8` |
| `demos/10-feedback-miner/pipeline.yaml` | `69e65158b39d9bcc6912035fb6052a235789c5c97389154e6078a755f1ea8dbb` |
| `demos/10-feedback-miner/input.jsonl` | `b39f04f7d5a5dfb46637f1a164db33b8364548f5f7a8749bd2f2c7f149013e46` |
| `demos/10-feedback-miner/pipeline.yaml` | `69e65158b39d9bcc6912035fb6052a235789c5c97389154e6078a755f1ea8dbb` |
| `demos/10-feedback-miner/input.jsonl` | `b39f04f7d5a5dfb46637f1a164db33b8364548f5f7a8749bd2f2c7f149013e46` |
| `demos/11-pod-labels/pipeline.yaml` | `d4e868c61ef010e2bb2557e3088aff04c0b9dcf9669327698210e01db3a490a1` |
| `demos/11-pod-labels/fixtures/events.jsonl` | `7b2d802aa55916d928ee2e587487a36d423d4e6084c39b82c9ee01423d64714a` |
| `demos/12-ade-schedule/pipeline.yaml` | `44d1faff8d357b6caf3fdc606ec5126932c0e0608c3509e48afb466e3f280fff` |
| `demos/12-ade-schedule/input.jsonl` | `eaff893c15fa35c393f42bca46c369379c810ccd0a6a30cb854aa1fed17a2e49` |
