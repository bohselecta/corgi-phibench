# Review boundaries

Implementation review attempts to falsify the release contract, not certify a
scientific hypothesis. Builder self-review found and repaired:

- Whole-user process limits included unrelated cloud processes: child creation
  now fails at the candidate syscall boundary, independently of host counts.
- A closed stdout/stderr path escaped the short wall deadline: execution now
  waits under that deadline even after streams close.
- Fixture transports could be mislabeled as real providers: injected transports
  are explicitly fixture mode, with null model tokens and zero runtime cost.
- Refactor/feature output parity did not establish input preservation: ordinary
  mutation tests were added, then independently challenged as described below.
- Null fixture expectations incorrectly assumed zero accepted baseline checks:
  the real bug-fix baseline passes one check; that unfavorable partial result
  is retained rather than editing fixtures or scores.

Fresh-context review reproduced six defects in the initial candidate: spoofable
mutation telemetry, ignored smaller adapter authorizations, omitted interrupted
tool attempts, inactivity-only HTTP timeouts, conflicting initial paths that
left empty receipts, and prices missing from provenance. Repairs add the host
restricted syntax proof, enforce both authorization envelopes, count requests
and match results, enforce a total POSIX timer, reject conflicting paths before
run creation while retaining storage-init failures, and record/recompute priced
usage. The original failed-review disposition is retained in campaign evidence.
The first repair's syntax proof was independently found to repeat quadratic
host work. Source/node ceilings, one-pass traversal, per-evaluation proof reuse
and shared host/execution deadlines were added before publication.
The constrained grammar was then found to be absent from builder prompts.
Every task view now carries the same versioned constraints before evaluation;
hidden criterion presence and answers remain absent. Those actual prompt
constraints enter the task fingerprint and the newly frozen protocol.
An additional local stdlib check showed automatic redirects forward authorization
headers across hosts. Provider redirects are now rejected before any second
request, and that endpoint policy is recorded in the provider fingerprint.

Automated checks and black-box acceptance supplement implementation review.
They are not human scientific vetting or independent model-performance evidence.
Live-provider verification remains NOT RUN. CI checks the same apparatus only.
