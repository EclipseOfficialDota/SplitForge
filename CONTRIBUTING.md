# Contributing

[Home](README.md) · [Architecture](docs/ARCHITECTURE.md) · [Security](SECURITY.md)

The project currently contains the Part 1 backend. Documentation fixes, parser
corrections, focused reliability work and real Linux integration evidence are
useful contributions. Keep current functionality distinct from planned UI/CLI
work; do not add release, benchmark or safety claims without corresponding data.

## Local workflow

```sh
git clone https://github.com/EclipseOfficialDota/SplitForge.git
cd SplitForge
python3 -m unittest discover -s tests -v
```

The current non-privileged checks use stdlib unittest. Network-command tests use
mocks and the state persistence test is POSIX-only. Importing `Runner` requires
Linux's `pwd` module; do not make actual root/network changes as a side effect of
test discovery or module import.

Use a small focused change and include the reason, observed behavior and relevant
verification in your pull request. Preserve literal argument handling, validation,
root/non-root boundaries, atomic state updates and narrowly owned resources.
Avoid adding dependencies for work covered by the standard library.

## Linux integration evidence

Use a disposable VM/VPS and report:

- Source revision; distribution, Python, systemd and kernel versions.
- Exact protocol core versions and CPU architecture.
- Namespaces/interfaces/routes/rules created and removed for the selected ID.
- Actual egress/DNS results and IPv6 behavior from a managed application.
- Host main-route comparison and observed SSH behavior.
- Tunnel/core/DNS failure behavior, restart/reassignment and rollback results.
- Reboot results and whether stable Python/credential paths remained available.

Sanitize outputs and never attach real private keys, passwords, subscription URIs
or a full state file. See [SECURITY.md](SECURITY.md) before reporting a vulnerability.
There is no current automated integration pipeline; describe exactly what you
ran rather than implying that a unit-test result covers kernel behavior.

## Documentation changes

Check local relative links and heading anchors. Use fenced `sh`/`python` blocks,
explicit Linux paths and real existing API names. Mark sample server domains and
credentials as values to replace. Never present planned `splitforge` CLI commands,
a nonexistent installer or a conceptual UI drawing as already working.

Keep the Persian overview consistent with the English guide, especially for
privileges, restart semantics, current limits and pending Linux validation.
Documentation examples should parse, but syntax validation alone must not be
described as a successful network test.

## Licensing

Submit only material you are entitled to contribute. Contributions to this
repository are made under its [MIT License](LICENSE); third-party protocol cores
remain separate upstream projects with their own terms.
