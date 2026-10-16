from __future__ import annotations

import dataclasses
import ipaddress
import shlex
from pathlib import Path

import httpx
from pydantic import AnyHttpUrl, BaseModel
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, ContentSwitcher, DataTable, Footer, Input, Label, ProgressBar, RichLog, Select, Static

from splitforge.core.netns import run
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, Profile, StateStore
from splitforge.tui.screens.app_router import AppForm, BrowseView, RouterView
from splitforge.tui.screens.home import HomeView
from splitforge.tui.screens.help import CoreChecklist, GuideModal
from splitforge.tui.screens.profiles import ProfileForm, ProfilesView


class DNSSettings(BaseModel):
    url: AnyHttpUrl
    bootstrap: ipaddress.IPv4Address


class SecurityView(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("ISOLATE THE WORKLOAD", classes="eyebrow")
        yield Static("Security & DNS guard", classes="page-title")
        yield Static("Tunnel namespaces deny Direct fallback and block IPv6. Workloads sharing a profile share these guards.", classes="subtitle")
        yield Static("● KILL SWITCH ENABLED     ● ENCRYPTED DNS     ● HOST ROUTES SCOPED", classes="guard-banner")
        yield Label("Profile · stop it before editing DNS")
        yield Select([("Select a profile", "none")], value="none", allow_blank=False, id="security-profile")
        yield Label("DNS-over-HTTPS URL")
        yield Input("https://cloudflare-dns.com/dns-query", id="dns-url")
        yield Label("Bootstrap IPv4 · must serve the URL hostname with a valid certificate")
        yield Input("1.1.1.1", id="dns-ip")
        yield Button("Save encrypted DNS", id="save-dns", variant="primary")
        yield Static("Root workloads are supported with privilege hardening. Use trusted programs: a network namespace is not a complete hostile-code sandbox.", classes="hint")

    @on(Select.Changed, "#security-profile")
    def selected(self, event):
        profile = next((p for p in self.app.current_profiles if p.id == event.value), None)
        if profile:
            self.query_one("#dns-url", Input).value = profile.doh_url
            self.query_one("#dns-ip", Input).value = profile.doh_ip

    @on(Button.Pressed, "#save-dns")
    def save(self, event):
        event.stop()
        profile_id = self.query_one(Select).value
        if profile_id == "none":
            self.notify("Select a profile first")
            return
        try:
            settings = DNSSettings(url=self.query_one("#dns-url", Input).value,
                                   bootstrap=self.query_one("#dns-ip", Input).value)
            if settings.url.scheme != "https":
                raise ValueError("HTTPS is required")
        except ValueError:
            self.notify("Enter a valid HTTPS URL and IPv4 bootstrap address", severity="error")
            return
        def operation():
            profile = self.app.store.profile(str(profile_id))
            if self.app.manager.netns.exists(profile):
                raise ValueError("Stop this profile before changing DNS")
            self.app.store.save_profile(dataclasses.replace(profile, doh_url=str(settings.url), doh_ip=str(settings.bootstrap)))
        self.app.perform(operation, "DNS saved for the next profile start")

    def refresh_data(self, data):
        ids = tuple((p["name"], p["id"]) for p in data["profiles"])
        if ids != getattr(self, "_options", None):
            self._options = ids
            select = self.query_one(Select)
            current = select.value
            select.set_options([("Select a profile", "none"), *ids])
            select.value = current if current in {value for _, value in ids} else "none"


class LogsView(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("OBSERVE & OPERATE", classes="eyebrow")
        yield Static("Live logs & dependencies", classes="page-title")
        with Horizontal(classes="toolbar"):
            yield Button("Core checklist · F2", id="install-dependency", variant="primary")
            yield Button("Read journal", id="read-journal")
        yield Static("Pinned binary downloads verify SHA-256. Journal follows SplitForge units while this panel is open.", classes="hint")
        yield Static("Choose cores to install / هسته‌های موردنیاز را انتخاب کنید", id="dependency-status", markup=False)
        yield ProgressBar(total=1, show_eta=False, id="dependency-progress")
        yield RichLog(id="live-log", wrap=True, highlight=False, markup=False, max_lines=2000)

    @on(Button.Pressed)
    def button(self, event):
        event.stop()
        if event.button.id == "read-journal":
            self.app.load_journal()
        elif event.button.id == "install-dependency":
            self.app.action_core_checklist()


class SplitForgeApp(App):
    TITLE = "SplitForge"
    CSS_PATH = "styles.tcss"
    BINDINGS = [Binding("q", "quit", "Quit"), Binding("1", "navigate('home')", "Home"),
        Binding("2", "navigate('router')", "Router"), Binding("3", "navigate('profiles')", "Profiles"),
        Binding("4", "navigate('browse')", "Add app"), Binding("5", "navigate('security')", "Security"),
        Binding("6", "navigate('logs')", "Logs"), Binding("a", "add_app", "Add"),
        Binding("n", "new_profile", "New VPN"), Binding("c", "change_route", "Change"),
        Binding("t", "test_all", "Test active"), Binding("r", "refresh", "Refresh"),
        Binding("f1", "guide", "Guide"), Binding("f2", "core_checklist", "Cores")]

    def __init__(self, state_path=Path("/etc/splitforge/state.json"), demo=False):
        super().__init__()
        self.store = StateStore(state_path)
        self.manager = ProtocolManager(self.store)
        self.runner = Runner(self.store, self.manager)
        self.demo, self.busy = demo, False
        self.current_profiles, self.current_apps = [], []
        self.data = {"profiles": [], "apps": []}
        self.host_ip = "checking…" if not demo else "DEMO"
        self.journal_cursor = None
        self.route_baseline = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("⚡ SPLITFORGE", id="brand")
            yield Static("", id="host-status")
        with Horizontal(id="workspace"):
            with VerticalScroll(id="sidebar"):
                yield Static("HOME MENU", id="menu-title")
                for key, label in [("home", "🏠 Home dashboard"), ("router", "🔀 App router"),
                    ("profiles", "🔐 VPN profiles"), ("browse", "＋ Add / browse app"),
                    ("security", "🛡 Security & DNS"), ("logs", "📜 Logs & tools")]:
                    yield Button(label, id=f"nav-{key}", classes="nav-button")
                yield Button("? Quick start · F1", id="open-guide", classes="utility-button")
                yield Button("↓ Core checklist · F2", id="open-cores", classes="utility-button")
                yield Static("─────────────\n[Enter] Select\n[C] Change route\n[A] Register app\n[N] New profile\n[T] Test active\n[Q] Exit", id="shortcuts", markup=False)
                yield Static("DEMO · READ ONLY" if self.demo else "ROOT CONTROL PLANE\nWorkloads: root or user", id="mode-label")
            with ContentSwitcher(initial="home", id="pages"):
                yield HomeView(id="home", classes="page")
                yield RouterView(id="router", classes="page")
                yield ProfilesView(id="profiles", classes="page")
                yield BrowseView(id="browse", classes="page")
                yield SecurityView(id="security", classes="page")
                yield LogsView(id="logs", classes="page")
        yield Static("Ready", id="operation-status")
        yield Footer()

    def on_mount(self):
        self.query_one("#nav-home", Button).add_class("selected-nav")
        self.set_interval(4, self.action_refresh)
        self.set_interval(5, self.poll_journal)
        self.action_refresh()
        if not self.demo:
            self.find_host_ip()

    def on_resize(self, event):
        self.set_class(event.size.width < 100, "compact")

    @on(Button.Pressed, ".nav-button")
    def navigation(self, event):
        event.stop()
        self.action_navigate(event.button.id.removeprefix("nav-"))

    def action_navigate(self, page):
        self.query_one("#pages", ContentSwitcher).current = page
        for button in self.query(".nav-button"):
            button.set_class(button.id == f"nav-{page}", "selected-nav")
        if page == "logs":
            self.load_journal()

    def action_quit(self):
        if self.busy:
            self.notify("Wait for the current operation to finish before exiting")
        else:
            self.exit()

    @on(Button.Pressed, "#open-guide")
    def guide_button(self, event):
        event.stop()
        self.action_guide()

    @on(Button.Pressed, "#open-cores")
    def cores_button(self, event):
        event.stop()
        self.action_core_checklist()

    def action_guide(self):
        if isinstance(self.screen, (GuideModal, CoreChecklist)):
            return
        self.push_screen(GuideModal(), lambda choice: self.action_core_checklist() if choice == "cores" else None)

    def action_core_checklist(self):
        if isinstance(self.screen, GuideModal):
            self.screen.dismiss("cores")
            return
        if isinstance(self.screen, CoreChecklist):
            return
        if self.busy:
            self.notify("Wait for the current operation to finish")
            return
        from splitforge.core.dependencies import COMPONENTS, component_plan
        tools = {tool for profile in self.current_profiles for tool in self.manager.dependencies(profile.protocol)}
        recommended = [name for name, (binaries, _) in COMPONENTS.items() if tools.intersection(binaries)]
        if not self.current_profiles:
            recommended = ["xray", "tun2socks"]
        self.push_screen(CoreChecklist(component_plan(recommended)), self.install_cores)

    def install_cores(self, names):
        if not names:
            return
        from splitforge.core.dependencies import component_installed, component_plan, install
        names = component_plan(names)
        self.action_navigate("logs")

        def operation():
            failures = []
            for index, name in enumerate(names):
                self.call_from_thread(self.core_progress, index, len(names), f"Installing {name}…")
                try:
                    result = f"{name}: already installed; skipped" if component_installed(name) else install(name)
                except Exception as failure:
                    failures.append(name)
                    result = f"ERROR · {name}: {failure}"
                self.call_from_thread(self.core_progress, index + 1, len(names), result)
            if failures:
                raise RuntimeError("Failed: " + ", ".join(failures) + "; successful installations were retained. See logs.")

        self.perform(operation, "Selected cores processed; see individual results in Logs & Tools")

    def core_progress(self, completed, total, message):
        self.query_one("#dependency-status", Static).update(Text(f"{completed}/{total} · {message}"))
        self.query_one("#dependency-progress", ProgressBar).update(total=total, progress=completed)
        self.append_log(message)

    def action_add_app(self):
        self.open_app_form()

    def action_new_profile(self):
        self.push_screen(ProfileForm(), self.save_profile_form)

    def action_change_route(self):
        self.action_navigate("router")
        self.query_one(RouterView).change()

    def action_test_all(self):
        def operation():
            for profile in self.store.profiles():
                if self.manager.netns.exists(profile):
                    self.manager.test(profile.id)
        self.perform(operation, "Active profiles tested")

    def open_app_form(self, command="", user="root", cwd="/", service=""):
        def save(binding):
            if binding:
                def operation():
                    if any(a.name == binding.name for a in self.store.apps()):
                        raise ValueError("Application name already exists")
                    self.runner._identity(binding.user)
                    self.runner._validate_service(binding)
                    self.store.save_app(binding)
                self.perform(operation, "Workload registered; assign a route to start")
        self.push_screen(AppForm(command, user, cwd, service), save)

    def save_profile_form(self, values):
        if not values:
            return
        def operation():
            if values["method"] == "import":
                self.manager.import_profile(values["source"], name=values["name"], replace_id=values.get("replace_id"))
            else:
                self.manager.dns_tunnel(values["name"], values["method"], values["source"], values["resolver"],
                    public_key=(Path(values["key"]).read_text().strip() if values["key"] and Path(values["key"]).is_file()
                                else values["key"]) if values["method"] == "dnstt" else "",
                    certificate=values["key"] if values["method"] == "slipstream" else "",
                    replace_id=values.get("replace_id"))
        self.perform(operation, "Profile imported; start it when ready")

    def remove_profile(self, profile_id):
        self.manager.remove(profile_id)

    def perform(self, operation, label):
        if self.demo:
            self.notify("Read-only demo: no network or state changes were made")
            return
        if self.busy:
            self.notify("Another operation is still running")
            return
        self.busy = True
        self.query_one("#operation-status", Static).update("◌ Working… " + label)
        self.operation_worker(operation, label)

    @work(thread=True, group="mutations")
    def operation_worker(self, operation, label):
        error = None
        try:
            operation()
        except Exception as failure:
            error = str(failure)
        self.call_from_thread(self.operation_done, label, error)

    def operation_done(self, label, error):
        self.busy = False
        message = "ERROR · " + error if error else "✓ " + label
        self.query_one("#operation-status", Static).update(Text(message, style="red" if error else "green"))
        self.append_log(message)
        self.notify(error or label, severity="error" if error else "information", timeout=6)
        self.action_refresh()

    def action_refresh(self):
        if not self.busy:
            self.refresh_worker()

    @work(thread=True, exclusive=True, group="refresh")
    def refresh_worker(self):
        try:
            if self.demo:
                profiles = [Profile("vless-demo", "vless", {}, id="de000001", slot=1, exit_ip="192.0.2.10", country="DE", latency_ms=42),
                            Profile("wireguard-demo", "wireguard", {}, id="ab000002", slot=2, exit_ip="198.51.100.20", country="US", latency_ms=110)]
                apps = [AppBinding("telegram_bot.py", ["/usr/bin/python3", "/srv/bot.py"], id="aa000001", profile_id=profiles[0].id, user="root"),
                        AppBinding("backup.sh", ["/bin/bash", "/srv/backup.sh"], id="aa000002", user="nobody")]
            else:
                profiles, apps = self.store.profiles(), self.store.apps()
            rows = []
            for profile in profiles:
                status = ({"active": True, "bandwidth": {"rx": 1048576, "tx": 262144}} if self.demo else self.manager.status(profile.id))
                rows.append({"id": profile.id, "name": profile.name, "protocol": profile.protocol,
                    "country": profile.country, "exit_ip": profile.exit_ip, "latency_ms": profile.latency_ms,
                    "active": status["active"], **status.get("bandwidth", {})})
            bindings = [{"id": a.id, "name": a.name, "user": a.user, "profile_id": a.profile_id,
                         "command": a.service or shlex.join(a.argv), "running": True if self.demo else self.runner.running(a)} for a in apps]
            route = None if self.demo else run(["ip", "-j", "-4", "route", "show", "table", "main"], check=False).stdout
            self.call_from_thread(self.apply_data, {"profiles": rows, "apps": bindings}, profiles, apps, route)
        except Exception as failure:
            self.call_from_thread(self.append_log, "ERROR · refresh: " + str(failure))

    def apply_data(self, data, profiles, apps, route):
        self.data, self.current_profiles, self.current_apps = data, profiles, apps
        if self.route_baseline is None:
            self.route_baseline = route
        for view in (HomeView, RouterView, ProfilesView, SecurityView):
            self.query_one(view).refresh_data(data)
        host = "DEMO · READ ONLY · SAMPLE ADDRESSES" if self.demo else (
            f"Host IP: {self.host_ip}  ·  {'⚠ HOST ROUTE CHANGED' if route != self.route_baseline else '🛡 HOST ROUTE'}  ·  {sum(p['active'] for p in data['profiles'])} active")
        self.query_one("#host-status", Static).update(Text(host))

    @work(thread=True, exclusive=True, group="host-ip")
    def find_host_ip(self):
        try:
            with httpx.Client(timeout=5, trust_env=False) as client:
                response = client.get("https://www.cloudflare.com/cdn-cgi/trace")
                response.raise_for_status()
                values = dict(line.split("=", 1) for line in response.text.splitlines() if "=" in line)
                self.host_ip = str(ipaddress.ip_address(values["ip"]))
        except Exception:
            self.host_ip = "unavailable"

    def append_log(self, line):
        style = "red" if any(word in line.lower() for word in ("error", "failed", "failure")) else "cyan"
        self.query_one("#live-log", RichLog).write(Text(line, style=style))

    def poll_journal(self):
        if self.query_one("#pages", ContentSwitcher).current == "logs":
            self.load_journal()

    @work(thread=True, exclusive=True, group="journal")
    def load_journal(self):
        if self.demo:
            self.call_from_thread(self.append_log, "DEMO · no system journal or dependency installation is accessed")
            return
        argv = ["journalctl", "--no-pager", "-n", "100", "-o", "short-iso", "-u", "splitforge-*", "--show-cursor"]
        if self.journal_cursor:
            argv += ["--after-cursor", self.journal_cursor]
        result = run(argv, check=False, timeout=8)
        for line in result.stdout.splitlines():
            if line.startswith("-- cursor: "):
                self.journal_cursor = line[11:]
            else:
                self.call_from_thread(self.append_log, line)

    @work(thread=True, exclusive=True, group="services")
    def load_services(self):
        if self.demo:
            self.call_from_thread(self.notify, "Read-only demo; service discovery is disabled")
            return
        result = run(["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--no-legend", "--plain"], timeout=15)
        rows = []
        for line in result.stdout.splitlines():
            fields = line.split(None, 4)
            if len(fields) == 5:
                rows.append((fields[0], fields[2] + "/" + fields[3], fields[4]))
        self.call_from_thread(self.apply_services, rows)

    def apply_services(self, rows):
        table = self.query_one("#service-table", DataTable)
        table.clear()
        for name, state, description in rows:
            table.add_row(Text(name), Text(state), Text(description), key=name)
