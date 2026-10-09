# Fixture run, 2026-10-09

Every shipped pipeline was deployed unmodified to a local `expanso-edge run --local` agent and fed its shipped input one record at a time. Jev answers were replayed from each example's recorded file; nothing called a model, and the agent had no Expanso Cloud credentials. What each pipeline wrote was compared with the committed expected output (`received_at`-style fields removed from both sides).

- Date: 2026-10-09
- Agent: v2.1.22
- Command: `uv run -s tools/fixture-runner.py run`
- Result: **22 of 22 cases passed** across 12 pipelines

| Case | Pipeline | Inputs | Jev calls | Queues written | File-in replay | Seconds | Result |
|---|---|---|---|---|---|---|---|
| 01-log-triage:logging | `demos/01-log-triage/pipeline-logging.yaml` | 16 | 0 | logs 16 | 16 records | 5.0 | pass |
| 01-log-triage:recurrence | `demos/01-log-triage/pipeline-recurrence.yaml` | 16 | 11 | archive 5, notify 2, page 1, review 8 | 16 records | 10.1 | pass |
| 01-log-triage:outage | `demos/01-log-triage/pipeline-recurrence.yaml` | 3 | 64 | archive 2, held 1, review 1 | not run | 100.4 | pass |
| 02-ticket-router:main | `demos/02-ticket-router/pipeline.yaml` | 6 | 6 | page 1, priority 1, routed-billing 1, routed-sales 1, routed-technical 2 | 6 records | 4.9 | pass |
| 02-ticket-router:jev_down | `demos/02-ticket-router/pipeline.yaml` | 6 | 12 | triage 6 | not run | 8.0 | pass |
| 03-sensitivity-masking:main | `demos/03-sensitivity-masking/pipeline.yaml` | 5 | 5 | forwarded 3, quarantine 2 | 5 records | 4.7 | pass |
| 03-sensitivity-masking:jev_down | `demos/03-sensitivity-masking/pipeline.yaml` | 5 | 10 | quarantine 5 | not run | 7.1 | pass |
| 04-sensor-triage:main | `demos/04-sensor-triage/pipeline.yaml` | 5 | 5 | dispatch 1, flagged 1, rollup 3 | 5 records | 5.0 | pass |
| 04-sensor-triage:jev_down | `demos/04-sensor-triage/pipeline.yaml` | 5 | 10 | flagged 5 | not run | 7.0 | pass |
| 05-agent-guardrail:main | `demos/05-agent-guardrail/pipeline.yaml` | 5 | 5 | allowed 2, blocked 3 | 5 records | 4.9 | pass |
| 05-agent-guardrail:jev_down | `demos/05-agent-guardrail/pipeline.yaml` | 5 | 10 | blocked 5 | not run | 6.9 | pass |
| 06-smart-sampling:main | `demos/06-smart-sampling/pipeline.yaml` | 8 | 8 | kept 2 | 2 records | 4.7 | pass |
| 06-smart-sampling:jev_down | `demos/06-smart-sampling/pipeline.yaml` | 8 | 16 | kept 8 | not run | 10.0 | pass |
| 07-soc-prefilter:main | `demos/07-soc-prefilter/pipeline.yaml` | 5 | 5 | cold 2, siem 1, warm 2 | 5 records | 5.0 | pass |
| 07-soc-prefilter:jev_down | `demos/07-soc-prefilter/pipeline.yaml` | 5 | 10 | warm 5 | not run | 6.9 | pass |
| 08-data-quality:main | `demos/08-data-quality/pipeline.yaml` | 5 | 5 | quarantine 3, warehouse 2 | 5 records | 4.9 | pass |
| 08-data-quality:jev_down | `demos/08-data-quality/pipeline.yaml` | 5 | 10 | quarantine 5 | not run | 7.1 | pass |
| 09-moderation:main | `demos/09-moderation/pipeline.yaml` | 5 | 5 | allowed 2, review 3 | 5 records | 4.8 | pass |
| 09-moderation:jev_down | `demos/09-moderation/pipeline.yaml` | 5 | 10 | review 5 | not run | 7.1 | pass |
| 10-feedback-miner:main | `demos/10-feedback-miner/pipeline.yaml` | 5 | 5 | alert 1, analytics 3, eng 1 | 5 records | 4.9 | pass |
| 10-feedback-miner:jev_down | `demos/10-feedback-miner/pipeline.yaml` | 5 | 10 | analytics 5 | not run | 7.1 | pass |
| 11-pod-labels | `demos/11-pod-labels/pipeline.yaml` | 6 | 6 | events 33, labels 7, receipts 6 | 6 records | 55.9 | pass |

## Files exercised

| File | sha256 |
|---|---|
| `demos/01-log-triage/pipeline-logging.yaml` | `85b049ac6e36182692d110719110a673e829cfc0edc3857056c7f8cfb1200046` |
| `demos/01-log-triage/input.jsonl` | `f7a8afd40dc7e3f26f40de9a1e71deb39486d945b7d539cac7d226f898ceafcc` |
| `demos/01-log-triage/pipeline-recurrence.yaml` | `e7a74a6bddb4fb5a43eab2585d9aae48ddd0c180d150ebb5445008280c6bdc8b` |
| `demos/01-log-triage/input.jsonl` | `f7a8afd40dc7e3f26f40de9a1e71deb39486d945b7d539cac7d226f898ceafcc` |
| `demos/01-log-triage/pipeline-recurrence.yaml` | `e7a74a6bddb4fb5a43eab2585d9aae48ddd0c180d150ebb5445008280c6bdc8b` |
| `demos/01-log-triage/input-outage.jsonl` | `a51bf3310cf8513fa027ae1f92b12f389d7b0faad0abafaaef411a3c9d0c66db` |
| `demos/02-ticket-router/pipeline.yaml` | `bb8a26167618f9220c72a83b1df8f07da7cff203154a39e1bfe34f80a00cc749` |
| `demos/02-ticket-router/input.jsonl` | `e420978e2a39aa7175bbfa047e882f563aba64029bd55a8d540543b18d494e7b` |
| `demos/02-ticket-router/pipeline.yaml` | `bb8a26167618f9220c72a83b1df8f07da7cff203154a39e1bfe34f80a00cc749` |
| `demos/02-ticket-router/input.jsonl` | `e420978e2a39aa7175bbfa047e882f563aba64029bd55a8d540543b18d494e7b` |
| `demos/03-sensitivity-masking/pipeline.yaml` | `b294d5d3956dcd1250e20176b5c5b581cbd66aef8d27e45023bc571440983265` |
| `demos/03-sensitivity-masking/input.jsonl` | `5b100482ea7e7ca7a8984b91992c97b362aec62f9a604234a3ddc00d369af555` |
| `demos/03-sensitivity-masking/pipeline.yaml` | `b294d5d3956dcd1250e20176b5c5b581cbd66aef8d27e45023bc571440983265` |
| `demos/03-sensitivity-masking/input.jsonl` | `5b100482ea7e7ca7a8984b91992c97b362aec62f9a604234a3ddc00d369af555` |
| `demos/04-sensor-triage/pipeline.yaml` | `0bf21b0ad7af2cec3873118fd0af1d9a1849050c460f9c08eed3324ff802400e` |
| `demos/04-sensor-triage/input.jsonl` | `604de9d43f0a88d4a972a4ae6e63de6ee3495ea882ca1dee9a8d70bbb6b2f2af` |
| `demos/04-sensor-triage/pipeline.yaml` | `0bf21b0ad7af2cec3873118fd0af1d9a1849050c460f9c08eed3324ff802400e` |
| `demos/04-sensor-triage/input.jsonl` | `604de9d43f0a88d4a972a4ae6e63de6ee3495ea882ca1dee9a8d70bbb6b2f2af` |
| `demos/05-agent-guardrail/pipeline.yaml` | `92e49f41beb262723214af188246a6c4ded2d481abb5fe783d28211c4c77cc65` |
| `demos/05-agent-guardrail/input.jsonl` | `df9bfea14e7f837813075e071cb2d119c8388e9e63097b737f8d4409476efd79` |
| `demos/05-agent-guardrail/pipeline.yaml` | `92e49f41beb262723214af188246a6c4ded2d481abb5fe783d28211c4c77cc65` |
| `demos/05-agent-guardrail/input.jsonl` | `df9bfea14e7f837813075e071cb2d119c8388e9e63097b737f8d4409476efd79` |
| `demos/06-smart-sampling/pipeline.yaml` | `0330137321909291ab9b6afcdb3ae997197cfdd30f8e759e34ed9e9c71e4ba24` |
| `demos/06-smart-sampling/input.jsonl` | `4d34a2b82fbe61597f4db2a89fa25041855665d529df9957fea1db707712fce2` |
| `demos/06-smart-sampling/pipeline.yaml` | `0330137321909291ab9b6afcdb3ae997197cfdd30f8e759e34ed9e9c71e4ba24` |
| `demos/06-smart-sampling/input.jsonl` | `4d34a2b82fbe61597f4db2a89fa25041855665d529df9957fea1db707712fce2` |
| `demos/07-soc-prefilter/pipeline.yaml` | `6c855ca8e273400e0b644012710b39a71465a911f01f0706606565cb78053404` |
| `demos/07-soc-prefilter/input.jsonl` | `3a452f0d6ba10fae25eecb62727a5120542be8eb36ab9d4ecbdc5a12b9a99b55` |
| `demos/07-soc-prefilter/pipeline.yaml` | `6c855ca8e273400e0b644012710b39a71465a911f01f0706606565cb78053404` |
| `demos/07-soc-prefilter/input.jsonl` | `3a452f0d6ba10fae25eecb62727a5120542be8eb36ab9d4ecbdc5a12b9a99b55` |
| `demos/08-data-quality/pipeline.yaml` | `482b7525e660f0cfe225b2fc9827b43972079775aee23784e4c72eaed9f556c7` |
| `demos/08-data-quality/input.jsonl` | `41811e520fb4b0904b6f0aefd78d08f4207a103dd3ebb3311dcf318d8b97a8e5` |
| `demos/08-data-quality/pipeline.yaml` | `482b7525e660f0cfe225b2fc9827b43972079775aee23784e4c72eaed9f556c7` |
| `demos/08-data-quality/input.jsonl` | `41811e520fb4b0904b6f0aefd78d08f4207a103dd3ebb3311dcf318d8b97a8e5` |
| `demos/09-moderation/pipeline.yaml` | `9faaac09fd6cfa3bc132bb12ef7ccc50615ce8cbe6653e131971546faafcf206` |
| `demos/09-moderation/input.jsonl` | `3132e125d8afcf6db845e2d84d58629b68f05452c6b82ce966aec0f4d206b8e8` |
| `demos/09-moderation/pipeline.yaml` | `9faaac09fd6cfa3bc132bb12ef7ccc50615ce8cbe6653e131971546faafcf206` |
| `demos/09-moderation/input.jsonl` | `3132e125d8afcf6db845e2d84d58629b68f05452c6b82ce966aec0f4d206b8e8` |
| `demos/10-feedback-miner/pipeline.yaml` | `4eb6e73d06731b10c5abaf33ecf6b1fdfda282393fc3ea754c2e851fb4444960` |
| `demos/10-feedback-miner/input.jsonl` | `b39f04f7d5a5dfb46637f1a164db33b8364548f5f7a8749bd2f2c7f149013e46` |
| `demos/10-feedback-miner/pipeline.yaml` | `4eb6e73d06731b10c5abaf33ecf6b1fdfda282393fc3ea754c2e851fb4444960` |
| `demos/10-feedback-miner/input.jsonl` | `b39f04f7d5a5dfb46637f1a164db33b8364548f5f7a8749bd2f2c7f149013e46` |
| `demos/11-pod-labels/pipeline.yaml` | `d4e868c61ef010e2bb2557e3088aff04c0b9dcf9669327698210e01db3a490a1` |
| `demos/11-pod-labels/fixtures/events.jsonl` | `7b2d802aa55916d928ee2e587487a36d423d4e6084c39b82c9ee01423d64714a` |
