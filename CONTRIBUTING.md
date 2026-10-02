# Contributing

Run `python3 -m unittest discover -s tests -v` and `python3 tests/acceptance.py`.
Use the README installation path to check packaging. The runtime has no Python
dependencies; keep the trusted harness small and review any new dependency.

A new control law must implement the same `Policy.next`, `observe`, `memory`
and `stop` contract. It cannot alter tools, oracle, fixture answers or ceilings.
Version semantics and freeze experiments before trials. Include unfavorable
outcomes and a test designed to falsify the mechanism's implementation.

Use synthetic data for tests. Do not commit credentials, personal data, private
repository archives or genuine holdout answers. New public demonstration tasks
are apparatus fixtures, not research holdouts. Separate model evidence from
transport mocks and byte accounting. Live provider experiments require the
operator's explicit runtime authorization.

Changes to sandbox mounts, allowed syscalls, judge inputs, journal durability or
budgets require boundary regressions and fresh saved-artifact verification.
