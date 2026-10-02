# Execution and data boundaries

Persistent builder edits use relative UTF-8 file tools: no traversal, absolute
paths, symlinks, `.git`, special files or files >1 MiB; total workspace <=4 MiB,
128 files and depth <=16. File tools execute sequentially in a private disposable
workspace. Candidate execution cannot race them: its workspace mount is read-only,
child creation is denied, and the sandbox process has exited before tool edits.

Linux Bubblewrap unshares mount, user, PID, network and other supported
namespaces. It maps a non-root UID, clears the environment, drops capabilities,
mounts trusted distribution runtimes read-only and creates fresh `/proc` and
minimal `/dev`. No host workspace, judge file, expected value, repository Git
metadata or credential environment is mounted. Scratch `/tmp` is an 8 MiB tmpfs.
A seccomp filter verifies the syscall ABI and denies fork, vfork, clone and
clone3. Each invocation has one candidate process; subprocesses and threads
are unavailable. `prlimit` enforces 256 MiB address space, three CPU seconds,
64 descriptors, 1 MiB per-file writes and zero core dump. Parent-enforced wall
and output bounds terminate the sandbox. There is no unsafe execution fallback.

These are process boundaries, not a VM. Trust the host kernel, Python, Bubblewrap
and mounted distribution files. Kernel exploits and side channels are outside
this profile. ARM64 has an untested filter; only x86_64 was accepted locally.
Never mount operator secrets or genuine hidden answers into candidate code.

The host oracle supplies function arguments, invokes candidate code in a fresh
sandbox, then compares output with expected values in the trusted runner.
Candidate code necessarily sees test arguments. It cannot edit trusted scoring
or read expected values. Public checks provide development feedback; the hidden
set is evaluated once at termination with no subsequent model request. This is
a functional oracle, not a claim that benchmark gaming is impossible. The demo
provider is scripted with known answers and has no scientific holdout standing.
For argument preservation, candidate-reported before/after observations are
supplementary. Acceptance requires the host-side restricted syntax proof
documented in [architecture](docs/ARCHITECTURE.md#argument-preservation-profile);
unsupported syntax fails the criterion. Python frame/serializer manipulation
cannot authorize that proof.

Journal hash chains detect corruption or edits without recomputing subsequent
hashes; they do not establish authorship or resist a fully rewritten receipt.
Run `verify` to recompute final scores from retained code. Treat private task
receipts as private: code, prompts, outputs and snapshots can contain your data.
The campaign's distributed examples contain new synthetic tasks only.

Real-provider credentials are read only when an authorized request is made.
Avoid credentials in endpoint paths; URL userinfo/query/fragment are rejected.
Raw transport errors are suppressed because they can contain sensitive headers.
HTTP redirects are rejected with a local per-request policy, so credentials
cannot be forwarded to another endpoint and the recorded endpoint remains exact.
Provider token usage must be reported; missing accounting stops a run with
unknown usage. Configured token prices produce an estimate, not billing proof.
Strict provider ceilings use conservative reservations; a server that ignores
its output limit or bills differently cannot be made spend-proof by this client.
No provider request was authorized or executed for this release verification.
The total request deadline requires an unblocked POSIX main-thread alarm with
no existing timer. The adapter refuses other contexts. Prices and the smaller
of provider/run authorizations are retained for receipt audit.

For a vulnerability, privately contact the maintainers through the publisher's
[website](https://corgi-verse.com). Share a synthetic reproduction, affected
version and platform. Do not put secrets or a private exploit in a public issue.
