"""Public CLI. All workload commands are argument arrays, never shell strings."""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from splitforge import __version__
from splitforge.core.netns import require_root, run
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, StateStore

app = typer.Typer(no_args_is_help=False, help="SplitForge — per-application Linux tunnel routing.")
profiles = typer.Typer(help="Import, start, inspect and remove tunnel profiles.")
apps = typer.Typer(help="Register scripts, binaries and existing services.")
deps = typer.Typer(help="Inspect or install protocol dependencies.")
users = typer.Typer(help="Route future systemd user-manager workloads.")
web_app = typer.Typer(invoke_without_command=True, help="Set up and run the web control panel.")
backups = typer.Typer(help="Encrypted profile/settings export and recovery.")
traffic_app = typer.Typer(help='Independent application/tunnel usage and sampled traffic budgets.')
app.add_typer(profiles, name="profile")
app.add_typer(apps, name="app")
app.add_typer(deps, name="dependencies")
app.add_typer(users, name="user")
app.add_typer(web_app, name="web")
app.add_typer(backups, name="backup")
app.add_typer(traffic_app, name='traffic')
console = Console()


@traffic_app.command('enable')
def traffic_enable(ctx: typer.Context):
    from splitforge.core.traffic import ensure_service
    ensure_service(objects(ctx)[0])
    typer.echo('Persistent traffic collector enabled')


@traffic_app.command('status')
def traffic_status(ctx: typer.Context):
    require_root()
    from splitforge.core.traffic import TrafficStore
    typer.echo(json.dumps(TrafficStore(objects(ctx)[0]).snapshot(), indent=2))


@traffic_app.command('quota')
def traffic_quota(ctx: typer.Context, target: str,
                  kind: str = typer.Option('app', '--kind', help='app or profile'),
                  mib: int | None = typer.Option(None, '--mib', min=1),
                  disable: bool = typer.Option(False, '--disable'),
                  warning: int = typer.Option(80, '--warning', min=1, max=99),
                  reset: bool = typer.Option(False, '--reset')):
    """Set/reset a manual usage period; stops at the next collector sample."""
    require_root()
    from splitforge.core.traffic import TrafficStore
    store, _, _ = objects(ctx)
    if kind not in ('app', 'profile') or (disable and mib is not None):
        raise ValueError('Choose app/profile and either --mib or --disable')
    identifier = app_by_name(store, target).id if kind == 'app' else store.profile(target).id
    group = 'apps' if kind == 'app' else 'profiles'
    traffic = TrafficStore(store)
    previous = traffic.snapshot()[group].get(identifier)
    limit = None if disable else mib * 1048576 if mib is not None else previous['quota'] if previous else None
    if mib is None and not disable and not reset:
        raise ValueError('Use --mib, --disable or --reset')
    traffic.set_quota(group, identifier, limit, warning=warning, reset=reset)
    typer.echo('Budget saved; start a previously blocked target explicitly when ready')


def backup_password(path: Path | None, *, confirm=False):
    if path is None:
        return typer.prompt('Backup password (12+ bytes)', hide_input=True, confirmation_prompt=confirm)
    import stat
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > 1025:
        raise ValueError('Password file must be owned by the current user, mode 0600, and at most 1025 bytes')
    return path.read_text().rstrip('\n')


@backups.command('export')
def backup_export(ctx: typer.Context, destination: Path,
                  password_file: Path | None = typer.Option(None, '--password-file')):
    """Export encrypted state, DNS, failover, web settings and public trust anchors."""
    require_root()
    from splitforge.core.backup import export_backup
    path = export_backup(objects(ctx)[0], destination, backup_password(password_file, confirm=True))
    typer.echo(f'Encrypted backup saved: {path}')


@backups.command('inspect')
def backup_inspect(source: Path, password_file: Path | None = typer.Option(None, '--password-file')):
    """Authenticate a backup and show its version/counts without restoring it."""
    require_root()
    from splitforge.core.backup import read_backup
    document = read_backup(source, backup_password(password_file))
    typer.echo(json.dumps({'version': document.get('version'), 'created': document.get('created'),
        'profiles': len(document['state']['profiles']), 'apps': len(document['state']['apps']),
        'web_settings': bool(document.get('web'))}, indent=2))


@backups.command('restore')
def backup_restore(ctx: typer.Context, source: Path,
                   password_file: Path | None = typer.Option(None, '--password-file'),
                   start: bool = typer.Option(False, '--start', help='Run enabled commands from this trusted backup.'),
                   web_settings: bool = typer.Option(False, '--web-settings', help='Also redeploy the saved public web address/ports.'),
                   agree_tos: bool = typer.Option(False, '--agree-tos'),
                   yes: bool = typer.Option(False, '--yes')):
    """Replace current registrations; stop workloads and retain encrypted recovery."""
    require_root()
    from splitforge.core.backup import read_backup, restore_backup
    password = backup_password(password_file)
    document = read_backup(source, password)
    if web_settings and (document.get('web') or {}).get('mode') == 'https' and not agree_tos:
        raise ValueError('HTTPS web restoration requires --agree-tos for certificate issuance')
    if not yes:
        typer.confirm(f"Replace configuration with {len(document['state']['profiles'])} profiles and "
                      f"{len(document['state']['apps'])} apps? Current workloads stop; "
                      f"saved enabled commands {'will start' if start else 'remain stopped'}.", abort=True)
    store, manager, runner = objects(ctx)
    restore_backup(store, manager, runner, document, password, start=start, report=typer.echo)
    if web_settings and document.get('web'):
        from splitforge.web.setup import WebSettings, deploy, load_settings
        current = load_settings()
        values = dict(document['web'], state=str(store.path.absolute()),
                      token_file=current.token_file if current else '/etc/splitforge/web.token')
        deploy(WebSettings(**values), agree_tos=agree_tos, report=typer.echo)


def objects(ctx: typer.Context):
    store = StateStore(ctx.find_root().obj["state"])
    manager = ProtocolManager(store)
    return store, manager, Runner(store, manager)


def app_by_name(store: StateStore, value: str) -> AppBinding:
    matches = [a for a in store.apps() if value in (a.name, a.id)]
    if len(matches) != 1:
        raise ValueError("Application not found or ambiguous; use its ID")
    return matches[0]


def print_rows(title, columns, rows):
    table = Table(title=title, header_style="bold cyan", border_style="bright_black")
    for column in columns:
        table.add_column(column)
    for row in rows:
        table.add_row(*(Text(str(value)) for value in row))
    console.print(table)


@app.callback(invoke_without_command=True)
def entry(ctx: typer.Context,
          state: Path = typer.Option(Path("/etc/splitforge/state.json"), "--state", envvar="SPLITFORGE_STATE"),
          demo: bool = typer.Option(False, "--demo", help="Open the read-only UI demo without root/network changes."),
          version: bool = typer.Option(False, "--version", is_eager=True)):
    if version:
        console.print(__version__)
        raise typer.Exit()
    ctx.obj = {"state": state}
    if ctx.invoked_subcommand is None:
        if not demo:
            require_root()
        from splitforge.tui.app import SplitForgeApp
        SplitForgeApp(state_path=state, demo=demo).run()


@profiles.command("list")
def profile_list(ctx: typer.Context, as_json: bool = typer.Option(False, "--json")):
    store, _, _ = objects(ctx)
    rows = [{"id": p.id, "name": p.name, "protocol": p.protocol, "exit_ip": p.exit_ip,
             "country": p.country} for p in store.profiles()]
    if as_json:
        typer.echo(json.dumps(rows))
    else:
        print_rows("Profiles", ["ID", "Name", "Protocol", "Last exit", "Country"],
                   [tuple(r.values()) for r in rows])


@profiles.command("import")
def profile_import(ctx: typer.Context, source: str, name: str | None = None,
                   uri_file: bool = typer.Option(False, "--uri-file", help="Read a private URI from this file."),
                   replace: str | None = typer.Option(None, "--replace", help="Replace a stopped profile without changing its assignments.")):
    require_root()
    _, manager, _ = objects(ctx)
    profile = manager.import_profile(Path(source).read_text().strip() if uri_file else source, name=name, replace_id=replace)
    typer.echo(f"{profile.id} {profile.name}")


@profiles.command("dns-tunnel")
def dns_tunnel(ctx: typer.Context, name: str, protocol: str, domain: str, resolver: str,
               public_key_file: Path | None = None, certificate: Path | None = None):
    require_root()
    _, manager, _ = objects(ctx)
    profile = manager.dns_tunnel(name, protocol, domain, resolver,
        public_key=public_key_file.read_text().strip() if public_key_file else "",
        certificate=str(certificate) if certificate else "")
    typer.echo(f"{profile.id} {profile.name}")


@profiles.command("start")
def profile_start(ctx: typer.Context, name: str):
    objects(ctx)[1].start(name)
    typer.echo("Profile started and enabled for boot")


@profiles.command("stop")
def profile_stop(ctx: typer.Context, name: str):
    objects(ctx)[1].stop(name)
    typer.echo("Profile stopped and disabled for boot")


@profiles.command("test")
def profile_test(ctx: typer.Context, name: str):
    require_root()
    typer.echo(json.dumps(objects(ctx)[1].test(name)))


@profiles.command("dns")
def profile_dns(ctx: typer.Context, name: str, url: str, bootstrap: str):
    require_root()
    store, manager, _ = objects(ctx)
    profile = store.profile(name)
    if manager.netns.exists(profile):
        raise ValueError("Stop the profile before changing DNS")
    updated = dataclasses.replace(profile, doh_url=url, doh_ip=bootstrap)
    store.save_profile(updated)
    typer.echo("DNS saved")


@profiles.command("remove")
def profile_remove(ctx: typer.Context, name: str):
    objects(ctx)[1].remove(name)
    typer.echo("Profile removed")


@profiles.command("probe")
def profile_probe(ctx: typer.Context, name: str,
                  url: str = typer.Option("https://www.cloudflare.com/cdn-cgi/trace", "--url"),
                  tls_ca_file: Path | None = typer.Option(None, "--tls-ca-file")):
    """Set a verified HTTPS trace endpoint/custom CA for private environments."""
    require_root()
    store, manager, _ = objects(ctx)
    profile = store.profile(name)
    if manager.netns.exists(profile):
        raise ValueError("Stop the profile before changing the probe")
    if tls_ca_file and not tls_ca_file.is_file():
        raise ValueError("CA bundle does not exist")
    store.save_profile(dataclasses.replace(profile, probe_url=url,
        tls_ca_file=str(tls_ca_file.resolve()) if tls_ca_file else ""))
    typer.echo("Verified HTTPS probe settings saved; custom CA also applies to this profile's DoH stub")


@apps.command("add", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def app_add(ctx: typer.Context, name: str,
            user: str = typer.Option("root", "--user"),
            cwd: str = typer.Option("/", "--cwd"),
            service: str | None = typer.Option(None, "--service")):
    require_root()
    store, _, runner = objects(ctx)
    if any(a.name == name for a in store.apps()):
        raise ValueError("Application name already exists")
    argv = list(ctx.args)
    if argv and argv[0] == "--":
        argv.pop(0)
    if argv:
        executable = shutil.which(argv[0])
        if not executable:
            raise FileNotFoundError(argv[0])
        argv[0] = executable
    binding = AppBinding(name, argv, user=user, cwd=cwd, service=service)
    runner._identity(user)
    runner._validate_service(binding)
    store.save_app(binding)
    typer.echo(f"{binding.id} {binding.name}")


@apps.command("list")
def app_list(ctx: typer.Context):
    store, _, _ = objects(ctx)
    names = {p.id: p.name for p in store.profiles()}
    print_rows("Applications", ["ID", "Name", "User", "Profile", "Enabled intent"],
               [(a.id, a.name, a.user, names.get(a.profile_id, "Direct"), a.enabled) for a in store.apps()])


@app.command("bind")
def bind(ctx: typer.Context, target: str, profile: str = typer.Option("direct", "--profile"),
         stopped: bool = typer.Option(False, "--stopped"),
         backup: str | None = typer.Option(None, "--backup", help="Automatic failover to this tunnel; never Direct.")):
    store, _, runner = objects(ctx)
    updated = runner.bind(app_by_name(store, target).id, None if profile == "direct" else profile, start=not stopped,
                backup_profile_name=backup)
    status = ('application left stopped' if stopped else 'application restarted' if runner.running(updated)
              else 'application is stopped; inspect logs; configured failover intent is retained')
    typer.echo('Assignment applied; ' + status)


@apps.command("stop")
def app_stop(ctx: typer.Context, target: str):
    store, _, runner = objects(ctx)
    runner.stop(app_by_name(store, target).id)


@apps.command("test")
def app_test(ctx: typer.Context, target: str):
    """Check IP, DNS and HTTPS in the actual running application namespaces."""
    store, _, runner = objects(ctx)
    typer.echo(json.dumps(runner.test(app_by_name(store, target).id), indent=2))


@apps.command("remove")
def app_remove(ctx: typer.Context, target: str):
    store, _, runner = objects(ctx)
    runner.remove(app_by_name(store, target).id)


@app.command("exec", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def execute(ctx: typer.Context, profile: str | None = typer.Option(None, "--profile"),
            user: str = typer.Option("root", "--user"), cwd: str | None = typer.Option(None, "--cwd"),
            proxychains: bool = typer.Option(False, "--proxychains")):
    _, _, runner = objects(ctx)
    argv = list(ctx.args)
    if argv and argv[0] == "--":
        argv.pop(0)
    if not argv:
        raise ValueError("Supply a command after --")
    if proxychains:
        if not profile or profile == "direct":
            raise ValueError("Proxychains requires a proxy profile")
        code = runner.proxychains(profile, argv, user=user)
    else:
        # Explicit Direct must not accidentally inherit a saved user mapping.
        code = runner.execute(argv, profile_name=profile, user=user, cwd=cwd)
    raise typer.Exit(code)


@users.command("bind")
def user_bind(ctx: typer.Context, user: str, profile: str):
    unit = objects(ctx)[2].bind_user(user, None if profile == "direct" else profile)
    typer.echo(f"Saved. Apply by deliberately restarting {unit}; existing user workloads may stop.")


@app.command("status")
def status(ctx: typer.Context, as_json: bool = typer.Option(False, "--json")):
    store, manager, runner = objects(ctx)
    live = sys.platform == "linux" and shutil.which("systemctl") is not None
    rows = [manager.status(p.id) if live else {"id": p.id, "name": p.name, "active": False,
            "namespace": False, "exit_ip": p.exit_ip, "latency_ms": p.latency_ms} for p in store.profiles()]
    applications = [{"id": a.id, "name": a.name, "user": a.user, "profile_id": a.profile_id,
                     "running": runner.running(a) if live else False} for a in store.apps()]
    if as_json:
        typer.echo(json.dumps({"profiles": rows, "apps": applications}))
    else:
        print_rows("Tunnel lifecycle (use profile test for fresh egress)", ["ID", "Name", "Unit", "Namespace", "Last exit"],
                   [(r["id"], r["name"], r["active"], r["namespace"], r["exit_ip"]) for r in rows])
        print_rows("Applications", ["ID", "Name", "User", "Running"],
                   [(r["id"], r["name"], r["user"], r["running"]) for r in applications])


@app.command("logs")
def logs(follow: bool = typer.Option(False, "--follow", "-f"), unit: str = typer.Option("splitforge-*", "--unit")):
    require_root()
    if not unit.startswith("splitforge-") or any(c in unit for c in "\n\r\0"):
        raise ValueError("Choose a SplitForge unit or splitforge-* pattern")
    raise typer.Exit(subprocess.call(["journalctl", "--no-pager", "-n", "100", "-u", unit, *(["-f"] if follow else [])]))


@deps.command("list")
def dependencies_list():
    tools = ["ip", "nft", "systemctl", "systemd-run", "wg", "openvpn", "xray", "tun2socks",
             "dnstt-client", "slipstream-client", "proxychains4"]
    print_rows("Dependencies", ["Binary", "Path"], [(name, shutil.which(name) or "MISSING") for name in tools])


@deps.command("install")
def dependencies_install(name: str):
    from splitforge.core.dependencies import install, progress_text
    typer.echo(install(name, progress=lambda event: typer.echo(progress_text(event))))


@app.command("doctor")
def doctor():
    linux = sys.platform == "linux"
    checks = {"linux": linux, "root": linux and os.geteuid() == 0,
              "systemd_pid1": linux and Path("/proc/1/comm").read_text().strip() == "systemd",
              "tun_device": Path("/dev/net/tun").exists(),
              **{tool: bool(shutil.which(tool)) for tool in ["ip", "nft", "systemctl", "systemd-run", "sysctl"]}}
    print_rows("Platform preflight", ["Check", "Result"], [(k, "OK" if v else "MISSING") for k, v in checks.items()])
    if not all(checks.values()):
        raise typer.Exit(1)


@app.command("update")
def update(ctx: typer.Context,
           prefix: Path | None = typer.Option(None, "--prefix", help="Managed installation directory; normally detected automatically."),
           force: bool = typer.Option(False, "--force", help="Reinstall even when the official revision is already installed.")):
    """Download and install the latest official version, backing up state and restoring workloads."""
    from splitforge.core.updater import update as update_installation
    update_installation(ctx.find_root().obj["state"], prefix=prefix, force=force, report=typer.echo)


@app.command('rollback')
def rollback(ctx: typer.Context, prefix: Path | None = typer.Option(None, '--prefix'),
             backup: str | None = typer.Option(None, '--backup'),
             list_backups: bool = typer.Option(False, '--list'), yes: bool = typer.Option(False, '--yes')):
    """Restore a private pre-update environment and its matching saved state."""
    require_root()
    from splitforge.core.updater import available_backups, installation_prefix, rollback as revert
    state = ctx.find_root().obj['state'].expanduser().absolute()
    prefix = installation_prefix(prefix)
    choices = available_backups(prefix, state)
    if list_backups:
        typer.echo(json.dumps(choices, indent=2))
        return
    selected = next((item for item in choices if backup is None or item['id'] == backup), None)
    if not selected:
        raise ValueError('No matching installation backup; use splitforge rollback --list')
    if not yes:
        typer.confirm(f"Restore installation AND saved state from {selected['id']}? Workloads restart and later configuration changes are replaced.", abort=True)
    revert(state, prefix=prefix, backup_id=selected['id'], report=typer.echo)


@web_app.callback()
def web(ctx: typer.Context,
        host: str = typer.Option("127.0.0.1", "--host", help="Loopback host; use an SSH forward for remote access."),
        port: int = typer.Option(8765, "--port", min=1, max=65535),
        token_file: Path = typer.Option(Path("/etc/splitforge/web.token"), "--token-file"),
        demo: bool = typer.Option(False, "--demo", help="Read-only sample dashboard; no root or token required."),
        foreground: bool = typer.Option(False, "--foreground", help="Run the HTTP backend directly; used by systemd.")):
    """Open the authenticated macOS-style web control panel."""
    if ctx.invoked_subcommand is not None:
        return
    from splitforge.web.server import serve
    state = ctx.find_root().obj["state"]
    if not demo and not foreground and sys.stdin.isatty():
        from splitforge.web.setup import load_settings, wizard
        settings = load_settings()
        if settings is None:
            wizard(state)
        else:
            require_root()
            run(["systemctl", "start", "splitforge-web.service"])
            typer.echo(f"Panel ready: {settings.url}\nAccess token file: {settings.token_file}")
        return
    serve(state, host=host, port=port, token_file=token_file, demo=demo)


@web_app.command("setup")
def web_setup(ctx: typer.Context,
              address: str | None = typer.Option(None, "--address", help="Domain or public IP. Omit for the wizard."),
              tls: bool = typer.Option(True, "--tls/--no-tls", help="Request a trusted SSL certificate automatically."),
              local: bool = typer.Option(False, "--local", help="Local HTTP with SSH forwarding."),
              port: int = typer.Option(9090, "--port", min=1, max=65535),
              backend_port: int = typer.Option(8765, "--backend-port", min=1, max=65535),
              email: str = typer.Option("", "--email"),
              token_file: Path = typer.Option(Path("/etc/splitforge/web.token"), "--token-file"),
              agree_tos: bool = typer.Option(False, "--agree-tos", help="Accept Let's Encrypt's subscriber agreement.")):
    """Configure first launch, HTTPS, permanent service and certificate renewal."""
    from splitforge.web.setup import WebSettings, deploy, wizard
    state = ctx.find_root().obj["state"]
    if address is None and not local:
        if not sys.stdin.isatty():
            raise ValueError("Use an interactive terminal or supply --address / --local")
        wizard(state)
        return
    settings = WebSettings(mode="local" if local else "https" if tls else "http", address=address or "",
                           port=port, backend_port=backend_port, email=email, state=str(state), token_file=str(token_file))
    deploy(settings, agree_tos=agree_tos, report=typer.echo)


@app.command("restore")
def restore(ctx: typer.Context):
    require_root()
    store, manager, runner = objects(ctx)
    enabled = [profile.id for profile in store.profiles() if run(
        ['systemctl', 'is-enabled', '--quiet', f'splitforge-profile-{profile.id}.service'], check=False).returncode == 0]
    runner.restore(enabled)
    typer.echo("Enabled workload assignments restored")


@app.command("stop-all")
def stop_all(ctx: typer.Context, preserve: bool = typer.Option(False, "--preserve", help="Keep boot/assignment intent for upgrade restore.")):
    require_root()
    store, manager, runner = objects(ctx)
    from splitforge.core.traffic import stop_service
    stop_service(store)
    from splitforge.core.failover import unit_name
    run(['systemctl', 'stop', unit_name(store)], check=False, timeout=310)
    for binding in store.apps():
        if preserve:
            run(["systemctl", "stop", runner.unit(binding)], check=False)
        else:
            runner.stop(binding.id)
    for profile in store.profiles():
        unit = f"splitforge-profile-{profile.id}.service"
        if Path("/etc/systemd/system", unit).exists():
            if preserve:
                run(["systemctl", "stop", unit], timeout=130)
            else:
                manager.stop(profile.id)
    typer.echo("Workloads stopped; state retained")


def main():
    try:
        app()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        Console(stderr=True).print(Text(f"SplitForge: {error}", style="red"))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
