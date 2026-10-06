# Public bar report

- Generated: 2026-10-06T04:15:54Z
- Commit: `3dd10d84681a1e613593808239818c0c303af7ad`
- Checker: `1.1.3`
- Lane: `all`

## Result

| Criterion | Status |
|---|---|
| 1. Runs | PASS |
| 2. Platform | PASS |
| 3. Structure | PASS |
| 4. Usability | PASS |
| 5. Regressions | PASS |

## Tool versions

- `expanso-cli`: Expanso CLI version v2.1.21
- `expanso-edge`: v2.1.21
- `playwright`: 1.55.0
- `python`: 3.12.13

## Assertions

| Criterion | Assertion | Result | Detail |
|---|---|---|---|
| 1 | `manifest-schema` | PASS | public-bar.toml matches schema version 1 |
| 1 | `yaml-inventory` | PASS | classified 16 YAML files |
| 1 | `service:jev-responder` | PASS | declared fixture service is ready |
| 1 | `service:recurrence-counter` | PASS | declared fixture service is ready |
| 1 | `service:recorded-adapter` | PASS | declared fixture service is ready |
| 1 | `01-log-triage-recurrence:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `01-log-triage-recurrence:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `01-log-triage-recurrence:fixture` | PASS | local Edge replay matched 16 JSON records |
| 1 | `01-log-triage-recurrence:fixture:actual_sha256` | EVIDENCE | `a31792d3f38ac2522898b5a8151827dbe67850fe80bbc89d126b196a295232c7` |
| 1 | `01-log-triage-recurrence:fixture:expected_schema_sha256` | EVIDENCE | `4059318e66935f60b61ab85310bf0b45da847f03bbc5f63c33a6e9c89ddf526d` |
| 1 | `01-log-triage-recurrence:fixture:input_sha256` | EVIDENCE | `f7a8afd40dc7e3f26f40de9a1e71deb39486d945b7d539cac7d226f898ceafcc` |
| 1 | `01-log-triage-logging:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `01-log-triage-logging:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `01-log-triage-logging:fixture` | PASS | local Edge replay matched 16 JSON records |
| 1 | `01-log-triage-logging:fixture:actual_sha256` | EVIDENCE | `0f5ace36769773204facd011f4d54fc2e30766949845de8d86c6220c5a677eeb` |
| 1 | `01-log-triage-logging:fixture:expected_schema_sha256` | EVIDENCE | `b924ce65b03f703fbd60aec9d9b8418234af7e22e4f9e5ad05cfb65abc753d04` |
| 1 | `01-log-triage-logging:fixture:input_sha256` | EVIDENCE | `f7a8afd40dc7e3f26f40de9a1e71deb39486d945b7d539cac7d226f898ceafcc` |
| 1 | `02-ticket-router:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `02-ticket-router:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `02-ticket-router:fixture` | PASS | local Edge replay matched 6 JSON records |
| 1 | `02-ticket-router:fixture:actual_sha256` | EVIDENCE | `2325bbeb514cbddfdbf47057252edafd8ae50ca8b406fcc1d38fc13c91fd46e4` |
| 1 | `02-ticket-router:fixture:expected_schema_sha256` | EVIDENCE | `d8e1c09dc6523b4b6c04d6a71e0688510bdfbcba723524dc7aa2f747e5f1ae86` |
| 1 | `02-ticket-router:fixture:input_sha256` | EVIDENCE | `e420978e2a39aa7175bbfa047e882f563aba64029bd55a8d540543b18d494e7b` |
| 1 | `03-sensitivity-masking:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `03-sensitivity-masking:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `03-sensitivity-masking:fixture` | PASS | local Edge replay matched 5 JSON records |
| 1 | `03-sensitivity-masking:fixture:actual_sha256` | EVIDENCE | `32128e85dabb2240ccb40a5821f4e418fb5caaa24b0b73e39a8f0378d65f0617` |
| 1 | `03-sensitivity-masking:fixture:expected_schema_sha256` | EVIDENCE | `d36b874e6d5f745f669ce86071b4d570be724078a65962d5aa61407d2fe8c672` |
| 1 | `03-sensitivity-masking:fixture:input_sha256` | EVIDENCE | `5b100482ea7e7ca7a8984b91992c97b362aec62f9a604234a3ddc00d369af555` |
| 1 | `04-sensor-triage:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `04-sensor-triage:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `04-sensor-triage:fixture` | PASS | local Edge replay matched 5 JSON records |
| 1 | `04-sensor-triage:fixture:actual_sha256` | EVIDENCE | `c243d022570d2ebf084b62b503fefd61a6a2f9f6635f80a4a9f4697e4c82a2a0` |
| 1 | `04-sensor-triage:fixture:expected_schema_sha256` | EVIDENCE | `fd7cf7edcf367d6399f18ab82a64cb812566de370c5f2afd916963a455ef8387` |
| 1 | `04-sensor-triage:fixture:input_sha256` | EVIDENCE | `604de9d43f0a88d4a972a4ae6e63de6ee3495ea882ca1dee9a8d70bbb6b2f2af` |
| 1 | `05-agent-guardrail:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `05-agent-guardrail:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `05-agent-guardrail:fixture` | PASS | local Edge replay matched 5 JSON records |
| 1 | `05-agent-guardrail:fixture:actual_sha256` | EVIDENCE | `a4984cc02a9f29b25434ff024fe4f37f94dbd2c3d41f9dcc745321e386203d0a` |
| 1 | `05-agent-guardrail:fixture:expected_schema_sha256` | EVIDENCE | `a1f19b87155a9d9572087786441b207cf6b1598491c6f9a93d3bc6f370af08c2` |
| 1 | `05-agent-guardrail:fixture:input_sha256` | EVIDENCE | `df9bfea14e7f837813075e071cb2d119c8388e9e63097b737f8d4409476efd79` |
| 1 | `06-smart-sampling:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `06-smart-sampling:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `06-smart-sampling:fixture` | PASS | local Edge replay matched 2 JSON records |
| 1 | `06-smart-sampling:fixture:actual_sha256` | EVIDENCE | `1decd212df3f7a91722ca1b799d42877d199164bafc38728a287637cd8503801` |
| 1 | `06-smart-sampling:fixture:expected_schema_sha256` | EVIDENCE | `b8981255c1e16c15f836bf76b6bd79aa5c7444ea96b700f94772b7bab919b966` |
| 1 | `06-smart-sampling:fixture:input_sha256` | EVIDENCE | `4d34a2b82fbe61597f4db2a89fa25041855665d529df9957fea1db707712fce2` |
| 1 | `07-soc-prefilter:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `07-soc-prefilter:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `07-soc-prefilter:fixture` | PASS | local Edge replay matched 5 JSON records |
| 1 | `07-soc-prefilter:fixture:actual_sha256` | EVIDENCE | `930aba6ab529c3e24806b5c4d756defe238b0a7dce34ffb73fbcf40c8e078bad` |
| 1 | `07-soc-prefilter:fixture:expected_schema_sha256` | EVIDENCE | `c47793d2156cc6ad8306d7a617dee7b127cf329fba42104912499eb7e1bfabda` |
| 1 | `07-soc-prefilter:fixture:input_sha256` | EVIDENCE | `3a452f0d6ba10fae25eecb62727a5120542be8eb36ab9d4ecbdc5a12b9a99b55` |
| 1 | `08-data-quality:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `08-data-quality:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `08-data-quality:fixture` | PASS | local Edge replay matched 5 JSON records |
| 1 | `08-data-quality:fixture:actual_sha256` | EVIDENCE | `9011d8b17fe5eaad2d3e239a25b2e668164a3296b6977bc75a78d377719d8069` |
| 1 | `08-data-quality:fixture:expected_schema_sha256` | EVIDENCE | `c584763772467d8bc0df6026749f2b7dd88293390dea086b58b7c5d432b81bbf` |
| 1 | `08-data-quality:fixture:input_sha256` | EVIDENCE | `41811e520fb4b0904b6f0aefd78d08f4207a103dd3ebb3311dcf318d8b97a8e5` |
| 1 | `09-moderation:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `09-moderation:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `09-moderation:fixture` | PASS | local Edge replay matched 5 JSON records |
| 1 | `09-moderation:fixture:actual_sha256` | EVIDENCE | `5adc735d3b4f0820da087272ef3b1da61aa294d4497f6d2ed64c4277ca3e7f3c` |
| 1 | `09-moderation:fixture:expected_schema_sha256` | EVIDENCE | `7df150090a88c9b56abf10dca332707cee6d63965606f4b69830f3dcef1e09b6` |
| 1 | `09-moderation:fixture:input_sha256` | EVIDENCE | `3132e125d8afcf6db845e2d84d58629b68f05452c6b82ce966aec0f4d206b8e8` |
| 1 | `10-feedback-miner:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `10-feedback-miner:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `10-feedback-miner:fixture` | PASS | local Edge replay matched 5 JSON records |
| 1 | `10-feedback-miner:fixture:actual_sha256` | EVIDENCE | `5a76f03d0d98ab1a2f2d295294066f7c627d83363836807550fe93076142c5bc` |
| 1 | `10-feedback-miner:fixture:expected_schema_sha256` | EVIDENCE | `f0a77fb97d96130b08dbb333b866b5a730b0c9a397a2a1aa927e94080e7f1e48` |
| 1 | `10-feedback-miner:fixture:input_sha256` | EVIDENCE | `b39f04f7d5a5dfb46637f1a164db33b8364548f5f7a8749bd2f2c7f149013e46` |
| 1 | `11-pod-labels:edge-validate` | PASS | expanso-edge validate passed |
| 1 | `11-pod-labels:job-validate` | PASS | expanso-cli offline job validation passed |
| 1 | `11-pod-labels:fixture` | PASS | local Edge replay matched 6 JSON records |
| 1 | `11-pod-labels:fixture:actual_sha256` | EVIDENCE | `10233a8a403d807fb1f2a1847b38ae082b0f92af2ffd45ac35e0c5405ee73e1a` |
| 1 | `11-pod-labels:fixture:expected_schema_sha256` | EVIDENCE | `724614ae64765dd6c371c43cc7633f4197c9f1db0c7c46b4a1e576fdcd5b642b` |
| 1 | `11-pod-labels:fixture:input_sha256` | EVIDENCE | `7b2d802aa55916d928ee2e587487a36d423d4e6084c39b82c9ee01423d64714a` |
| 1 | `teardown` | PASS | all declared services and browser hosts stopped |
| 2 | `platform-inventory` | PASS | declared 1 named platforms |
| 2 | `kubernetes` | PASS | other files and integration declaration passed |
| 3 | `explanation` | PASS | #explanation matched 1 element(s) |
| 3 | `explorer` | PASS | #explorer matched 1 element(s) |
| 3 | `run` | PASS | #run matched 1 element(s) |
| 3 | `deploy` | PASS | #deploy matched 1 element(s) |
| 3 | `stage:01-log-triage-logging.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-logging.shape_fingerprint` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-logging.track_recurrence` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-logging.mark_routed` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-logging.build_log_fields` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-logging.log_selection` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-logging.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.hold_wait` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.shape_fingerprint` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.track_recurrence` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.bypass_check` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.ask_jev` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.cascade` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.build_log_fields` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.log_selection` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.record_decision` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:01-log-triage-recurrence.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:02-ticket-router.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:02-ticket-router.parse_body` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:02-ticket-router.stamp_received` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:02-ticket-router.start_timer` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:02-ticket-router.ask_jev` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:02-ticket-router.route_decision` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:02-ticket-router.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:03-sensitivity-masking.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:03-sensitivity-masking.parse_body` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:03-sensitivity-masking.stamp_received` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:03-sensitivity-masking.start_timer` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:03-sensitivity-masking.ask_jev` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:03-sensitivity-masking.pick_policy` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:03-sensitivity-masking.apply_policy` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:03-sensitivity-masking.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:04-sensor-triage.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:04-sensor-triage.parse_body` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:04-sensor-triage.stamp_received` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:04-sensor-triage.start_timer` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:04-sensor-triage.ask_jev` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:04-sensor-triage.route_decision` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:04-sensor-triage.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:05-agent-guardrail.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:05-agent-guardrail.parse_body` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:05-agent-guardrail.stamp_received` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:05-agent-guardrail.start_timer` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:05-agent-guardrail.ask_jev` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:05-agent-guardrail.route_decision` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:05-agent-guardrail.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:06-smart-sampling.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:06-smart-sampling.parse_body` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:06-smart-sampling.stamp_received` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:06-smart-sampling.start_timer` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:06-smart-sampling.ask_jev` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:06-smart-sampling.score_event` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:06-smart-sampling.sample_noise` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:06-smart-sampling.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:07-soc-prefilter.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:07-soc-prefilter.parse_body` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:07-soc-prefilter.stamp_received` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:07-soc-prefilter.start_timer` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:07-soc-prefilter.ask_jev` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:07-soc-prefilter.route_decision` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:07-soc-prefilter.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:08-data-quality.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:08-data-quality.parse_body` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:08-data-quality.stamp_received` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:08-data-quality.start_timer` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:08-data-quality.ask_jev` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:08-data-quality.route_decision` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:08-data-quality.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:09-moderation.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:09-moderation.parse_body` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:09-moderation.stamp_received` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:09-moderation.start_timer` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:09-moderation.ask_jev` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:09-moderation.route_decision` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:09-moderation.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:10-feedback-miner.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:10-feedback-miner.parse_body` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:10-feedback-miner.stamp_received` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:10-feedback-miner.start_timer` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:10-feedback-miner.ask_jev` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:10-feedback-miner.route_decision` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:10-feedback-miner.route` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:11-pod-labels.input` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:11-pod-labels.candidates` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:11-pod-labels.split_candidates` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:11-pod-labels.pick_id` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:11-pod-labels.judge` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:11-pod-labels.apply` | PASS | fixture-backed explorer stage exists |
| 3 | `stage:11-pod-labels.route` | PASS | fixture-backed explorer stage exists |
| 4 | `browser-contract` | PASS | rendered-browser declarations are complete |
| 4 | `source-policy` | PASS | source avoids banned public-demo decoration |
| 5 | `feature-manifest` | PASS | public-features.json matches schema version 1 |
| 5 | `baseline` | PASS | initial adoption: no prior retained-feature baseline exists |
| 4 | `service:jev-responder` | PASS | declared fixture service is ready |
| 4 | `service:recurrence-counter` | PASS | declared fixture service is ready |
| 4 | `service:recorded-adapter` | PASS | declared fixture service is ready |
| 4 | `theme-default:320` | PASS | default theme reports light |
| 4 | `overflow:320:light` | PASS | scrollWidth 320 <= clientWidth 320 |
| 4 | `contrast:320:light` | PASS | all visible text meets WCAG AA |
| 4 | `axe:320:light` | PASS | axe found no WCAG A/AA violations |
| 4 | `theme-dark:320` | PASS | toggle reports dark |
| 4 | `overflow:320:dark` | PASS | scrollWidth 320 <= clientWidth 320 |
| 4 | `contrast:320:dark` | PASS | all visible text meets WCAG AA |
| 4 | `axe:320:dark` | PASS | axe found no WCAG A/AA violations |
| 4 | `theme-default:400` | PASS | default theme reports light |
| 4 | `overflow:400:light` | PASS | scrollWidth 400 <= clientWidth 400 |
| 4 | `contrast:400:light` | PASS | all visible text meets WCAG AA |
| 4 | `axe:400:light` | PASS | axe found no WCAG A/AA violations |
| 4 | `theme-dark:400` | PASS | toggle reports dark |
| 4 | `overflow:400:dark` | PASS | scrollWidth 400 <= clientWidth 400 |
| 4 | `contrast:400:dark` | PASS | all visible text meets WCAG AA |
| 4 | `axe:400:dark` | PASS | axe found no WCAG A/AA violations |
| 4 | `theme-default:768` | PASS | default theme reports light |
| 4 | `overflow:768:light` | PASS | scrollWidth 768 <= clientWidth 768 |
| 4 | `contrast:768:light` | PASS | all visible text meets WCAG AA |
| 4 | `axe:768:light` | PASS | axe found no WCAG A/AA violations |
| 4 | `theme-dark:768` | PASS | toggle reports dark |
| 4 | `overflow:768:dark` | PASS | scrollWidth 768 <= clientWidth 768 |
| 4 | `contrast:768:dark` | PASS | all visible text meets WCAG AA |
| 4 | `axe:768:dark` | PASS | axe found no WCAG A/AA violations |
| 4 | `theme-default:1440` | PASS | default theme reports light |
| 4 | `overflow:1440:light` | PASS | scrollWidth 1440 <= clientWidth 1440 |
| 4 | `contrast:1440:light` | PASS | all visible text meets WCAG AA |
| 4 | `axe:1440:light` | PASS | axe found no WCAG A/AA violations |
| 4 | `theme-dark:1440` | PASS | toggle reports dark |
| 4 | `overflow:1440:dark` | PASS | scrollWidth 1440 <= clientWidth 1440 |
| 4 | `contrast:1440:dark` | PASS | all visible text meets WCAG AA |
| 4 | `axe:1440:dark` | PASS | axe found no WCAG A/AA violations |
| 4 | `stage-keys` | PASS | Right and Left paged 90 stages; scroll stayed within 2px |
| 4 | `json:#stage-input:0` | PASS | JSON is valid and vertically pretty-printed |
| 4 | `json:#stage-output:0` | PASS | JSON is valid and vertically pretty-printed |
| 4 | `control:copy-stage-input` | PASS | copy invoked=True, local success=True, forced failure=True |
| 4 | `control:download-pipeline` | PASS | download completed=True, local success=True, forced failure=True |
| 4 | `teardown` | PASS | all declared services and browser hosts stopped |
