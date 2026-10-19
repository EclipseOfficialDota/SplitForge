from __future__ import annotations

import shlex
import shutil
from pathlib import Path

import psutil
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, DataTable, DirectoryTree, Input, Label, Select, Static, TabbedContent, TabPane

from splitforge.state import AppBinding
from splitforge.tui.screens.home import flag


class RouteSelector(ModalScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def action_cancel(self):
        self.dismiss(False)

    def __init__(self, binding, profiles):
        super().__init__()
        self.binding, self.profiles = binding, profiles

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(Text(f"↗ Assign route · {self.binding.name}"), classes="dialog-title")
            yield Static("Applying stops and restarts this workload. Open connections will close.", classes="subtitle")
            options = [("◌ Direct server internet", "direct")]
            options.extend((f"{flag(p['country'])} {p['name']} · {p['protocol']} · {p['exit_ip'] or 'not tested'}", p["id"]) for p in self.profiles)
            primary = self.binding.primary_profile_id if self.binding.failover_enabled else self.binding.profile_id
            yield Select(options, value=primary or "direct", allow_blank=False, id="route-choice")
            yield Label('Automatic backup tunnel · switching restarts the program')
            backups = [('Disabled · single route', 'disabled')] + [(p['name'], p['id']) for p in self.profiles if p['id'] != primary]
            yield Select(backups, value=self.binding.backup_profile_id or 'disabled', allow_blank=False,
                         disabled=not primary, id='backup-choice')
            yield Checkbox("Kill switch · required for tunnel profiles", value=True, disabled=True)
            yield Checkbox("Isolated encrypted DNS · required for tunnel profiles", value=True, disabled=True)
            with Horizontal(classes="dialog-actions"):
                yield Button("Apply & restart", id="apply-route", variant="primary")
                yield Button("Cancel", id="cancel-modal")

    @on(Button.Pressed)
    def button(self, event):
        event.stop()
        if event.button.id == "apply-route":
            value = self.query_one("#route-choice", Select).value
            backup = self.query_one('#backup-choice', Select).value
            self.dismiss({'profile': None if value == 'direct' else str(value),
                          'backup': None if value == 'direct' or backup == 'disabled' else str(backup)})
        else:
            self.dismiss(False)

    @on(Select.Changed, '#route-choice')
    def primary_changed(self, event):
        if not self.query('#backup-choice'):
            return
        backup = self.query_one('#backup-choice', Select)
        previous = backup.value
        options = [('Disabled · single route', 'disabled')] + [(p['name'], p['id']) for p in self.profiles if p['id'] != event.value]
        backup.set_options(options)
        backup.value = previous if previous in {value for _, value in options} and event.value != 'direct' else 'disabled'
        backup.disabled = event.value == 'direct'


class AppForm(ModalScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def action_cancel(self):
        self.dismiss(None)

    def __init__(self, command="", user="root", cwd="/", service=""):
        super().__init__()
        self.command, self.user, self.cwd, self.service = command, user, cwd, service

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("＋ Register workload", classes="dialog-title")
            yield Label("Display name")
            yield Input(placeholder="telegram-bot", id="app-name")
            yield Label("Command and arguments · or use an existing service below")
            yield Input(self.command, placeholder="/usr/bin/python3 /srv/bot/main.py", id="app-command")
            with Horizontal(classes="form-row"):
                with Vertical():
                    yield Label("Linux user · root is supported")
                    yield Input(self.user, id="app-user")
                with Vertical():
                    yield Label("Working directory")
                    yield Input(self.cwd, id="app-cwd")
            yield Label("Existing systemd service (optional)")
            yield Input(self.service, placeholder="my-worker.service", id="app-service")
            yield Static("Registration saves a command. Assign a route to start it. Root workloads are trusted programs.", classes="hint")
            with Horizontal(classes="dialog-actions"):
                yield Button("Register", id="save-app", variant="primary")
                yield Button("Cancel", id="cancel-modal")

    @on(Button.Pressed)
    def button(self, event):
        event.stop()
        if event.button.id != "save-app":
            self.dismiss(None)
            return
        try:
            argv = shlex.split(self.query_one("#app-command", Input).value)
            service = self.query_one("#app-service", Input).value.strip() or None
            if service:
                argv = []
            if argv:
                executable = shutil.which(argv[0])
                if not executable:
                    raise ValueError("Executable not found")
                argv[0] = executable
            binding = AppBinding(self.query_one("#app-name", Input).value.strip(), argv,
                user=self.query_one("#app-user", Input).value.strip(),
                cwd=self.query_one("#app-cwd", Input).value.strip(), service=service)
            self.dismiss(binding)
        except (ValueError, OSError) as error:
            self.notify(str(error), severity="error")


class RouterView(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("APPLICATION → NETWORK", classes="eyebrow")
        yield Static("App router", classes="page-title")
        yield Static("Choose the route for a script, binary or service. Enter opens the profile selector.", classes="subtitle")
        with Horizontal(classes="toolbar"):
            yield Button("＋ Register", id="router-add", variant="primary")
            yield Button("↗ Change route", id="router-change")
            yield Button("Stop", id="router-stop")
            yield Button("Remove", id="router-remove", variant="error")
        yield DataTable(id="router-table", cursor_type="row", zebra_stripes=True)
        yield Static("Root is supported. SSH and host networking services are protected from adoption. Reassignment restarts the app.", classes="hint")

    def on_mount(self):
        self.query_one(DataTable).add_columns("Application / command", "User", "Assigned profile", "Mode", "Process")

    def selected(self):
        table = self.query_one(DataTable)
        if not table.row_count:
            self.notify("Register a workload first")
            return None
        key = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        return next((a for a in self.app.current_apps if a.id == key), None)

    def change(self):
        binding = self.selected()
        if binding:
            self.app.push_screen(RouteSelector(binding, self.app.data["profiles"]),
                lambda value: self.app.perform(lambda: self.app.runner.bind(binding.id, value['profile'], backup_profile_name=value['backup']),
                                              "Route/policy applied; failover restarts this workload") if value is not False else None)

    @on(DataTable.RowSelected, "#router-table")
    def row(self):
        self.change()

    @on(Button.Pressed)
    def button(self, event):
        event.stop()
        action = event.button.id
        if action == "router-add":
            self.app.open_app_form()
        elif action == "router-change":
            self.change()
        else:
            binding = self.selected()
            if binding:
                operation = self.app.runner.remove if action == "router-remove" else self.app.runner.stop
                self.app.perform(lambda: operation(binding.id), "Workload removed" if action == "router-remove" else "Workload stopped")

    def refresh_data(self, data):
        table = self.query_one(DataTable)
        cursor = table.cursor_row
        table.clear()
        names = {p["id"]: p["name"] for p in data["profiles"]}
        for a in data["apps"]:
            table.add_row(Text(a["name"] + " · " + a["command"]), Text(a["user"]),
                Text(names.get(a["profile_id"], "◌ Direct server")), "NETNS" if a["profile_id"] else "DIRECT",
                Text("RUNNING" if a["running"] else "STOPPED", style="green" if a["running"] else "bright_black"), key=a["id"])
        if table.row_count:
            table.move_cursor(row=min(cursor, table.row_count - 1))


class BrowseView(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("DISCOVER & REGISTER", classes="eyebrow")
        yield Static("Find your workload", classes="page-title")
        yield Static("Select a file, copy a process launch command, or adopt a systemd service.", classes="subtitle")
        with TabbedContent():
            with TabPane("Files", id="files-tab"):
                with Horizontal(classes="toolbar"):
                    yield Input("/srv", id="browse-path", placeholder="Directory path")
                    yield Button("Browse", id="browse-go")
                yield DirectoryTree("/srv" if Path("/srv").exists() else str(Path.home()), id="file-tree")
            with TabPane("Processes", id="processes-tab"):
                yield Button("Refresh processes", id="process-refresh")
                yield Static("Selecting copies a command; it does not migrate or stop the original process.", classes="hint")
                yield DataTable(id="process-table", cursor_type="row", zebra_stripes=True)
            with TabPane("Services", id="services-tab"):
                yield Button("Refresh services", id="service-refresh")
                yield DataTable(id="service-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self):
        self.query_one("#process-table", DataTable).add_columns("PID", "Name", "User", "Launch command")
        self.query_one("#service-table", DataTable).add_columns("Service", "State", "Description")
        self.processes = {}

    @on(DirectoryTree.FileSelected)
    def selected_file(self, event):
        path = event.path.resolve()
        argv = ([shutil.which("python3") or "/usr/bin/python3", str(path)] if path.suffix == ".py" else
                ["/bin/bash", str(path)] if path.suffix == ".sh" else [str(path)])
        self.app.open_app_form(shlex.join(argv), cwd=str(path.parent))

    @on(Button.Pressed)
    def button(self, event):
        event.stop()
        if event.button.id == "browse-go":
            path = Path(self.query_one("#browse-path", Input).value).expanduser()
            if not path.is_dir():
                self.notify("Directory does not exist", severity="error")
            else:
                self.query_one(DirectoryTree).path = path
        elif event.button.id == "process-refresh":
            table = self.query_one("#process-table", DataTable)
            table.clear()
            self.processes = {}
            for process in psutil.process_iter(["pid", "name", "username", "cmdline", "cwd"]):
                try:
                    info = process.info
                    if info["cmdline"]:
                        self.processes[str(info["pid"])] = info
                        table.add_row(str(info["pid"]), Text(info["name"] or ""), Text(info["username"] or ""),
                                      Text(shlex.join(info["cmdline"])[:160]), key=str(info["pid"]))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                if table.row_count >= 500:
                    break
        elif event.button.id == "service-refresh":
            self.app.load_services()

    @on(DataTable.RowSelected, "#process-table")
    def process(self, event):
        info = self.processes.get(str(event.row_key.value))
        if info:
            self.app.open_app_form(shlex.join(info["cmdline"]), user=info["username"] or "root", cwd=info["cwd"] or "/")

    @on(DataTable.RowSelected, "#service-table")
    def service(self, event):
        name = str(event.row_key.value)
        self.app.open_app_form(service=name)
