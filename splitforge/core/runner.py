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
        network = "\n".join(self._network(profile))
        hardening = "NoNewPrivileges=yes\nCapabilityBoundingSet=\nAmbientCapabilities=\nRestrictSUIDSGID=yes\n"
        if app.service:
            return f"[Unit]\n{dependencies}\n[Service]\n{network}\n{hardening}"
        command = " ".join(unit_word(a) for a in app.argv)
        return (f"[Unit]\nDescription=SplitForge application {app.id}\n{dependencies}\n"
                f"[Service]\nType=exec\nUser={app.user}\n"
                f"WorkingDirectory={app.cwd.replace('%', '%%')}\nExecStart={command}\n"
                f"Restart=on-failure\nRestartSec=3\nKillMode=control-group\nTimeoutStopSec=20\n"
                f"{network}\n{hardening}\n[Install]\nWantedBy=multi-user.target\n")

    def running(self, app: AppBinding) -> bool:
        return run(["systemctl", "is-active", "--quiet", self.unit(app)], check=False).returncode == 0

    def bind(self, app_id: str, profile_name: str | None, *, start: bool = True):
        require_root()
        profile = self.store.profile(profile_name) if profile_name else None
        if profile:
            self.manager.start(profile.id)
        with self.store.operation(app_id):
            old = self.store.app(app_id)
            self._validate_service(old)
            updated = dataclasses.replace(old, profile_id=profile.id if profile else None, enabled=start)
            content = self._render(updated, profile)
            path = self._path(old)
            previous = path.read_text() if path.exists() else None
            was_running = self.running(old)
            was_enabled = run(["systemctl", "is-enabled", "--quiet", self.unit(old)], check=False).returncode == 0
            run(["systemctl", "stop", self.unit(old)], check=False)
            if self.running(old):
                raise RuntimeError("Application did not stop; assignment was not changed")
            try:
                if updated.service and profile is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_secret(path, content, 0o644)
                run(["systemctl", "daemon-reload"])
                if start:
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

    def stop(self, app_id: str):
        require_root()
        with self.store.operation(app_id):
            app = self.store.app(app_id)
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
