"""Application execution, service adoption and transactional swaps."""
from __future__ import annotations

import dataclasses
import os
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from splitforge.core.netns import atomic_secret, namespace_properties, require_root, run, unit_word
from splitforge.state import AppBinding, Profile, StateStore

if TYPE_CHECKING:
    from splitforge.protocols.manager import ProtocolManager


class Runner:
    def __init__(self, store: StateStore, manager: ProtocolManager):
        self.store, self.manager = store, manager

    @staticmethod
    def unit(app: AppBinding) -> str:
        return app.service or f"splitforge-app-{app.id}.service"

    @staticmethod
    def _identity(user: str):
        import pwd
        return pwd.getpwuid(int(user)) if user.isdecimal() else pwd.getpwnam(user)

    @staticmethod
    def _network(profile: Profile | None) -> list[str]:
        if profile is None:
            return []
        return namespace_properties(profile)

    def _path(self, app: AppBinding) -> Path:
        base = Path("/etc/systemd/system")
        return (base / f"{app.service}.d" / "90-splitforge.conf" if app.service
                else base / self.unit(app))

    def _validate_service(self, app: AppBinding):
        if not app.service:
            return
        properties = run(["systemctl", "show", app.service, "--property=User,LoadState,Id,Names,TriggeredBy"]).stdout
        values = dict(line.split("=", 1) for line in properties.splitlines() if "=" in line)
        if values.get("LoadState") != "loaded":
            raise ValueError("Service is not loaded")
        names = set(values.get("Names", "").split()) | {values.get("Id", ""), app.service}
        protected = {"ssh.service", "sshd.service", "networking.service", "NetworkManager.service",
                     "systemd-networkd.service", "systemd-resolved.service"}
        if names & protected or any(n.startswith(("ssh@", "sshd@")) for n in names):
            raise ValueError("SSH and host networking services cannot be routed")
        service_identity = self._identity(values.get("User") or "root")
        if service_identity.pw_uid != self._identity(app.user).pw_uid:
            raise ValueError("Registered user must match the service's effective user")
        if values.get("TriggeredBy"):
            raise ValueError("Socket-activated services must be converted to ordinary services first")
        if any(name.startswith(("splitforge-", "user@")) for name in names):
            raise ValueError("Use bind_user for user managers; internal units cannot be adopted")

    def _render(self, app: AppBinding, profile: Profile | None) -> str:
        self._identity(app.user)
        if profile and (not app.kill_switch or not app.isolate_dns):
            raise ValueError("Shared profile namespaces require kill-switch and DNS isolation")
        dependencies = (f"BindsTo=splitforge-profile-{profile.id}.service\n"
                        f"After=splitforge-profile-{profile.id}.service\n" if profile else "")
        from splitforge.core.traffic import unit_name
        dependencies += f'Wants={unit_name(self.store)}\nAfter={unit_name(self.store)}\n'
        network = "\n".join(self._network(profile))
        hardening = "NoNewPrivileges=yes\nCapabilityBoundingSet=\nAmbientCapabilities=\nRestrictSUIDSGID=yes\n"
        helper = [sys.executable, '-m', 'splitforge.core.traffic', '--state', str(self.store.path.resolve())]
        check = ['check', '--app', app.id] + (['--profile', profile.id] if profile else [])
        accounting = ('IPAccounting=yes\nExecCondition=' + ' '.join(unit_word(word) for word in
                       ['+' + helper[0], *helper[1:], *check])
                      + '\nExecStopPost=' + ' '.join(unit_word(word) for word in
                       ['-+' + helper[0], *helper[1:], 'final', '--app', app.id]) + '\n')
        if app.service:
            return (f"[Unit]\n{dependencies}\n[Service]\n{network}\n{hardening}{accounting}" if profile
                    else f'[Unit]\n{dependencies}\n[Service]\n{accounting}')
        command = " ".join(unit_word(a) for a in app.argv)
        return (f"[Unit]\nDescription=SplitForge application {app.id}\n{dependencies}\n"
                f"[Service]\nType=exec\nUser={app.user}\n"
                f"WorkingDirectory={app.cwd.replace('%', '%%')}\nExecStart={command}\n"
                f"Restart=on-failure\nRestartSec=3\nKillMode=control-group\nTimeoutStopSec=20\n"
                f"{network}\n{hardening}{accounting}\n[Install]\nWantedBy=multi-user.target\n")

    def running(self, app: AppBinding) -> bool:
        return run(["systemctl", "is-active", "--quiet", self.unit(app)], check=False).returncode == 0

    def test(self, app_id: str) -> dict:
        from splitforge.core.probe import test_application
        return test_application(self, app_id)

    def restore(self, enabled_profiles=()):
        require_root()
        bindings = self.store.apps()
        automatic = set().union(*(binding.profile_references for binding in bindings if binding.failover_enabled))
        needed = {binding.profile_id for binding in bindings if binding.enabled and not binding.failover_enabled and binding.profile_id}
        needed |= set(self.store.snapshot()['users'].values()) | (set(enabled_profiles) - automatic)
        for profile_id in needed:
            self.manager.start(profile_id)
        for user, profile_id in self.store.snapshot()['users'].items():
            self.bind_user(user, profile_id)
        for binding in bindings:
            if binding.enabled:
                self.bind(binding.id, binding.profile_id, preserve_failover=True, expected=binding)
        if any(binding.failover_enabled for binding in bindings):
            from splitforge.core.failover import ensure_service
            ensure_service(self.store)

    def bind(self, app_id: str, profile_name: str | None, *, start: bool = True,
             backup_profile_name: str | None = None, preserve_failover: bool = False, expected: AppBinding | None = None):
        require_root()
        current = self.store.app(app_id)
        if expected is not None and current != expected:
            raise RuntimeError('Application assignment changed during the health check; retry with current policy')
        self._validate_service(current)
        from splitforge.core.traffic import TrafficStore
        if start:
            TrafficStore(self.store).guard('apps', app_id)
            from splitforge.core.traffic import ensure_service
            ensure_service(self.store)
        profile = self.store.profile(profile_name) if profile_name else None
        backup = self.store.profile(backup_profile_name) if backup_profile_name else None
        primary = profile
        if backup:
            if preserve_failover:
                raise ValueError('Choose either a new backup policy or preservation of the existing policy')
            if not profile or profile.id == backup.id:
                raise ValueError('Choose two distinct tunnel profiles; Direct cannot be a failover target')
            from splitforge.core.failover import ensure_service
            ensure_service(self.store)
        fallback = backup
        if preserve_failover and current.failover_enabled:
            if expected is None:
                from splitforge.core.failover import ensure_service
                ensure_service(self.store)
            other = (current.backup_profile_id if profile and profile.id == current.primary_profile_id
                     else current.primary_profile_id)
            fallback = self.store.profile(other)
        deferred = False
        if profile:
            try:
                self.manager.start(profile.id)
            except Exception:
                if not fallback:
                    raise
                try:
                    self.manager.start(fallback.id)
                    from splitforge.core.diagnostics import namespace_checks
                    if not all(ok for _, ok, _ in namespace_checks(self.manager, fallback)):
                        raise RuntimeError('Backup namespace guard/DNS/route checks failed')
                    self.manager.test(fallback.id, persist=False)
                    profile = fallback
                except Exception:
                    # Persist a fail-closed unit and intent so the monitor can recover later.
                    deferred = True
        with self.store.operation(app_id):
            old = self.store.app(app_id)
            if expected is not None and old != expected:
                raise RuntimeError('Application assignment changed during the health check; retry with current policy')
            self._validate_service(old)
            policy = ({} if preserve_failover else {'primary_profile_id': primary.id if backup else None,
                      'backup_profile_id': backup.id if backup else None, 'failover_enabled': bool(backup)})
            updated = dataclasses.replace(old, profile_id=profile.id if profile else None, enabled=start, **policy)
            content = self._render(updated, profile)
            path = self._path(old)
            previous = path.read_text() if path.exists() else None
            was_running = self.running(old)
            was_enabled = run(["systemctl", "is-enabled", "--quiet", self.unit(old)], check=False).returncode == 0
            run(["systemctl", "stop", self.unit(old)], check=False)
            if self.running(old):
                raise RuntimeError("Application did not stop; assignment was not changed")
            try:
                atomic_secret(path, content, 0o644)
                run(["systemctl", "daemon-reload"])
                if start and not deferred:
                    run(["systemctl", "start", self.unit(updated)])
                if not updated.service:
                    run(["systemctl", "enable" if start else "disable", self.unit(updated)])
                self.store.save_app(updated)
            except BaseException as failure:
                run(["systemctl", "stop", self.unit(updated)], check=False)
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_secret(path, previous, 0o644)
                run(["systemctl", "daemon-reload"])
                if previous is not None and not old.service:
                    run(["systemctl", "enable" if was_enabled else "disable", self.unit(old)], check=False)
                if was_running:
                    try:
                        run(["systemctl", "start", self.unit(old)])
                    except RuntimeError as rollback:
                        raise RuntimeError("Swap and restart rollback failed; application remains stopped") from rollback
                self.store.save_app(old)
                raise RuntimeError("Swap failed; previous assignment restored") from failure
        return updated

    def suspend(self, app: AppBinding):
        """Fail closed without clearing the saved enabled/failover intent."""
        require_root()
        with self.store.operation(app.id):
            if self.store.app(app.id) != app:
                raise RuntimeError('Application policy changed; suspension cancelled')
            self._validate_service(app)
            run(['systemctl', 'stop', self.unit(app)])

    def stop(self, app_id: str):
        require_root()
        with self.store.operation(app_id):
            app = self.store.app(app_id)
            self._validate_service(app)
            managed = self._path(app).exists()
            if managed or app.service:
                run(["systemctl", "stop", self.unit(app)])
            if managed and not app.service:
                run(["systemctl", "disable", self.unit(app)])
            self.store.save_app(dataclasses.replace(app, enabled=False))

    def remove(self, app_id: str):
        require_root()
        with self.store.operation(app_id):
            self.stop(app_id)
            app = self.store.app(app_id)
            self._path(app).unlink(missing_ok=True)
            run(["systemctl", "daemon-reload"])
            self.store.delete_app(app_id)
        from splitforge.core.traffic import cleanup_if_unused
        cleanup_if_unused(self.store)

    def execute(self, argv: list[str], *, profile_name: str | None = None,
                user: str = "nobody", cwd: str | None = None) -> int:
        require_root()
        self._identity(user)
        if not argv:
            raise ValueError("An executable command is required")
        import shutil
        executable = shutil.which(argv[0])
        if not executable:
            raise FileNotFoundError(argv[0])
        argv = [executable, *argv[1:]]
        bound = self.store.snapshot()["users"].get(user)
        profile = (None if profile_name == "direct" else
                   self.store.profile(profile_name or bound) if profile_name or bound else None)
        if profile:
            self.manager.start(profile.id)
        args = ["systemd-run", "--quiet", "--wait", "--collect",
                "--pty" if sys.stdin.isatty() and sys.stdout.isatty() else "--pipe",
                "--service-type=exec", f"--unit=splitforge-exec-{uuid.uuid4().hex[:8]}",
                f"--uid={user}", f"--working-directory={cwd or os.getcwd()}",
                "--property=NoNewPrivileges=yes", "--property=CapabilityBoundingSet=",
                "--property=AmbientCapabilities=", "--property=KillMode=control-group"]
        for setting in self._network(profile):
            args.append(f"--property={setting}")
        if profile:
            args.extend([f"--property=BindsTo=splitforge-profile-{profile.id}.service",
                         f"--property=After=splitforge-profile-{profile.id}.service"])
        import subprocess
        return subprocess.call([*args, "--", *[a.replace("$", "$$") for a in argv]])

    def bind_user(self, user: str, profile_name: str | None):
        """Route future systemd --user workloads; never move live SSH sessions.

        Existing processes and system services with User= need explicit restarts
        or individual adoption. UID-wide live migration is not a Linux feature.
        """
        require_root()
        identity = self._identity(user)
        if identity.pw_uid < 1000:
            raise ValueError("User-manager binding requires a non-system account")
        profile = self.store.profile(profile_name) if profile_name else None
        if profile:
            self.manager.start(profile.id)
        with self.store.operation():
            unit = f"user@{identity.pw_uid}.service"
            path = Path("/etc/systemd/system", unit + ".d", "90-splitforge.conf")
            if profile:
                network = "\n".join(self._network(profile))
                atomic_secret(path, f"[Unit]\nBindsTo=splitforge-profile-{profile.id}.service\n"
                              f"After=splitforge-profile-{profile.id}.service\n[Service]\n{network}\n"
                              "NoNewPrivileges=yes\nCapabilityBoundingSet=\nAmbientCapabilities=\n", 0o644)
            else:
                path.unlink(missing_ok=True)
            run(["systemctl", "daemon-reload"])
            self.store.assign_user(user, profile.id if profile else None)
        return unit

    def proxychains(self, profile_name: str, argv: list[str], *, user: str = "nobody") -> int:
        """TCP-only convenience mode. This mode is NOT a namespace kill-switch."""
        require_root()
        self._identity(user)
        profile = self.store.profile(profile_name)
        if profile.protocol in {"wireguard", "openvpn"}:
            raise ValueError("Use namespace execution for WireGuard/OpenVPN")
        from splitforge.core.traffic import TrafficStore
        limits = TrafficStore(self.store).snapshot()['profiles'].get(profile.id, {})
        if limits.get('quota') is not None or limits.get('download_bps', 0) or limits.get('upload_bps', 0):
            raise ValueError('Limited profiles require namespace execution; remove --proxychains')
        self.manager.start(profile.id)
        path = Path("/run/splitforge", profile.id, "proxychains.conf")
        atomic_secret(path, f"strict_chain\nproxy_dns\n[ProxyList]\nsocks5 {profile.gateway} 1080\n", 0o644)
        # The profile runtime directory is private. Hand the readable configuration
        # through systemd's credential mount instead of relaxing its permissions.
        import subprocess
        unit = f"splitforge-proxy-{uuid.uuid4().hex[:8]}.service"
        return subprocess.call(["systemd-run", "--quiet", "--wait", "--collect", "--pipe",
                                f"--unit={unit}",
                                f"--uid={user}", "--property=NoNewPrivileges=yes",
                                "--property=CapabilityBoundingSet=",
                                f"--property=LoadCredential=proxychains:{path}",
                                "--", "/usr/bin/proxychains4", "-f", f"/run/credentials/{unit}/proxychains",
                                *[a.replace("$", "$$") for a in argv]])
