"""In-app walkthrough and a checklist backed by the existing verified installer."""
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Markdown, Static

from splitforge.core.dependencies import COMPONENTS, component_installed, component_plan


LESSONS = [
    (("Welcome to SplitForge", "A separate route for every app"),
     ("راهنمای SplitForge", "انتخاب مسیر اینترنت برای هر برنامه"),
     "Choose the cores you need, import a VPN profile, register a workload, then assign its route. "
     "Unregistered apps keep their current network. This guide only explains the controls; it does not change your server.",
     "ابتدا هسته‌های موردنیاز را نصب کنید، پروفایل را وارد کنید، برنامه را ثبت کنید و مسیرش را انتخاب کنید. "
     "برنامه‌های ثبت‌نشده روی شبکه قبلی می‌مانند. این راهنما تنظیمات سرور را تغییر نمی‌دهد."),
    (("1 · Install the required cores", "Core checklist · F2"),
     ("۱ · نصب هسته‌ها", "چک‌لیست هسته‌ها · F2"),
     "Open **Core checklist**. Tick WireGuard or OpenVPN for those profiles. Xray and tun2socks serve VLESS, "
     "VMess, REALITY, Trojan, Shadowsocks and SOCKS5. DNSTT/Slipstream automatically include those proxy helpers. "
     "Installed tools are detected and skipped. Downloads/builds run sequentially with results in Logs & Tools. "
     "DNSTT is built from pinned source and can take several minutes; binary downloads verify SHA-256.",
     "از **Core checklist** هسته‌های لازم را تیک بزنید. برای وایرگارد WireGuard و برای اوپن وی پی ان OpenVPN را انتخاب کنید. "
     "برای VLESS، VMess، REALITY، Trojan، Shadowsocks و SOCKS5 به Xray و tun2socks نیاز دارید. "
     "پیش‌نیازهای DNSTT و Slipstream خودکار اضافه می‌شوند. ابزارهای نصب‌شده دوباره دانلود نمی‌شوند. "
     "نتیجه و پیشرفت در Logs & Tools نمایش داده می‌شود. ساخت DNSTT ممکن است چند دقیقه طول بکشد."),
    (("2 · Import and test a profile", "VPN Profiles · 3 / N"),
     ("۲ · افزودن و تست پروفایل", "VPN Profiles · 3 / N"),
     "Open **VPN Profiles → Add profile**. Enter a name and a URI or a `.conf`, `.ovpn` or single-outbound `.json` path. "
     "DNSTT/Slipstream use the domain/resolver wizard and require a compatible remote server pointing to SOCKS5. "
     "Select **Start**, then **Test egress**. A saved profile is not yet a connection. Active lifecycle and last measured "
     "egress are different; timings include DNS and HTTPS, not ICMP ping.",
     "در **VPN Profiles → Add profile** نام و لینک یا مسیر فایل تنظیمات را وارد کنید. "
     "برای DNSTT و Slipstream دامنه، resolver و کلید یا گواهی لازم است؛ سرور سازگار با مقصد SOCKS5 باید از قبل آماده باشد. "
     "سپس **Start** و **Test egress** را بزنید. ذخیره کردن به معنی اتصال نیست. وضعیت Active با تست تازه خروجی تفاوت دارد."),
    (("3 · Register a script or service", "Add / Browse App · 4 / A"),
     ("۳ · ثبت اسکریپت یا سرویس", "Add / Browse App · 4 / A"),
     "Use the file tree or enter an executable command. For Python, choose your app's own venv interpreter. "
     "Set the Linux user (root is supported) and working directory. The process picker copies a command; it never "
     "moves a live process. Stop the original yourself if duplicate instances would conflict. Service registration "
     "must match its effective User=. SSH and host network services cannot be adopted.",
     "فایل را از مرورگر انتخاب کنید یا فرمان اجرا را بنویسید. برای پایتون از interpreter محیط خود برنامه استفاده کنید. "
     "کاربر لینوکس و پوشه کاری را مشخص کنید؛ root پشتیبانی می‌شود. انتخاب پردازش فقط فرمان را کپی می‌کند و پردازش جاری را منتقل نمی‌کند. "
     "برای جلوگیری از اجرای دو نمونه، نسخه قبلی را خودتان متوقف کنید. کاربر سرویس باید با User= آن برابر باشد. SSH قابل مسیریابی نیست."),
    (("4 · Assign or change the route", "App Router · 2 / C"),
     ("۴ · انتخاب یا تعویض مسیر", "App Router · 2 / C"),
     "Select an app, press Enter or **Change route**, choose a profile or **Direct server internet**, then apply. "
     "The managed workload STOPS and RESTARTS: open connections and process memory do not migrate. Registration "
     "alone does not start an app. Generated services continue after closing this UI. Use Stop to stop them deliberately.",
     "در **App Router** برنامه را انتخاب کنید، Enter یا **Change route** را بزنید و پروفایل یا Direct را انتخاب کنید. "
     "با Apply برنامه متوقف و دوباره اجرا می‌شود؛ اتصال‌های باز و حافظه قبلی حفظ نمی‌شوند. "
     "ثبت برنامه به‌تنهایی آن را اجرا نمی‌کند. بستن رابط سرویس را متوقف نمی‌کند؛ برای توقف از Stop استفاده کنید."),
    (("5 · Guards, logs and recovery", "Security · 5 / Logs · 6"),
     ("۵ · محافظت، لاگ و بازیابی", "Security · 5 / Logs · 6"),
     "Tunnel namespaces enforce the kill switch and encrypted DNS; IPv6 is disabled. Stop a profile before editing "
     "its DNS or source. Root workloads must be trusted; a network namespace is not a complete hostile-code sandbox. "
     "Read failures in **Logs & Tools**. After an upgrade, `sudo splitforge restore` reapplies saved enabled assignments. "
     "Never publish state files, private keys or subscription URIs.",
     "Kill Switch و DNS رمزگذاری‌شده برای پروفایل‌ها اجباری است و IPv6 داخل namespace غیرفعال است. "
     "برای تغییر DNS یا تنظیمات، ابتدا پروفایل را متوقف کنید. روی root فقط کد مورد اعتماد اجرا کنید؛ namespace یک sandbox کامل نیست. "
     "خطاها را در **Logs & Tools** ببینید. بعد از ارتقا، فرمان `sudo splitforge restore` نگاشت‌های فعال ذخیره‌شده را بازیابی می‌کند. "
     "state، کلید خصوصی و لینک اشتراک را عمومی نکنید."),
]


class GuideModal(ModalScreen):
    BINDINGS = [("escape", "close", "Close"), ("f2", "cores", "Core checklist")]

    def __init__(self):
        super().__init__()
        self.step = 0
        self.language = "en"

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog learning-dialog"):
            yield Static("QUICK START / آموزش", classes="dialog-title")
            with Horizontal(classes="guide-toolbar"):
                yield Static("", id="guide-step")
                yield Button("فارسی", id="guide-language")
            with VerticalScroll(id="guide-scroll"):
                yield Markdown(id="guide-content")
            with Horizontal(classes="dialog-actions"):
                yield Button("Back", id="guide-back")
                yield Button("Next", id="guide-next", variant="primary")
                yield Button("Core checklist", id="guide-cores")
                yield Button("Close", id="guide-close")

    def on_mount(self):
        self.render_lesson()

    def render_lesson(self):
        english, persian, body_en, body_fa = LESSONS[self.step]
        title, subtitle = persian if self.language == "fa" else english
        body = body_fa if self.language == "fa" else body_en
        self.query_one("#guide-step", Static).update(f"{self.step + 1} / {len(LESSONS)}")
        self.query_one(Markdown).update(f"# {title}\n\n### {subtitle}\n\n{body}")
        self.query_one("#guide-scroll", VerticalScroll).scroll_home(animate=False)
        self.query_one("#guide-back", Button).disabled = self.step == 0
        self.query_one("#guide-next", Button).disabled = self.step == len(LESSONS) - 1
        for key, en, fa in (("back", "Back", "قبلی"), ("next", "Next", "بعدی"),
                            ("cores", "Core checklist", "هسته‌ها"), ("close", "Close", "بستن")):
            self.query_one(f"#guide-{key}", Button).label = fa if self.language == "fa" else en
        self.query_one("#guide-language", Button).label = "English" if self.language == "fa" else "فارسی"

    @on(Button.Pressed)
    def button(self, event):
        event.stop()
        choice = event.button.id
        if choice == "guide-close":
            self.action_close()
        elif choice == "guide-cores":
            self.dismiss("cores")
        else:
            if choice == "guide-language":
                self.language = "fa" if self.language == "en" else "en"
            elif choice == "guide-back":
                self.step = max(0, self.step - 1)
            elif choice == "guide-next":
                self.step = min(len(LESSONS) - 1, self.step + 1)
            self.render_lesson()

    def action_close(self):
        self.dismiss(None)

    def action_cores(self):
        self.dismiss("cores")


class CoreChecklist(ModalScreen):
    BINDINGS = [("escape", "close", "Cancel")]

    def __init__(self, recommended=()):
        super().__init__()
        self.recommended = set(recommended)

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog learning-dialog"):
            yield Static("CORE CHECKLIST / انتخاب هسته‌ها", classes="dialog-title")
            yield Static("Tick what you need. Required helpers are included automatically; installed tools are skipped.\n"
                         "هسته‌ها را انتخاب کنید؛ پیش‌نیازها خودکار اضافه می‌شوند و موارد نصب‌شده رد می‌شوند.", classes="hint")
            with VerticalScroll(id="core-options"):
                for name, (_, description) in COMPONENTS.items():
                    installed = component_installed(name)
                    yield Checkbox(f"{name} · {'INSTALLED' if installed else 'MISSING'}", id="core-" + name,
                                   value=name in self.recommended and not installed)
                    yield Static(description, classes="core-description", markup=False)
            yield Static("", id="core-plan", markup=False)
            yield Static("Detection checks executable paths, not versions. Downloads/builds need root and network access. "
                         "DNSTT source builds can take several minutes. Profiles are not started by installation.", classes="hint")
            with Horizontal(classes="dialog-actions"):
                yield Button("Install selected / نصب", id="cores-install", variant="primary")
                yield Button("Cancel / بستن", id="cores-cancel")

    def on_mount(self):
        self.refresh_plan()

    def selected(self):
        return component_plan(box.id.removeprefix("core-") for box in self.query(Checkbox) if box.value)

    def refresh_plan(self):
        names = self.selected()
        self.query_one("#core-plan", Static).update("Plan / فهرست: " + (", ".join(names) if names else "—"))
        self.query_one("#cores-install", Button).disabled = not names

    @on(Checkbox.Changed)
    def changed(self, event):
        event.stop()
        self.refresh_plan()

    @on(Button.Pressed)
    def button(self, event):
        event.stop()
        self.dismiss(self.selected() if event.button.id == "cores-install" else None)

    def action_close(self):
        self.dismiss(None)
