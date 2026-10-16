# Contributing

[Home](README.md) · [Architecture](docs/ARCHITECTURE.md) · [Security](SECURITY.md)

The project ships a networking engine, Textual UI, Typer CLI and installer.
Focused reliability work, protocol interoperability evidence and documentation
are welcome. Do not add benchmark or safety claims without corresponding data.

## Local workflow

```sh
git clone https://github.com/EclipseOfficialDota/SplitForge.git
cd SplitForge
python3 -m venv .venv
.venv/bin/pip install -c requirements.lock -e .
.venv/bin/python -m unittest discover -s tests -v
```

The routine suite uses stdlib unittest and installed runtime dependencies.
State persistence is POSIX-only; root integration is opt-in. CLI, UI, validation
and rollback tests complement real kernel tests. Do not change root/network
state as a side effect of test discovery or module import.

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
CI runs routine checks, builds packages and runs an isolated root Linux suite.
See [Validation](docs/VALIDATION.md) for commands and recorded scope. Describe
exactly what you ran rather than equating mocks with kernel behavior.

## Documentation changes

Check local relative links and heading anchors. Use fenced `sh`/`python` blocks,
explicit Linux paths and real existing API names. Mark sample server domains and
credentials as values to replace. Keep examples aligned with actual CLI help.
Demo screenshots must be identified as synthetic data, not live provider results.

Keep the Persian overview consistent with the English guide, especially for
privileges, restart semantics, current limits and the Linux validation record.
Documentation examples should parse, but syntax validation alone must not be
described as a successful network test.

## Licensing

Submit only material you are entitled to contribute. Contributions to this
repository are made under its [MIT License](LICENSE); third-party protocol cores
remain separate upstream projects with their own terms.
