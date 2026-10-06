# Fixture run, 2026-10-05

Every shipped pipeline was deployed unmodified to a local `expanso-edge run --local` agent and fed its shipped input one record at a time. Jev answers were replayed from each example's recorded file; nothing called a model, and the agent had no Expanso Cloud credentials. What each pipeline wrote was compared with the committed expected output (`received_at`-style fields removed from both sides).

- Date: 2026-10-05
- Agent: v2.1.21
- Command: `uv run -s tools/fixture-runner.py run`
- Result: **9 of 9 pipelines passed**

| Pipeline | Inputs | Jev calls | Queues written | Seconds | Result |
|---|---|---|---|---|---|
| `demos/02-ticket-router/pipeline.yaml` | 6 | 6 | page 1, priority 1, routed-billing 1, routed-sales 1, routed-technical 2 | 2.2 | pass |
| `demos/03-sensitivity-masking/pipeline.yaml` | 5 | 5 | forwarded 3, quarantine 2 | 2.2 | pass |
| `demos/04-sensor-triage/pipeline.yaml` | 5 | 5 | dispatch 1, flagged 1, rollup 3 | 2.2 | pass |
| `demos/05-agent-guardrail/pipeline.yaml` | 5 | 5 | allowed 2, blocked 3 | 2.2 | pass |
| `demos/06-smart-sampling/pipeline.yaml` | 8 | 8 | kept 2 | 2.2 | pass |
| `demos/07-soc-prefilter/pipeline.yaml` | 5 | 5 | cold 2, siem 1, warm 2 | 2.2 | pass |
| `demos/08-data-quality/pipeline.yaml` | 5 | 5 | quarantine 3, warehouse 2 | 2.2 | pass |
| `demos/09-moderation/pipeline.yaml` | 5 | 5 | allowed 2, review 3 | 2.2 | pass |
| `demos/10-feedback-miner/pipeline.yaml` | 5 | 5 | alert 1, analytics 3, eng 1 | 2.0 | pass |

## Files exercised

| File | sha256 |
|---|---|
| `demos/02-ticket-router/pipeline.yaml` | `ee470b600d39b7cbb96cb6b051062af4eab17fc6add2a4868fe9b75fe19ef823` |
| `demos/02-ticket-router/input.jsonl` | `e420978e2a39aa7175bbfa047e882f563aba64029bd55a8d540543b18d494e7b` |
| `demos/03-sensitivity-masking/pipeline.yaml` | `fcdda4dbe7241f8920eff0d85fb7e6f1bb6ecfde5debffd156abe5830b6c2265` |
| `demos/03-sensitivity-masking/input.jsonl` | `5b100482ea7e7ca7a8984b91992c97b362aec62f9a604234a3ddc00d369af555` |
| `demos/04-sensor-triage/pipeline.yaml` | `3fefecc06875b85bf04f72f237d7aede4f633bc3f2e15bc1fcb525adf60adb6d` |
| `demos/04-sensor-triage/input.jsonl` | `604de9d43f0a88d4a972a4ae6e63de6ee3495ea882ca1dee9a8d70bbb6b2f2af` |
| `demos/05-agent-guardrail/pipeline.yaml` | `12f02037ab971575ad5d530e916d6338c97701b75b2ffce9523a26449e1f3a9e` |
| `demos/05-agent-guardrail/input.jsonl` | `df9bfea14e7f837813075e071cb2d119c8388e9e63097b737f8d4409476efd79` |
| `demos/06-smart-sampling/pipeline.yaml` | `a6772ece322d7509e189eac9b7c2c89f604d548fa1db9ddc3091b4e75ef6d4ff` |
| `demos/06-smart-sampling/input.jsonl` | `4d34a2b82fbe61597f4db2a89fa25041855665d529df9957fea1db707712fce2` |
| `demos/07-soc-prefilter/pipeline.yaml` | `c96bd9167fd7e5b15dcdfaf3a62ccb245b487528ba332e706490644039634d36` |
| `demos/07-soc-prefilter/input.jsonl` | `3a452f0d6ba10fae25eecb62727a5120542be8eb36ab9d4ecbdc5a12b9a99b55` |
| `demos/08-data-quality/pipeline.yaml` | `e3bc74796be671dcaef43a3e85989b981c2571ade2f2de486cc63594e22e6d90` |
| `demos/08-data-quality/input.jsonl` | `41811e520fb4b0904b6f0aefd78d08f4207a103dd3ebb3311dcf318d8b97a8e5` |
| `demos/09-moderation/pipeline.yaml` | `ee77d5dd8fcc3789ac8b9b894b68c86489c8eab30f96a45b09d9ce77bf2162e8` |
| `demos/09-moderation/input.jsonl` | `3132e125d8afcf6db845e2d84d58629b68f05452c6b82ce966aec0f4d206b8e8` |
| `demos/10-feedback-miner/pipeline.yaml` | `15c2cdfeb38891daaab304add17afc7d8cbde0e60a67aea36a1d436b4269c44a` |
| `demos/10-feedback-miner/input.jsonl` | `b39f04f7d5a5dfb46637f1a164db33b8364548f5f7a8749bd2f2c7f149013e46` |
