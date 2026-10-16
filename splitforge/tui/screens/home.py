from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Static


def flag(country: str) -> str:
    return "".join(chr(127397 + ord(c)) for c in country) if len(country) == 2 and country.isalpha() else "◉"


def size(value: int) -> str:
    number = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if number < 1024 or unit == "TiB":
            return f"{number:.1f} {unit}"
        number /= 1024
    return "0 B"


class HomeView(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("YOUR NETWORK. YOUR RULES.", classes="eyebrow")
        yield Static("Command center", classes="page-title")
        yield Static("A separate route for every workload. Host traffic keeps its existing path.", classes="subtitle")
        with Horizontal(id="kpis"):
            yield Static("", id="kpi-tunnels", classes="kpi")
            yield Static("", id="kpi-apps", classes="kpi")
            yield Static("", id="kpi-traffic", classes="kpi")
            yield Static("", id="kpi-guard", classes="kpi")
        yield Static("◉ TUNNEL LIFECYCLE  ·  Test a profile for fresh egress health", classes="section-title")
        yield DataTable(id="health-table", cursor_type="row", zebra_stripes=True)
        yield Static("↗ APPLICATION ROUTES", classes="section-title")
        yield DataTable(id="overview-table", cursor_type="row", zebra_stripes=True)
        yield Static("Select App Router to assign or restart a workload. Profile counters are shared interface totals.", classes="hint")

    def on_mount(self):
        self.query_one("#health-table", DataTable).add_columns("Profile", "Protocol", "Lifecycle", "Last exit", "HTTPS elapsed")
        self.query_one("#overview-table", DataTable).add_columns("Application", "User", "Assigned route", "Process")

    def refresh_data(self, data):
        profiles, apps = data["profiles"], data["apps"]
        active = sum(p["active"] for p in profiles)
        traffic = sum(p.get("rx", 0) + p.get("tx", 0) for p in profiles)
        self.query_one("#kpi-tunnels", Static).update(f"[dim]ACTIVE PROFILES[/]\n[bold cyan]{active}[/] / {len(profiles)}")
        self.query_one("#kpi-apps", Static).update(f"[dim]RUNNING APPS[/]\n[bold magenta]{sum(a['running'] for a in apps)}[/] / {len(apps)}")
        self.query_one("#kpi-traffic", Static).update(f"[dim]INTERFACE TRAFFIC[/]\n[bold cyan]{size(traffic)}[/]")
        self.query_one("#kpi-guard", Static).update("[dim]TUNNEL POLICY[/]\n[bold green]DENY FALLBACK[/]")
        table = self.query_one("#health-table", DataTable)
        table.clear()
        for p in profiles:
            table.add_row(Text(f"{flag(p['country'])} {p['name']}"), Text(p["protocol"].upper()),
                Text("ACTIVE" if p["active"] else "STOPPED", style="green" if p["active"] else "bright_black"),
                Text(p["exit_ip"] or "—"), f"{p['latency_ms']:.0f} ms" if p["latency_ms"] is not None else "untested", key=p["id"])
        table = self.query_one("#overview-table", DataTable)
        table.clear()
        names = {p["id"]: p["name"] for p in profiles}
        for a in apps:
            table.add_row(Text(a["name"]), Text(a["user"]), Text(names.get(a["profile_id"], "◌ Direct server")),
                          Text("RUNNING" if a["running"] else "STOPPED", style="green" if a["running"] else "bright_black"), key=a["id"])
