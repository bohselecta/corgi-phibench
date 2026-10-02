# Research protocol · experiment-v1

Hypothesis: bounded speculative frontiers, green preservation, failure splitting
and bounded memory may improve verified software per unit inference. Fibonacci
is one candidate control law. Equal or worse matched completion/efficiency than
fixed-step, fresh-context, eval-opt, unrestricted or exponential weakens the
hypothesis. No runtime evidence in this release tests that hypothesis.

Primary proposed metrics: final completion fraction (including every failed
arm) and verified checks per million **provider-reported** tokens. Preserve
unknown metrics and failures separately from zero. Context bytes are not tokens;
scripted fixture output is not inference. A run that never reached final
judgment has unknown coverage; no interpolation is performed. A failed run can
retain a correct artifact after rollback; report both statuses.

Before execution `experiment.json` freezes task hashes, semantic versions,
partitions, seed list, all methods, exact provider/model/temperature, tools,
evaluator, environment and equal ceilings. Its SHA-256 goes into every run.
The provider fingerprint includes configured token prices and authorization
ceilings. Task hashes include the actual versioned builder view and the same
explicit evaluation constraints for every builder, without disclosing hidden
criterion presence or answers. Changing prompts/profiles changes the protocol.
Provider price/authorization changes also change the protocol. Attempt accounting counts
durable requests, including tool attempts interrupted before a result exists.
Reports reject mismatched fingerprints and retain every scheduled arm, even
when interrupted before most runs start. This is local preregistration, not a
third-party timestamp attestation. Record an external timestamp for real studies.

Use discovery only for mechanism development; calibration to set common
budgets; lock holdout tasks and configuration before final evaluation. The
fixture suite is `demonstration` and is deliberately open. None of the source
repository's frozen partitions or hidden tests was inspected or exported as
new task answers. Operator-supplied tasks preserve partition labels; the harness
does not claim to prevent an operator from intentionally selecting tasks twice.

Within a run public feedback is available to the builder. Hidden expected
values live only in the trusted runner. Hidden tests run once at termination;
no subsequent provider call can consume that feedback. Separate experiments
for retries must remain reported alongside the original. Never rerun only the
failed arms until a desirable comparison appears.

Real trials require explicit runtime authorization and budget. Reserve costs
before each request, keep prices and usage sources explicit, report missing
accounting as unknown, and distinguish local models from paid inference. Mock
HTTP transport tests are fixtures. Do not infer productive-token ratios,
internal reasoning or causal mechanism from unobserved data. Do not claim
statistical significance from these apparatus demos. Matched fixture success
can establish apparatus behavior only.
