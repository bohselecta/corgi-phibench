# Method-definition language · scalar-v1

MDL is a bounded subset of YAML 1.2: a flat mapping with one `key: value` per
line. Blank lines and whole-line comments beginning in column zero are accepted. Values are lowercase
identifiers, nonnegative decimal integers, `true` or `false`. No quoting, tags,
aliases, anchors, nesting, multiline values, expressions or commands are allowed.
Maximum size is 16 KiB. Duplicate and unknown keys are errors, never overrides.
This deliberately replaces the source prototype's wider ambiguous grammar.

| Key | Allowed | Default |
|---|---|---|
| name | lowercase identifier, <=48 chars | required |
| version | 1 | 1 |
| growth | fibonacci / fixed / exponential / all | fixed |
| step_size | integer 1–64 | 5 |
| rollback | boolean | true |
| failure | retry / fibonacci / halve | retry |
| memory | two / full / fresh | full |
| max_failures | integer 1–32 | 5 |
| critique | boolean | false |

`name` never determines semantics: all fields are honored by the same stateful
policy implementation. `growth: all` still has the shared execution ceiling.
Failure splitting queues the remaining frontier. Success requires every prior
verified and currently active public obligation; a regression blocks promotion.

Validate `examples/bounded-method.yaml` with `phibench validate-method`, then
execute it with `phibench demo --method-file … --out …`. The complete definition
and semantic version enter the frozen manifest and run fingerprints.
