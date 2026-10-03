# Verification scope

Factory-v2 candidate platform: Linux x86_64, harness Python 3.12.14,
Bubblewrap 0.12.0 and Chromium. The Python execution/security kernel and six
versioned policies are preserved. Node/Playwright are development-only browser
test tools; the public runtime has no Python package dependencies.

57 unit tests cover the existing security, evaluator, provider, policy and recovery
boundaries plus laboratory hash/protocol validation, status reconstruction,
context-byte checks, atomic export preservation, missing/hostile evidence,
duplicate schedules and rollback origin restoration. `tests/acceptance.py` is a
separately framed process test: 18 actual isolated executions, independent final
score reconstruction, repeatable replay/export and real SIGTERM/SIGKILL recovery
while model/tool operations are in flight. Automated review is not a claim of
independent scientific replication or human acceptance.

`npm test` checks the 54 retained success/regression/null outcomes against Python
report data, every run's final snapshot, replay boundaries without future checks,
actual request/component byte totals, rollback content, 20 method-grammar parity
cases against Python, a downloaded/revalidated method, keyboard and play controls,
unknown/hostile evidence, metric parity and an explicitly synthetic known-token
UI input (not provider evidence), zero external requests/errors and 390×844 layout.
The separately retained split mechanism records a failed two-obligation frontier,
queued remainder [1], rollback and eventual 7/7 completion. It is not mixed into
the matched 18-run comparison. Desktop and phone screenshots show retained success
fixtures; the original null screenshots and receipts remain unchanged.

The kernel suite attempts path traversal, symlinks, special files, read-only writes,
host/judge/environment disclosure, network/fork/thread/memory/output/scratch abuse,
provider/run budget conflicts, price reconstruction, total HTTP deadlines,
argument-preservation spoofing, interruption and torn-tail recovery. Unsupported
syntax fails a conservative argument-preservation grammar. Missing isolation fails
closed without host fallback. Linux tools and actual namespace/seccomp capability
are probed by `doctor`; host security settings are never changed.

Packaging builds twice with the same Python/setuptools/zlib toolchain and fixed
packaging epoch, compares SHA256SUMS, inspects archive paths/content and exact runtime
bytes, then installs the wheel with `--no-index` in a fresh venv outside the checkout.
The installed README doctor/demo/verify/observe path exercises bundled HTML/CSS/JS.
`release_gate.py` checks retained experiment accounting and documentation links.
Build reproducibility across different toolchains is not claimed.

CI retains the checksum-pinned Bubblewrap 0.12.0 build on Ubuntu 22.04 and adds
Python 3.12/3.14 to the existing 3.11/3.13 matrix, packaging/repeat-build/offline
installation and a separate Chromium job. Earlier unsuccessful hosted sandbox
probes remain history. Current candidate hosted outcomes are recorded by the
campaign after observation; local test success is not a hosted CI claim.

Live provider interoperability and scientific policy comparisons: NOT RUN.
Paid budget: $0. ARM64 and macOS/Windows execution: NOT VERIFIED. Hash chains
are not signatures or proof of authorship. Existing history includes unverified
unfavorable source claims. Public tag/Release/artifacts remain a subsequent approved
publication step, not implied by the presence of local `dist/` files.
