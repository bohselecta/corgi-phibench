# Architecture and extension points

The trusted Python harness controls immutable `Task`, `Method` and `Budget`
definitions. `Policy.next()` selects obligation IDs; `observe(passed)` controls
promotion, splitting and memory; `stop()` returns goal/failure termination.
It never owns tools, judges or budget enforcement.

`run()` creates a new receipt directory and disposable workspace. Each stateless
provider call receives the same `agent-v2` mapping: task view, active IDs,
workspace snapshot, policy memory, public feedback, tool results and critique.
Responses contain `calls` and optionally `critique`. Supported calls:

```json
{"calls":[{"tool":"write","path":"solution.py","content":"def answer(): return 42\n"}]}
```

Read: `{"tool":"read","path":"solution.py"}`. Execute:
`{"tool":"python","code":"print('sandboxed')"}`. No shell interpolation,
Git command, task package installation or builder-supplied judge exists.
The critic may return text but cannot call tools. Its text guides later optimize
calls, never overrides the trusted oracle.

Snapshot hashes are real content addresses. Patches derive from actual adjacent
snapshots. Each event is fsynced before proceeding; provider requests are saved
before dispatch. Model/tool ceilings include attempts and critique calls. A
real-provider error after dispatch cannot silently become zero-token success.

The host oracle sends only function/argument requests to an isolated Python
bridge. It compares returned values and declared exception names to trusted
expected values. Optional `unchanged_args: true` requires a conservative
host-side preservation proof as well as unchanged runtime observations.
The refactor profile also checks that `greet` and `farewell` call a shared
normalizer without duplicate normalization operations. Hidden expected values
are not in builder context or executable mounts.

## Argument-preservation profile

Candidate Python controls its interpreter, so its mutation telemetry alone is
untrusted. `oracle-v4` independently parses the actual saved source on the host
before accepting `unchanged_args`. It accepts one undecorated function with
ordinary positional arguments and no annotations/defaults, imports, nested
functions, globals, introspection, comprehensions or arbitrary calls. Expressions,
local assignments, `for`/`if`, comparisons, indexing and `len` are supported.
`len` must retain its builtin binding; assignments are plain name assignments.
Assignments may target local names only. The sole mutation operation allowed
is `append` on a local empty list allocated once and never rebound; argument
lists and their nested values cannot be mutation targets. Other syntax fails
the preservation criterion, even if a broader implementation would be pure.

The bundled feature fixture uses this loop-and-fresh-result-list grammar. The
functional output oracle still executes actual code and compares outputs on
the host. Ordinary functional criteria do not impose this grammar and do not
claim to prove absence of side effects.
Host syntax checks accept at most 64 KiB of source and 4096 AST nodes. They use
one-pass sets/counters and one proof per function in an evaluation; structural
checks share those bounds. Host checks and candidate execution share the
evaluation's remaining wall deadline. Exceeding a syntax bound fails the check.
Every `task-view-v2` builder view includes the identical versioned evaluation
constraints and preservation grammar, regardless of hidden checks. This exposes
the requirement equally without exposing hidden criterion presence, arguments
or expected values. The task fingerprint covers that actual builder view as
well as the complete definition, so prompt/profile changes alter the protocol.

The observatory is an offline HTML file containing verified receipt data. It
uses text nodes for user content and escapes script delimiters. The matrix
includes partial/missing runs; event scrubbing reconstructs the latest context,
code snapshot, patch and trace. Context composition/curves show measured
serialized bytes, not estimated tokenizer usage. No external libraries/CDNs.

## Custom task JSON

`phibench run --task-file task.json --out run` or `demo --task-file` accepts:

```json
{
  "id":"answer-task", "kind":"feature", "goal":"Implement answer() returning 42.",
  "version":1, "partition":"discovery",
  "initial":{"solution.py":"def answer(): raise NotImplementedError\n"},
  "public":[{"id":"answer","description":"Return forty-two","function":"answer","args":[],"expected":42}],
  "hidden":[]
}
```

Keep the task file outside candidate workspaces. The task loader bounds file
size, paths, criterion counts and IDs; every expected value must be JSON
serializable. `solution.py` is the executable entry module. A task's entire
public/hidden definition enters its hash; only its public view enters prompts.
Use `phibench verify experiment --task-file task.json` for separate reevaluation.
The built-in success fixture has answers only for the three bundled tasks.
For an operator task, supply a deliberately scripted JSON response using
`--fixture-script response.json` (the same `calls` schema above), or use an
explicitly authorized real provider. Script digests enter the provider identity;
scripted output remains fixture evidence and tokens remain null. The fixture
script is not included in builder context. Do not pass genuine holdout solutions
as fixtures and later call the outcome empirical.

The API's `Task` can be used for programmatic experiment construction.

A transport can implement `identity`, `mode` and
`respond(request,max_output,timeout)`; real mode requires explicit prices,
authorization, usage reporting and reservation fields. Production applications
must not instantiate privileged adapters from untrusted model responses.
The bundled HTTP adapter records configured prices and authorization ceilings
and its no-redirects policy in its fingerprint. Both adapter and run budgets apply. A POSIX main-thread
timer covers the complete request/read/parse operation; blocked or active alarms
and worker-thread use fail closed instead of losing the total deadline.
