# Receipt laboratory

`phibench observe EXPERIMENT --out laboratory.html` validates the frozen protocol,
receipt chains, saved snapshot roots and recorded context measurements, reconstructs
final accounting, and writes one atomic self-contained HTML file. Existing output
survives a failed export. Opening it executes no candidate code and makes no requests.
There are no external fonts, scripts, images or telemetry. Node/Playwright are development tools.

Choose an actual task × policy × seed run. All scheduled runs remain present;
absent journals show `not_run`, partial journals show retained interruption state.
The heading and matrix show final summaries. Panels show only evidence reached by
the event slider. Previous/next, keyboard-operable slider and play traverse actual
journal sequence numbers; elapsed time comes from the recorded monotonic clock.

Frontier squares have area proportional to the number of requested public obligations.
They show no universal optimal geometry or policy advantage. A square's color changes
only when its observation has been reached. Policy-verified obligations, queued
remainder sizes and consecutive failures are recorded state, distinct from the latest
evaluator's checks. Held-out results appear only after the final evaluation.

The context chart uses serialized UTF-8 bytes, not estimated tokens. The ceiling is
the frozen shared budget. Component bars plus JSON framing equal the selected request's
recorded size. No request means unknown. Fixture token counts remain null.

Saved files and patches come from the most recent snapshot reached. Version lineage
links an observed full-file write to its tool event, model call and policy step; rollback
restores the saved origin map. These are links between recorded versions, not inferred
line/token authorship, surviving-token productivity or causal test coverage. Receipt
hashes detect corruption relative to a retained root; anyone can construct a new chain.
They do not establish authenticity, rights or a signed third-party attestation.

The method studio previews the bounded scalar-v1 contract and downloads YAML.
It does not run a method or add imagined rows. The Python parser remains the execution
authority. Run `phibench validate-method method.yaml`, then start a new experiment;
existing experiments remain immutable. Compare ablations by preregistering different
explicit method fields under shared tasks, provider, ceilings and evaluator.

Retained pages: `docs/laboratory.html`, `docs/null-laboratory.html`,
`docs/regression-laboratory.html`, `docs/mechanism-laboratory.html`. Regenerate them from
the corresponding `examples/*-experiment` directories. Success, null and regression
cover the same 18 scheduled task/policy combinations. The split mechanism is a separate
one-run fixture, explicitly outside that comparison. The providers know demo answers
and can write complete solutions ahead of their frontier. These receipts test the
apparatus, not scientific model performance. Real-model comparison remains NOT RUN.

The export supports at most 4096 scheduled runs, 20000 events per run and 32 MiB
embedded data. Use CLI replay/report for larger experiments. Large source files and
matrices scroll locally without making the document wider than a phone screen.
