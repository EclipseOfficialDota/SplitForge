from __future__ import annotations


from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Select, Static

from splitforge.tui.screens.home import flag


class ProfileForm(ModalScreen):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, profile=None):
        super().__init__()
        self.profile = profile

    def action_cancel(self):
        self.dismiss(None)

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("◇ Replace stopped profile" if self.profile else "◇ Add tunnel profile", classes="dialog-title")
            yield Label("Unique profile name")
            yield Input(self.profile.name if self.profile else "", placeholder="wg-europe", id="profile-name")
            yield Label("Import method")
            yield Select([("URI or configuration file", "import"), ("DNSTT wizard", "dnstt"),
                          ("Slipstream wizard", "slipstream")],
                          value=self.profile.protocol if self.profile and self.profile.protocol in {"dnstt", "slipstream"} else "import",
                          allow_blank=False, id="profile-method")
            yield Label("URI or file path · for DNS tunnels, enter the delegated domain")
            yield Input(self.profile.config.get("domain", "") if self.profile else "", placeholder="vless://… or /root/profiles/client.conf", id="profile-source", password=True)
            yield Label("DNS-tunnel resolver (only used by DNSTT / Slipstream)")
            yield Input(self.profile.config.get("resolver", "") if self.profile else "", placeholder="https://cloudflare-dns.com/dns-query or 1.1.1.1:53", id="profile-resolver")
            yield Label("DNSTT hex key/file / Slipstream PEM file · blank preserves an existing key")
            yield Input(placeholder="/root/profiles/server.pub", id="profile-key")
            yield Static("DNSTT and Slipstream require a remote SOCKS5 target and carry TCP. Imported profiles start only when requested.", classes="hint")
            with Horizontal(classes="dialog-actions"):
                yield Button("Save profile", id="save-profile", variant="primary")
                yield Button("Cancel", id="cancel-modal")

    @on(Button.Pressed)
    def button(self, event):
        event.stop()
        if event.button.id != "save-profile":
            self.dismiss(None)
            return
        values = {key: self.query_one(f"#profile-{key}", Input).value.strip() for key in ("name", "source", "resolver", "key")}
        values["method"] = str(self.query_one("#profile-method", Select).value)
        values["replace_id"] = self.profile.id if self.profile else None
        if not values["name"] or not values["source"]:
            self.notify("Name and source/domain are required", severity="error")
            return
        self.dismiss(values)


class ProfilesView(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("MULTIPLE TUNNELS. ONE CONTROL PLANE.", classes="eyebrow")
        yield Static("Tunnel profiles", classes="page-title")
        yield Static("Import an upstream. Start it. Test egress. Assign workloads from App Router.", classes="subtitle")
        with Horizontal(classes="toolbar"):
            yield Button("＋ Add profile", id="profile-add", variant="primary")
            yield Button("Edit source", id="profile-edit")
            yield Button("Start", id="profile-start")
            yield Button("Test egress", id="profile-test")
            yield Button("Stop", id="profile-stop", variant="warning")
            yield Button("Remove", id="profile-remove", variant="error")
        yield DataTable(id="profiles-table", cursor_type="row", zebra_stripes=True)
        yield Static("Stopping a profile also stops dependent workloads. HTTPS timings are not ICMP ping. Last measurements can be stale.", classes="hint")

    def on_mount(self):
        self.query_one(DataTable).add_columns("Profile", "Protocol", "Lifecycle", "Last exit", "HTTPS elapsed", "Namespace")

    def selected(self):
        table = self.query_one(DataTable)
        if not table.row_count:
            self.notify("Add a profile first")
            return None
        return str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)

    @on(Button.Pressed)
    def button(self, event):
        event.stop()
        if event.button.id == "profile-add":
            self.app.push_screen(ProfileForm(), self.app.save_profile_form)
            return
        profile_id = self.selected()
        if not profile_id:
            return
        if event.button.id == "profile-edit":
            profile = next(p for p in self.app.current_profiles if p.id == profile_id)
            self.app.push_screen(ProfileForm(profile), self.app.save_profile_form)
            return
        if event.button.id == "profile-start":
            operation = lambda: self.app.manager.start(profile_id)
        elif event.button.id == "profile-stop":
            operation = lambda: self.app.manager.stop(profile_id)
        elif event.button.id == "profile-test":
            def operation():
                profile = self.app.store.profile(profile_id)
                if not self.app.manager.netns.exists(profile):
                    self.app.manager.start(profile_id)
                return self.app.manager.test(profile_id)
        elif event.button.id == "profile-remove":
            operation = lambda: self.app.remove_profile(profile_id)
        else:
            return
        self.app.perform(operation, "Profile operation completed")

    def refresh_data(self, data):
        table = self.query_one(DataTable)
        cursor = table.cursor_row
        table.clear()
        for p in data["profiles"]:
            table.add_row(Text(f"{flag(p['country'])} {p['name']}"), p["protocol"].upper(),
                Text("ACTIVE" if p["active"] else "STOPPED", style="green" if p["active"] else "bright_black"),
                Text(p["exit_ip"] or "—"), f"{p['latency_ms']:.0f} ms" if p["latency_ms"] is not None else "untested",
                "ns-" + p["id"], key=p["id"])
        if table.row_count:
            table.move_cursor(row=min(cursor, table.row_count - 1))
