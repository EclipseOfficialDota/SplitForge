"use strict";
// Keep source text in the DOM's WeakMap, so switching language preserves drafts,
// selected files, focus, open dialogs and unmodified technical/user-supplied data.
(() => {
  const fa = {
    "SplitForge · Control plane": "SplitForge · پنل مدیریت",
    "⌘ splitforge — control plane": "⌘ splitforge — پنل مدیریت",
    "SECURE LOCAL SESSION": "نشست محلی امن",
    "YOUR NETWORK. YOUR RULES.": "شبکهٔ شما، قوانین شما.",
    "Welcome to": "خوش آمدید به",
    "A separate network path for every application.":
      "مسیر شبکهٔ جداگانه برای هر برنامه.",
    "One quiet place to control it all.":
      "همهٔ مسیرها را از یک جا مدیریت کنید.",
    "Administrator access token": "توکن دسترسی مدیر",
    "Paste your local access token": "توکن دسترسی محلی را وارد کنید",
    "Unlock control plane": "ورود به پنل مدیریت",
    "Token:": "توکن:",
    "Connect remotely through SSH port forwarding.":
      "برای اتصال از راه دور از انتقال پورت SSH استفاده کنید.",
    "CONTROL PLANE": "پنل مدیریت",
    "LOCAL SERVER": "سرور محلی",
    WORKSPACE: "محیط کار",
    Overview: "نمای کلی",
    "App router": "مسیریابی برنامه‌ها",
    "Tunnel profiles": "پروفایل‌های تونل",
    "Security & DNS": "امنیت و DNS",
    "Core installer": "نصب هسته‌ها",
    "Live logs": "گزارش زنده",
    "Quick start": "شروع سریع",
    "Main navigation": "ناوبری اصلی",
    "System resources": "منابع سیستم",
    Memory: "حافظه",
    "End web session": "خروج از پنل",
    "Toggle navigation": "باز و بسته کردن فهرست",
    "LIVE SESSION": "نشست فعال",
    "Refresh server state": "تازه‌سازی وضعیت سرور",
    "Connecting…": "در حال اتصال…",
    "IPv4 namespaces": "فضاهای شبکهٔ IPv4",
    "Encrypted DNS": "DNS رمزگذاری‌شده",
    "Close dialog": "بستن پنجره",
    "Download progress": "پیشرفت دانلود",
    "Your apps.": "برنامه‌های شما.",
    "Your network.": "شبکهٔ شما.",
    "Every workload, exactly where it belongs. Your host keeps its existing route.":
      "هر برنامه در مسیر انتخابی خودش؛ مسیر فعلی میزبان حفظ می‌شود.",
    "Register app": "ثبت برنامه",
    "Import profile": "افزودن پروفایل",
    "WORKSPACE / OVERVIEW": "محیط کار / نمای کلی",
    "ACTIVE TUNNELS": "تونل‌های فعال",
    "RUNNING APPS": "برنامه‌های در حال اجرا",
    "TUNNEL TRANSFER": "ترافیک تونل",
    "HOST MAIN ROUTE": "مسیر اصلی میزبان",
    "Shared interface RX + TX": "مجموع دریافت و ارسال رابط مشترک",
    Intact: "بدون تغییر",
    Changed: "تغییر کرده",
    "Compared to panel startup": "نسبت به زمان شروع پنل",
    "Tunnel health": "سلامت تونل‌ها",
    "LIFECYCLE + LAST EGRESS CHECK": "وضعیت سرویس و آخرین تست خروجی",
    "Manage tunnels": "مدیریت تونل‌ها",
    "TUNNEL PROFILE": "پروفایل تونل",
    PROTOCOL: "پروتکل",
    "LAST EXIT IP": "آخرین IP خروجی",
    "HTTPS ELAPSED": "زمان HTTPS",
    STATE: "وضعیت",
    "Not tested": "تست نشده",
    ONLINE: "روشن",
    STOPPED: "متوقف",
    "No tunnels yet": "هنوز تونلی ثبت نشده",
    "Import a provider profile to build your first isolated network.":
      "برای ساخت اولین شبکهٔ جداگانه، پروفایل سرویس‌دهنده را وارد کنید.",
    "HTTPS timings include DNS and retries. Test egress for a fresh measurement.":
      "زمان HTTPS شامل DNS و تلاش‌های مجدد است. برای اندازه‌گیری تازه، خروجی را تست کنید.",
    "Application routes": "مسیر برنامه‌ها",
    "Open app router": "باز کردن مسیریابی برنامه‌ها",
    "Route changes restart the managed application. Existing connections close.":
      "تغییر مسیر، برنامه را دوباره اجرا می‌کند و اتصال‌های قبلی بسته می‌شوند.",
    "APPLICATION / SCRIPT": "برنامه / اسکریپت",
    "ASSIGNED ROUTE": "مسیر انتخابی",
    USER: "کاربر",
    CONTROLS: "عملیات",
    RUNNING: "در حال اجرا",
    Stop: "توقف",
    Start: "شروع",
    "Test route": "تست مسیر",
    Remove: "حذف",
    "Direct server": "اینترنت مستقیم سرور",
    "Failover restarts this app":
      "تعویض خودکار تونل، برنامه را دوباره اجرا می‌کند",
    "No matching workloads": "برنامه‌ای پیدا نشد",
    "Register a script, executable or existing systemd service.":
      "اسکریپت، فایل اجرایی یا سرویس systemd موجود را ثبت کنید.",
    App: "مسیریابی",
    "router.": "برنامه‌ها.",
    "One application. One route. Pick the tunnel each workload uses.":
      "برای هر برنامه، مسیر و تونل مورد نظرش را انتخاب کنید.",
    "WORKSPACE / APP ROUTER": "محیط کار / مسیریابی برنامه‌ها",
    "Search apps, commands or users…": "جست‌وجوی برنامه، فرمان یا کاربر…",
    "Search applications": "جست‌وجوی برنامه‌ها",
    "Root workloads are supported with capabilities removed. Run trusted programs. A network namespace is not a complete filesystem sandbox.":
      "اجرای برنامه با root و حذف قابلیت‌های ویژه پشتیبانی می‌شود. فقط برنامهٔ معتبر اجرا کنید؛ فضای شبکه، محیط ایزولهٔ کامل فایل‌سیستم نیست.",
    Tunnel: "پروفایل‌های",
    "profiles.": "تونل.",
    "Multiple protocols. Separate namespaces. A single control plane.":
      "چند پروتکل، فضای شبکهٔ جداگانه و یک پنل مدیریت.",
    "WORKSPACE / TUNNELS": "محیط کار / تونل‌ها",
    "Search profiles or protocols…": "جست‌وجوی پروفایل یا پروتکل…",
    "Search profiles": "جست‌وجوی پروفایل‌ها",
    "Active does not mean freshly tested":
      "روشن بودن، جای تست تازهٔ اتصال را نمی‌گیرد",
    "Last exit address": "آخرین نشانی خروجی",
    "HTTPS elapsed": "زمان HTTPS",
    Received: "دریافت",
    Sent: "ارسال",
    "Test egress": "تست خروجی",
    "Edit source": "ویرایش پیکربندی",
    "No matching profiles": "پروفایلی پیدا نشد",
    "Import a URI or a server-side configuration file.":
      "لینک یا فایل تنظیمات موجود روی سرور را وارد کنید.",
    "Choose a profile…": "یک پروفایل انتخاب کنید…",
    Security: "امنیت",
    "& DNS.": "و DNS.",
    "Fail closed. Resolve privately. Keep the host's existing network path.":
      "قطع امن در خرابی، DNS خصوصی و حفظ مسیر فعلی میزبان.",
    "WORKSPACE / GUARDS": "محیط کار / محافظت",
    "Namespace policy": "قوانین فضای شبکه",
    ENFORCED: "اعمال‌شده",
    "Kill switch enabled": "قطع اضطراری فعال است",
    "Managed tunnel namespaces deny fallback through the host underlay.":
      "فضاهای شبکهٔ تونل اجازهٔ خروج جایگزین از اینترنت میزبان را نمی‌دهند.",
    "Verified DNS-over-HTTPS": "DNS روی HTTPS با اعتبارسنجی گواهی",
    "A local stub forwards resolver requests through the assigned tunnel.":
      "حل‌کنندهٔ محلی، درخواست‌های DNS را از تونل انتخاب‌شده عبور می‌دهد.",
    "IPv6 disabled in managed namespaces":
      "IPv6 در فضاهای مدیریت‌شده غیرفعال است",
    "This release uses an IPv4 data plane.":
      "این نسخه ترافیک را با IPv4 منتقل می‌کند.",
    "Shared profile, shared guard": "پروفایل مشترک، محافظت مشترک",
    "Apps in one namespace cannot disable its protection independently.":
      "برنامه‌های یک فضای شبکه نمی‌توانند محافظت آن را جداگانه غیرفعال کنند.",
    "Encrypted DNS settings": "تنظیمات DNS رمزگذاری‌شده",
    Profile: "پروفایل",
    "DNS-over-HTTPS URL": "نشانی DNS روی HTTPS",
    "Bootstrap IPv4": "IPv4 اولیهٔ حل‌کننده",
    "Must serve this hostname with a valid TLS certificate.":
      "این IP باید نام میزبان را با گواهی معتبر TLS پاسخ دهد.",
    "Stop the profile before editing DNS. Dependent workloads may stop with it.":
      "قبل از تغییر DNS پروفایل را متوقف کنید؛ برنامه‌های وابسته ممکن است متوقف شوند.",
    "Save encrypted DNS": "ذخیرهٔ DNS رمزگذاری‌شده",
    Your: "ابزارهای",
    "core toolkit.": "هستهٔ شما.",
    "Install only what your protocols need. Required helpers are included automatically.":
      "هسته‌های مورد نیازتان را نصب کنید؛ پیش‌نیازها خودکار اضافه می‌شوند.",
    "WORKSPACE / DEPENDENCIES": "محیط کار / پیش‌نیازها",
    "Linux network tools": "ابزارهای شبکهٔ لینوکس",
    "TUN bridge for proxy profiles": "پل TUN برای پروفایل‌های پراکسی",
    "WireGuard profiles": "پروفایل‌های WireGuard",
    "OpenVPN profiles": "پروفایل‌های OpenVPN",
    "DNSTT DNS tunnel": "تونل DNS با DNSTT",
    "Slipstream DNS tunnel": "تونل DNS با Slipstream",
    "Optional TCP wrapper": "واسط اختیاری TCP",
    "INSTALLED · WILL SKIP": "نصب‌شده · رد می‌شود",
    "NOT INSTALLED": "نصب نشده",
    "Binary downloads verify SHA-256. DNSTT builds from pinned source and can take several minutes. Installed tools are skipped; profiles are never started by installation.":
      "دانلود فایل‌ها با SHA-256 بررسی می‌شود. ساخت DNSTT از منبع ثابت ممکن است چند دقیقه طول بکشد. ابزارهای نصب‌شده رد می‌شوند و نصب، پروفایل‌ها را اجرا نمی‌کند.",
    "Select components to review the plan.":
      "برای مشاهدهٔ برنامهٔ نصب، هسته‌ها را انتخاب کنید.",
    "Install selected cores": "نصب هسته‌های انتخاب‌شده",
    The: "گزارش",
    "live feed.": "زنده.",
    "Follow SplitForge's systemd journal and recent control-plane operations.":
      "گزارش systemd و آخرین عملیات پنل SplitForge را دنبال کنید.",
    "WORKSPACE / LOGS": "محیط کار / گزارش‌ها",
    Follow: "دنبال کردن",
    Refresh: "تازه‌سازی",
    "Reading journal…": "در حال خواندن گزارش…",
    "No SplitForge journal entries yet.":
      "هنوز گزارشی برای SplitForge ثبت نشده است.",
    "Health & repair / بررسی و تعمیر": "بررسی و تعمیر",
    "Check health": "بررسی سلامت",
    "Check & repair": "بررسی و تعمیر",
    "Checks cores, DNS, tunnel guards, managed applications and web ports. Repair may restart managed workloads; open connections close. Host routing and SSH settings are never reset.":
      "هسته‌ها، DNS، محافظت تونل‌ها، برنامه‌ها و پورت وب بررسی می‌شوند. تعمیر ممکن است برنامه‌ها را دوباره اجرا کند و اتصال‌های باز بسته شوند. مسیر میزبان و تنظیمات SSH بازنشانی نمی‌شوند.",
    "Check / scope": "بررسی / محدوده",
    State: "وضعیت",
    "Finding / next step": "نتیجه / اقدام بعدی",
    OK: "سالم",
    ERROR: "خطا",
    WARNING: "هشدار",
    REPAIRED: "تعمیر شد",
    "Run a check to see actionable results. Checks do not install or restart anything unless repair is selected.":
      "برای دیدن نتیجه، بررسی را اجرا کنید. بررسی به‌تنهایی نصب یا راه‌اندازی مجدد انجام نمی‌دهد.",
    "A little": "راهنمای",
    "guidance.": "شروع.",
    "From your first profile to your first isolated workload.":
      "از اولین پروفایل تا اولین برنامه با مسیر مستقل.",
    "WORKSPACE / QUICK START": "محیط کار / شروع سریع",
    "READ-ONLY DEMO": "دموی فقط‌خواندنی",
    "LOCAL SESSION": "نشست محلی",
    "Demo · sample addresses": "دمو · نشانی‌های نمونه",
    "Connected to local control plane": "متصل به پنل مدیریت محلی",
    "Working…": "در حال انجام…",
    "Operation started. Results will appear in the control plane.":
      "عملیات شروع شد؛ نتیجه در پنل نمایش داده می‌شود.",
    Save: "ذخیره",
    Cancel: "انصراف",
    "Register a workload": "ثبت برنامه",
    "Application name": "نام برنامه",
    "Command and arguments": "فرمان و آرگومان‌ها",
    "Browse server files": "مرور فایل‌های سرور",
    "Linux user": "کاربر لینوکس",
    "Working directory": "پوشهٔ کاری",
    "Existing systemd service (optional)": "سرویس systemd موجود (اختیاری)",
    "Registration saves a command. Assign a route to start it. Existing services must match the selected user. SSH and host network services are protected.":
      "ثبت، فرمان را ذخیره می‌کند. برای اجرا مسیر انتخاب کنید. کاربر سرویس موجود باید با کاربر انتخابی یکی باشد. سرویس SSH و شبکهٔ میزبان محافظت می‌شوند.",
    "Register workload": "ثبت برنامه",
    "APPLICATIONS / NEW": "برنامه‌ها / جدید",
    "Replace stopped profile": "جایگزینی پروفایل متوقف‌شده",
    "Import a tunnel profile": "افزودن پروفایل تونل",
    "Profile name": "نام پروفایل",
    "Import method": "روش افزودن",
    "URI or server-side configuration file": "لینک یا فایل تنظیمات روی سرور",
    "DNSTT wizard": "راهنمای DNSTT",
    "Slipstream wizard": "راهنمای Slipstream",
    "URI or server-side file path": "لینک یا مسیر فایل روی سرور",
    "Secrets are not saved in your browser. Native imports: .conf / .ovpn / single-outbound .json":
      "اطلاعات محرمانه در مرورگر ذخیره نمی‌شوند. قالب‌ها: .conf / .ovpn / فایل .json با یک خروجی",
    "Delegated tunnel domain": "دامنهٔ واگذارشدهٔ تونل",
    Resolver: "حل‌کنندهٔ DNS",
    "DNSTT hex public key": "کلید عمومی DNSTT به‌صورت hex",
    "32-byte public key in hex": "کلید عمومی ۳۲ بایتی به‌صورت hex",
    "Slipstream server certificate path": "مسیر گواهی سرور Slipstream",
    "A compatible remote server targeting SOCKS5 is required. These DNS adapters carry TCP.":
      "سرور سازگار با مقصد SOCKS5 لازم است. این تونل‌های DNS ترافیک TCP منتقل می‌کنند.",
    "Save does not start a tunnel. Replacing a profile requires it to be stopped and preserves its application assignments.":
      "ذخیره، تونل را اجرا نمی‌کند. برای جایگزینی باید پروفایل متوقف باشد؛ مسیر برنامه‌های آن حفظ می‌شود.",
    "Save profile": "ذخیرهٔ پروفایل",
    "TUNNELS / CONFIGURATION": "تونل‌ها / تنظیمات",
    "Primary network path": "مسیر اصلی شبکه",
    "Direct server internet": "اینترنت مستقیم سرور",
    "Automatic backup tunnel (optional)": "تونل پشتیبان خودکار (اختیاری)",
    "Disabled · keep this single route": "غیرفعال · فقط همین مسیر",
    "Two failed health checks trigger a restart into the backup. If both fail, the app stays stopped. Direct is never an automatic fallback. A healthy backup is retained until you reapply the primary or the backup fails.":
      "پس از دو بررسی ناموفق، برنامه در تونل پشتیبان دوباره اجرا می‌شود. با خرابی هر دو، برنامه متوقف می‌ماند. اینترنت مستقیم هرگز جایگزین خودکار نیست. پشتیبان سالم تا انتخاب دوبارهٔ تونل اصلی یا خرابی خودش حفظ می‌شود.",
    "This stops and restarts the managed workload. Automatic failover also restarts it: open connections and process memory will be lost.":
      "این کار برنامه را متوقف و دوباره اجرا می‌کند. تعویض خودکار تونل نیز همین‌طور است؛ اتصال‌های باز و حافظهٔ فرایند از دست می‌روند.",
    "Kill switch and encrypted DNS remain enforced for tunnel assignments.":
      "قطع اضطراری و DNS رمزگذاری‌شده برای مسیرهای تونلی فعال می‌مانند.",
    "Apply & restart": "اعمال و اجرای مجدد",
    "APP ROUTER / REASSIGN": "مسیریابی برنامه / تغییر مسیر",
    Confirm: "تأیید",
    "Absolute server directory": "مسیر کامل پوشه روی سرور",
    Go: "باز کردن",
    "Parent directory": "پوشهٔ بالاتر",
    "Back to form": "بازگشت به فرم",
    "Choose a script or executable; this does not move a running process. Up to 200 entries are displayed.":
      "اسکریپت یا فایل اجرایی را انتخاب کنید؛ فرایند در حال اجرا منتقل نمی‌شود. حداکثر ۲۰۰ مورد نمایش داده می‌شود.",
    "Choose a provider .conf, .ovpn or .json file. Up to 200 entries are displayed.":
      "فایل .conf، .ovpn یا .json سرویس‌دهنده را انتخاب کنید. حداکثر ۲۰۰ مورد نمایش داده می‌شود.",
    "Remove application?": "برنامه حذف شود؟",
    "The managed service will stop and its SplitForge registration will be removed. Original scripts and existing service definitions are retained.":
      "سرویس متوقف و ثبت برنامه در SplitForge حذف می‌شود. فایل اصلی اسکریپت و تعریف اصلی سرویس باقی می‌مانند.",
    "Remove tunnel profile?": "پروفایل تونل حذف شود؟",
    "Remove all app and user references first. The profile and its owned network resources will be removed.":
      "ابتدا ارجاع همهٔ برنامه‌ها و کاربران را بردارید. پروفایل و منابع شبکهٔ متعلق به آن حذف می‌شوند.",
    "Stop tunnel profile?": "تونل متوقف شود؟",
    "Dependent workloads may stop with this profile. They will not fall back to Direct.":
      "برنامه‌های وابسته ممکن است متوقف شوند؛ به اینترنت مستقیم منتقل نمی‌شوند.",
    "Check & repair?": "بررسی و تعمیر اجرا شود؟",
    "Check & repair now": "شروع بررسی و تعمیر",
    "Repairs required cores and SplitForge-owned tunnel/DNS/guard resources. Enabled managed apps may restart and their open connections will close. Host routing, SSH and provider firewall settings are retained.":
      "هسته‌ها و منابع تونل، DNS و محافظت متعلق به SplitForge تعمیر می‌شوند. برنامه‌های فعال ممکن است دوباره اجرا شوند و اتصال‌هایشان بسته شود. مسیر میزبان، SSH و فایروال سرویس‌دهنده حفظ می‌شوند.",
    "Repairs required cores and SplitForge-owned tunnel/DNS/guard resources.":
      "هسته‌ها و منابع اختصاصی تونل، DNS و محافظت تعمیر می‌شوند.",
    "Explore read-only demo": "مشاهدهٔ دموی فقط‌خواندنی",
    "Sample addresses and measurements. No server changes or downloads.":
      "نشانی‌ها و اعداد نمونه‌اند؛ تغییری در سرور یا دانلودی انجام نمی‌شود.",
    "Sign in to continue": "برای ادامه وارد شوید",
    "Incorrect access token": "توکن دسترسی اشتباه است",
    "Too many sign-in attempts; wait one minute":
      "تلاش ورود بیش از حد است؛ یک دقیقه صبر کنید",
    "Too many active sessions; sign out or wait for expiry":
      "نشست‌های فعال زیاد است؛ خارج شوید یا منتظر انقضا بمانید",
    "Read-only demo: no server configuration was changed":
      "دموی فقط‌خواندنی است؛ تنظیمات سرور تغییر نکرد",
    "An operation is still running; wait for it to finish":
      "عملیاتی در حال اجراست؛ تا پایان آن صبر کنید",
    "Invalid CSRF token": "توکن امنیتی نشست معتبر نیست؛ دوباره وارد شوید",
    "Start the application before testing its actual route":
      "ابتدا برنامه را اجرا کنید و سپس مسیر واقعی آن را تست کنید",
    "Actual application namespace differs from its saved route; repair the assignment":
      "فضای شبکهٔ برنامه با مسیر ذخیره‌شده فرق دارد؛ مسیر را دوباره اعمال کنید",
    "Application HTTPS/DNS test failed in its actual namespaces; no host fallback was used":
      "تست HTTPS یا DNS در فضای واقعی برنامه ناموفق بود؛ از مسیر میزبان استفاده نشد",
    "Application stopped, restarted or changed route during the test; retry":
      "برنامه هنگام تست متوقف، دوباره اجرا یا جابه‌جا شد؛ دوباره تست کنید",
    "Route testing for chroot/RootDirectory services is not supported":
      "تست مسیر سرویس‌های chroot یا RootDirectory پشتیبانی نمی‌شود",
    "Application DNS differs from the isolated tunnel resolver":
      "DNS برنامه با حل‌کنندهٔ ایزولهٔ تونل متفاوت است",
    "Application has no running main process":
      "برنامه فرایند اصلی در حال اجرا ندارد",
    "Application restarted during route inspection; retry":
      "برنامه هنگام بررسی دوباره اجرا شد؛ دوباره تست کنید",
    "Application name already exists": "این نام برنامه قبلاً ثبت شده است",
    "Stop the profile before changing DNS":
      "قبل از تغییر DNS پروفایل را متوقف کنید",
    "Unknown action": "عملیات ناشناخته است",
    "Not found": "پیدا نشد",
    "Could not read server state; inspect the local server terminal":
      "خواندن وضعیت سرور ممکن نشد؛ ترمینال سرور را بررسی کنید",
    "Request failed; inspect the local server terminal":
      "درخواست ناموفق بود؛ ترمینال سرور را بررسی کنید",
    "Request exceeds 64 KiB or is empty":
      "درخواست خالی یا بزرگ‌تر از ۶۴ کیبی‌بایت است",
    "This operation requires Linux and root":
      "این عملیات به لینوکس و دسترسی root نیاز دارد",
    "This operation requires Linux and root access":
      "این عملیات به لینوکس و دسترسی root نیاز دارد",
    "This operation requires Linux and root privileges":
      "این عملیات به لینوکس و دسترسی root نیاز دارد",
    "Start the profile before testing": "ابتدا پروفایل را اجرا کنید",
    "Tunnel egress/DNS test failed; no host fallback was used":
      "تست خروجی یا DNS تونل ناموفق بود؛ از اینترنت میزبان استفاده نشد",
    "Choose two distinct tunnel profiles; Direct cannot be a failover target":
      "دو تونل متفاوت انتخاب کنید؛ اینترنت مستقیم مقصد پشتیبان نیست",
    overview: "نمای کلی",
    router: "مسیریابی",
    profiles: "پروفایل‌ها",
    security: "امنیت",
    cores: "هسته‌ها",
    logs: "گزارش‌ها",
    help: "راهنما",
    platform: "سیستم",
    core: "هسته",
    tunnel: "تونل",
    firewall: "فایروال",
    dns: "DNS",
    route: "مسیر",
    application: "برنامه",
    port: "پورت",
    certificate: "گواهی",
    "dns-egress": "DNS و خروجی",
    web: "وب",
    routing: "مسیریابی",
  };
  Object.assign(fa, {
    'Specify a traffic limit or an explicit disabled value': 'مقدار سقف مصرف یا غیرفعال‌سازی آن را صریحاً مشخص کنید',
    "COLLECTOR ACTIVE": "پایشگر فعال",
    "COLLECTOR STOPPED": "پایشگر متوقف",
    "Traffic budget usage": "میزان استفاده از سقف مصرف",
    "Traffic & quotas": "مصرف و سقف ترافیک",
    Traffic: "مصرف",
    "& budgets.": "و سقف مصرف.",
    "Each application has its own counter. Follow tunnel usage and set a budget.":
      "هر برنامه شمارندهٔ مستقل دارد. مصرف تونل‌ها را ببینید و سقف مصرف تعیین کنید.",
    "Enable collector": "فعال‌سازی پایش مصرف",
    "WORKSPACE / TRAFFIC": "محیط کار / مصرف ترافیک",
    "Budgets stop workloads at the next sample (normally every 5 seconds). Bursts can exceed the limit before stopping. App counters include local IP traffic; tunnel counters include shared DNS and protocol traffic.":
      "در نمونه‌برداری بعدی (معمولاً هر ۵ ثانیه) برنامه یا تونل متوقف می‌شود؛ ترافیک لحظه‌ای ممکن است پیش از توقف از سقف عبور کند. شمارندهٔ برنامه شامل ترافیک IP محلی و شمارندهٔ تونل شامل DNS و ترافیک مشترک پروتکل است.",
    "Application traffic": "مصرف برنامه‌ها",
    "Tunnel traffic": "مصرف تونل‌ها",
    "Budget alerts": "هشدارهای مصرف",
    "No budget alerts": "هشدار مصرفی ثبت نشده است",
    APPLICATION: "برنامه",
    TUNNEL: "تونل",
    "BUDGET BLOCKED": "متوقف با سقف مصرف",
    "COUNTERS LIVE": "شمارندهٔ زنده",
    "LAST READING": "آخرین اندازه‌گیری",
    "Independent service kernel counters": "شمارندهٔ مستقل کرنل برای این سرویس",
    "Shared tunnel interface counters": "شمارندهٔ رابط مشترک تونل",
    "No verified counter reading yet": "هنوز اندازه‌گیری معتبر دریافت نشده است",
    "Collecting rate history…": "در حال جمع‌آوری سابقهٔ سرعت…",
    "Receive and send rate history": "نمودار سرعت دریافت و ارسال",
    Received: "دریافت",
    Sent: "ارسال",
    "Budget usage": "مصرف دوره",
    Unlimited: "بدون سقف",
    "Traffic warning threshold reached": "مصرف به آستانهٔ هشدار رسیده است",
    "Set budget": "تنظیم سقف مصرف",
    "Traffic budget": "سقف مصرف ترافیک",
    "Limit in MiB (0 disables budget)": "سقف به مِبی‌بایت (صفر یعنی غیرفعال)",
    "Warning at percent": "درصد هشدار",
    "Reset usage period from now": "شروع دورهٔ مصرف از همین لحظه",
    "Changing routes or restarting does not reset usage. Resetting the period or increasing the limit permits a manual restart; it does not start a workload automatically.":
      "تغییر مسیر یا ری‌استارت مصرف را صفر نمی‌کند. با شروع دورهٔ جدید یا افزایش سقف، می‌توانید برنامه را دستی اجرا کنید؛ اجرای خودکار انجام نمی‌شود.",
    "Save budget": "ذخیرهٔ سقف مصرف",
    "Budget must be a valid nonnegative MiB amount":
      "مقدار سقف مصرف باید عدد معتبر و نامنفی به مِبی‌بایت باشد",
    "Traffic quota blocks this workload; reset its budget or increase the limit":
      "سقف مصرف جلوی اجرا را گرفته است؛ دوره را از نو شروع کنید یا سقف را افزایش دهید",
    "Traffic monitor is unavailable; quota-protected startup was blocked":
      "پایش مصرف در دسترس نیست؛ اجرای برنامهٔ دارای سقف مصرف مسدود شد",
    "Start this target and verify independent counters before setting a quota":
      "ابتدا برنامه یا تونل را اجرا کنید و شمارندهٔ مستقل آن را بررسی کنید؛ سپس سقف تعیین کنید",
    "Kernel/systemd independent IP accounting is unavailable":
      "شمارش مستقل IP در کرنل یا systemd این میزبان در دسترس نیست",
    "Reapply the app route to enable independent kernel IP accounting":
      "برای فعال‌سازی شمارندهٔ مستقل کرنل، مسیر برنامه را دوباره اعمال کنید",
    "Application is stopped; its last counter reading is retained":
      "برنامه متوقف است؛ آخرین اندازه‌گیری مصرف آن حفظ شده است",
    "Start the application to collect independent counters":
      "برای دریافت شمارندهٔ مستقل، برنامه را اجرا کنید",
    "Start the tunnel to collect interface counters":
      "برای دریافت شمارندهٔ رابط، تونل را اجرا کنید",
    "Restart this tunnel to enable persistent activation accounting":
      "برای شمارش پایدار مصرف، این تونل را دوباره اجرا کنید",
    "Tunnel interface accounting is unavailable":
      "شمارندهٔ رابط تونل در دسترس نیست",
    warning: "هشدار",
    blocked: "متوقف",
    quota: "سقف مصرف",
    "accounting unavailable": "شمارنده در دسترس نیست",
    "quota warning threshold": "آستانهٔ هشدار مصرف",
    "Request is empty or exceeds its allowed size":
      "درخواست خالی یا بزرگ‌تر از حجم مجاز است",
    "Encrypted backup & recovery": "پشتیبان رمزگذاری‌شده و بازیابی",
    "Export configuration": "خروجی گرفتن از تنظیمات",
    "Includes profiles, app routes, DNS, failover and web settings. Keep your password separately; it cannot be recovered.":
      "شامل پروفایل‌ها، مسیر برنامه‌ها، DNS، پشتیبان خودکار و تنظیمات وب است. رمز را جداگانه نگه دارید؛ قابل بازیابی نیست.",
    "Backup password (12+ characters)": "رمز پشتیبان (حداقل ۱۲ نویسه)",
    "Confirm password": "تکرار رمز",
    "Create encrypted backup": "ساخت پشتیبان رمزگذاری‌شده",
    "Restore configuration": "بازیابی تنظیمات",
    "Replaces current registrations and stops workloads. Imported commands remain stopped. Current web access is retained; use the CLI to apply saved web settings or restart trusted workloads.":
      "ثبت‌های فعلی جایگزین و برنامه‌ها متوقف می‌شوند. فرمان‌های واردشده اجرا نمی‌شوند. دسترسی فعلی وب حفظ می‌شود؛ برای اعمال تنظیمات وب ذخیره‌شده یا اجرای برنامه‌های معتبر از خط فرمان استفاده کنید.",
    "Encrypted .sfb file": "فایل رمزگذاری‌شدهٔ .sfb",
    "Backup password": "رمز پشتیبان",
    "I trust this backup and accept replacement of current registrations":
      "به این پشتیبان اعتماد دارم و جایگزینی ثبت‌های فعلی را می‌پذیرم",
    "Restore and keep workloads stopped": "بازیابی با حفظ توقف برنامه‌ها",
    "Version rollback: splitforge rollback --list / splitforge rollback --backup ID. Updates retain a private installation snapshot on the server.":
      "بازگشت نسخه: splitforge rollback --list / splitforge rollback --backup ID. قبل از به‌روزرسانی، نسخهٔ خصوصی نصب روی سرور نگه‌داری می‌شود.",
    "Download encrypted backup": "دانلود پشتیبان رمزگذاری‌شده",
    "Backup passwords do not match": "رمز و تکرار آن یکسان نیستند",
    "Backup file must be smaller than 16 MiB":
      "حجم فایل پشتیبان باید کمتر از ۱۶ مِبی‌بایت باشد",
    "Backup download expired; export a new backup":
      "مهلت دریافت پشتیبان تمام شده است؛ خروجی جدید بسازید",
    "Incorrect backup password or damaged backup; nothing was restored":
      "رمز اشتباه است یا فایل پشتیبان آسیب دیده؛ چیزی بازیابی نشد",
    "Backup password must contain 12–1024 UTF-8 bytes":
      "رمز پشتیبان باید بین ۱۲ تا ۱۰۲۴ بایت UTF-8 باشد",
    "Confirm replacement of current registrations before restoring":
      "قبل از بازیابی، جایگزینی ثبت‌های فعلی را تأیید کنید",
    connecting: "در حال برقراری اتصال",
    retry: "تلاش مجدد",
    "verified cache": "فایل معتبر از کش خوانده شد",
    "verifying SHA-256": "در حال بررسی SHA-256",
    "verified; cache unavailable": "صحت فایل تأیید شد؛ کش در دسترس نیست",
    "building pinned source": "در حال ساخت از منبع ثابت و تأییدشده",
    "Operation completed.": "عملیات انجام شد.",
    downloading: "در حال دانلود",
    verified: "صحت فایل تأیید شد",
    cached: "فایل معتبر از کش خوانده شد",
    retrying: "تلاش مجدد",
    building: "در حال ساخت",
    installing: "در حال نصب",
    "Technical details": "جزئیات فنی",
    "Check whether systemd is PID 1.":
      "بررسی اجرای systemd به‌عنوان فرایند شمارهٔ ۱.",
    "Use a VPS/VM with systemd enabled.":
      "از سرور مجازی با systemd فعال استفاده کنید.",
    "Check the kernel TUN device.": "بررسی دستگاه TUN کرنل.",
    "Ask the VPS provider to enable /dev/net/tun; load the tun module when supported.":
      "از سرویس‌دهنده بخواهید /dev/net/tun را فعال کند؛ در صورت امکان ماژول tun را بارگذاری کنید.",
    "Required component is installed.": "هستهٔ لازم نصب شده است.",
    "Required component is missing.": "هستهٔ لازم نصب نشده است.",
    "Intentionally stopped; no repair was attempted.":
      "پروفایل عمداً متوقف است؛ تعمیری انجام نشد.",
    "Tunnel lifecycle and namespace checks passed.":
      "بررسی سرویس تونل و فضای شبکه موفق بود.",
    "Tunnel is unavailable or its isolated network configuration is inconsistent.":
      "تونل در دسترس نیست یا تنظیمات فضای شبکهٔ آن ناسازگار است.",
    "Check required cores/provider configuration; use repair to rebuild only this managed tunnel.":
      "هسته‌ها و تنظیمات سرویس‌دهنده را بررسی کنید؛ تعمیر فقط همین تونل مدیریت‌شده را بازسازی می‌کند.",
    "Managed namespace configuration passed.":
      "تنظیمات فضای شبکهٔ مدیریت‌شده سالم است.",
    "Namespace/host guard is missing or allows an unexpected path.":
      "محافظت فضای شبکه یا میزبان وجود ندارد یا مسیر غیرمجاز را باز گذاشته است.",
    "Namespace DNS files do not enforce the local encrypted-DNS stub.":
      "فایل‌های DNS فضای شبکه، حل‌کنندهٔ محلی رمزگذاری‌شده را الزام نمی‌کنند.",
    "Namespace default route does not exclusively use its tunnel interface.":
      "مسیر پیش‌فرض فضای شبکه منحصراً از رابط تونل استفاده نمی‌کند.",
    "Repair rebuilds this managed namespace and restarts its enabled applications.":
      "تعمیر، همین فضای شبکه را بازسازی و برنامه‌های فعال آن را دوباره اجرا می‌کند.",
    "Namespace DNS/HTTPS egress probe failed; no Direct fallback used.":
      "تست خروجی DNS یا HTTPS فضای شبکه ناموفق بود؛ از اینترنت مستقیم استفاده نشد.",
    "Check provider reachability, DNS-over-HTTPS/bootstrap settings, remote credentials and MTU.":
      "دسترسی به سرویس‌دهنده، DNS روی HTTPS، IP اولیه، مشخصات ورود و MTU را بررسی کنید.",
    "Inspect Live logs and provider configuration. SSH and host routing were not repaired or reset.":
      "گزارش زنده و تنظیمات سرویس‌دهنده را بررسی کنید. SSH و مسیریابی میزبان تغییر نکرده‌اند.",
    "Workload repair is blocked until its assigned tunnel is healthy.":
      "تعمیر برنامه تا سالم شدن تونل انتخابی آن متوقف است.",
    "Repair the tunnel first; the assignment is retained and Direct is never selected automatically.":
      "ابتدا تونل را تعمیر کنید؛ مسیر ذخیره‌شده حفظ می‌شود و اینترنت مستقیم خودکار انتخاب نمی‌شود.",
    "Enabled workload is running.": "برنامهٔ فعال در حال اجراست.",
    "Enabled workload is stopped.": "برنامهٔ فعال متوقف است.",
    "Inspect the application journal, executable path, Linux user and working directory.":
      "گزارش برنامه، مسیر فایل اجرایی، کاربر لینوکس و پوشهٔ کاری را بررسی کنید.",
    "Inspect its systemd journal.": "گزارش systemd آن را بررسی کنید.",
    "Check host DNS resolution.": "بررسی حل نام DNS میزبان.",
    "Inspect resolvectl status / host resolver settings; repair does not replace host DNS.":
      "خروجی resolvectl status و تنظیمات DNS میزبان را بررسی کنید؛ تعمیر DNS میزبان را جایگزین نمی‌کند.",
    "Host resolver timed out.": "مهلت پاسخ DNS میزبان تمام شد.",
    "Inspect host resolver settings and outbound DNS connectivity.":
      "تنظیمات حل‌کنندهٔ میزبان و اتصال خروجی DNS را بررسی کنید.",
    "Check configured web listener.": "بررسی پورت شنوندهٔ وب.",
    "Inspect splitforge-web/nginx journal and rerun splitforge web setup; this worker cannot restart itself.":
      "گزارش splitforge-web و nginx را بررسی و splitforge web setup را دوباره اجرا کنید؛ این عملیات سرویس خودش را ری‌استارت نمی‌کند.",
    "Check certificate renewal timer.": "بررسی زمان‌بندی تمدید گواهی.",
    "Rerun web setup to restore renewal scheduling.":
      "برای بازیابی زمان‌بندی تمدید، راه‌اندازی وب را دوباره اجرا کنید.",
    "No setup-managed web configuration; current backend remains reachable.":
      "تنظیمات وبِ ساخته‌شده با راه‌انداز وجود ندارد؛ سرویس فعلی پاسخ‌گوست.",
    "Run splitforge web setup for public listener and certificate diagnostics.":
      "برای تنظیم دسترسی عمومی و بررسی گواهی، splitforge web setup را اجرا کنید.",
    "UFW active; inspect allow rules for public ports.":
      "فایروال UFW فعال است؛ مجوز پورت‌های عمومی را بررسی کنید.",
    "UFW inactive; other host/provider policies may apply.":
      "فایروال UFW غیرفعال است؛ ممکن است قوانین دیگری در میزبان یا سرویس‌دهنده فعال باشند.",
    "External/cloud firewall reachability requires an independent public connection.":
      "بررسی فایروال ابری یا خارجی به اتصال مستقل از اینترنت نیاز دارد.",
    "Allow the configured panel port and HTTP-01 port 80 at the provider; host checks cannot prove provider rules.":
      "پورت پنل و پورت ۸۰ برای HTTP-01 را در فایروال سرویس‌دهنده باز کنید؛ بررسی میزبان، قوانین سرویس‌دهنده را تأیید نمی‌کند.",
    "Inspect nginx configuration and web setup output.":
      "تنظیمات nginx و خروجی راه‌اندازی وب را بررسی کنید.",
    "Compare the host main route with the panel startup baseline.":
      "مقایسهٔ مسیر اصلی میزبان با زمان شروع پنل.",
    "Inspect changes by other network tools; repair deliberately does not reset host routes.":
      "تغییرات سایر ابزارهای شبکه را بررسی کنید؛ تعمیر مسیرهای میزبان را بازنشانی نمی‌کند.",
  });
  const patterns = [
    [/^Peak (.+)\/s$/, (_, amount) => `بیشترین سرعت ${amount} در ثانیه`],
    [
      /^Last sampled (.+)$/,
      (_, timestamp) => `آخرین نمونه‌برداری ${timestamp}`,
    ],
    [
      /^◌ (.+) · (.+)$/,
      (_, action, status) => `◌ ${action} · ${lookup(status)}`,
    ],
    [
      /^Fresh namespace HTTPS\/DNS probe passed; exit (.+)\.$/,
      (_, ip) => `تست تازهٔ HTTPS و DNS فضای شبکه موفق بود؛ خروجی ${ip}.`,
    ],
    [
      /^Use Core installer to install (.+); inspect its individual download result\.$/,
      (_, name) =>
        `از نصب هسته‌ها برای نصب ${name} استفاده کنید؛ نتیجهٔ دانلود آن را بررسی کنید.`,
    ],
    [
      /^(Check\/repair failed|Workload check failed|Web configuration check failed): (.+)$/,
      (_, category, error) => `بررسی یا تعمیر ناموفق بود: ${errorText(error)}`,
    ],
    [
      /^(\d+) stopped · lifecycle status$/,
      (_, n) => `${n} متوقف · وضعیت سرویس`,
    ],
    [/^(\d+) assigned to a tunnel$/, (_, n) => `${n} برنامه متصل به تونل`],
    [/^(\d+) registered workloads$/, (_, n) => `${n} برنامهٔ ثبت‌شده`],
    [/^Updated (.+)$/, (_, time) => `آخرین به‌روزرسانی ${time}`],
    [/^v([\d.]+) \/ CONTROL PLANE$/, (_, v) => `v${v} / پنل مدیریت`],
    [/^Assign route · (.+)$/, (_, name) => `انتخاب مسیر · ${name}`],
    [/^Plan: (.+)$/, (_, names) => `برنامهٔ نصب: ${names}`],
    [/^Auto: (.+)$/, (_, names) => `پشتیبان خودکار: ${names}`],
    [
      /^(.*) · (active|stopped|auto start)$/,
      (_, name, status) =>
        `${name} · ${{ active: "روشن", stopped: "متوقف", "auto start": "شروع خودکار" }[status]}`,
    ],
    [
      /^(\d+) errors · (\d+) warnings · (.+)$/,
      (_, errors, warnings, time) =>
        `${errors} خطا · ${warnings} هشدار · ${time}`,
    ],
    [
      /^Last process-route test: (.+)$/,
      (_, time) => `آخرین تست مسیر فرایند: ${time}`,
    ],
    [/^IP (.+) · DNS (.+)$/, (_, ip, dns) => `IP خروجی ${ip} · DNS ${dns}`],
    [
      /^HTTPS connected · PID (\d+) · (.+) ms$/,
      (_, pid, ms) => `HTTPS متصل · فرایند ${pid} · ${ms} میلی‌ثانیه`,
    ],
    [/^Route at test: (.+)$/, (_, name) => `مسیر هنگام تست: ${name}`],
    [
      /^Connection issue: (.+)\. Retrying…$/,
      (_, message) => `اشکال در اتصال: ${errorText(message)}؛ تلاش مجدد…`,
    ],
    [/^(.+) completed$/, (_, action) => `عملیات ${action} انجام شد`],
    [
      /^([\w.-]+) · (RUNNING|SUCCESS|FAILED)$/,
      (_, action, status) =>
        `${action} · ${{ RUNNING: "در حال اجرا", SUCCESS: "موفق", FAILED: "ناموفق" }[status]}`,
    ],
    [/^Invalid (.+)$/, (_, field) => `مقدار ${field} معتبر نیست`],
    [/^Choose (.+)$/, (_, field) => `مقدار لازم را انتخاب کنید: ${field}`],
  ];
  let language = "en";
  try {
    language =
      localStorage.getItem("splitforge.language") === "fa" ? "fa" : "en";
  } catch {}
  const originals = new WeakMap();
  const normalize = (text) => text.replace(/\s+/g, " ").trim();
  function lookup(text) {
    const key = normalize(text);
    if (Object.hasOwn(fa, key)) return fa[key];
    for (const [pattern, replacement] of patterns)
      if (pattern.test(key)) return key.replace(pattern, replacement);
    const leading = key.match(/^([^\p{L}\p{N}]+)(.+)$/u);
    if (leading && Object.hasOwn(fa, leading[2]))
      return leading[1] + fa[leading[2]];
    const parts = key.match(/^([^\p{L}\p{N}]*)(.*?)([^\p{L}\p{N}]*)$/u);
    if (parts && Object.hasOwn(fa, parts[2]))
      return parts[1] + fa[parts[2]] + parts[3];
    return text;
  }
  function errorText(text) {
    if (/[\u0600-\u06ff]/.test(text)) return text;
    const translated = lookup(text);
    if (translated !== text) return translated;
    if (/fetch|connect|timeout|timed out|network/i.test(text))
      return "ارتباط برقرار نشد؛ اتصال سرور، تونل و DNS را بررسی کنید";
    if (/permission|denied|root|protected/i.test(text))
      return "دسترسی مجاز نیست؛ کاربر، مجوزها و سرویس‌های محافظت‌شده را بررسی کنید";
    if (/checksum|SHA-256|digest|corrupt/i.test(text))
      return "بررسی صحت فایل ناموفق بود؛ فایل استفاده نشد. منبع یا کش را بررسی کنید";
    if (/download|HTTP|install/i.test(text))
      return "دریافت یا نصب هسته ناموفق بود؛ منبع دانلود، اتصال و جزئیات فنی عملیات را بررسی کنید";
    if (/profile|tunnel|namespace/i.test(text))
      return "عملیات تونل انجام نشد؛ پروفایل، وضعیت تونل و گزارش فنی را بررسی کنید";
    if (/invalid|validation|expected|required|must|unsupported/i.test(text))
      return "دادهٔ واردشده معتبر یا پشتیبانی‌شده نیست؛ مقادیر فرم و جزئیات فنی را بررسی کنید";
    return "عملیات انجام نشد؛ جزئیات فنی و گزارش سرور را بررسی کنید";
  }
  function change(node, key, read, write, isError = false) {
    const value = read();
    const saved = originals.get(node) || {};
    if (!saved[key] || value !== saved[key].translated)
      saved[key] = { source: value };
    const source = saved[key].source;
    let translated =
      language === "fa"
        ? isError && source.trim()
          ? errorText(source)
          : lookup(source)
        : source;
    if (translated !== source)
      translated =
        (source.match(/^\s*/)?.[0] || "") +
        translated.trim() +
        (source.match(/\s*$/)?.[0] || "");
    saved[key].translated = translated;
    originals.set(node, saved);
    if (value !== translated) write(translated);
  }
  const observer = new MutationObserver(() => apply());
  function apply() {
    observer.disconnect();
    document.documentElement.lang = language;
    document.documentElement.dir = language === "fa" ? "rtl" : "ltr";
    const title = document.querySelector("title");
    change(
      title,
      "text",
      () => title.textContent,
      (value) => {
        title.textContent = value;
      },
    );
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
    );
    while (walker.nextNode()) {
      const node = walker.currentNode,
        parent = node.parentElement;
      if (
        !parent ||
        parent.closest(
          "script,style,code,pre,[data-no-translate],.identity strong,.identity small,.profile-card h2,.component strong,.mono.muted,#host-label,#workspace-host",
        )
      )
        continue;
      const entry = parent.closest(".file-entry");
      if (entry && entry.previousElementSibling) continue;
      change(
        node,
        "text",
        () => node.nodeValue,
        (value) => {
          node.nodeValue = value;
        },
        !!parent.closest(
          "#login-error,#form-error,.error-text,.toast.error,.operation.failed p",
        ),
      );
    }
    for (const node of document.querySelectorAll(
      "[placeholder],[aria-label],[title]",
    )) {
      for (const attribute of ["placeholder", "aria-label", "title"])
        if (node.hasAttribute(attribute))
          change(
            node,
            attribute,
            () => node.getAttribute(attribute),
            (value) => node.setAttribute(attribute, value),
          );
    }
    for (const button of document.querySelectorAll("[data-language-toggle]")) {
      button.textContent = language === "fa" ? "English" : "فارسی";
      button.setAttribute(
        "aria-label",
        language === "fa" ? "Switch to English" : "تغییر به فارسی",
      );
    }
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "aria-label", "title"],
    });
  }
  function set(value) {
    language = value === "fa" ? "fa" : "en";
    try {
      localStorage.setItem("splitforge.language", language);
    } catch {}
    for (const input of document.querySelectorAll("input,select,textarea"))
      input.setCustomValidity("");
    apply();
    document.dispatchEvent(
      new CustomEvent("splitforge-language", { detail: language }),
    );
  }
  window.SplitForgeLocale = {
    get language() {
      return language;
    },
    set,
    apply,
    lookup,
    errorText,
  };
  document.addEventListener(
    "invalid",
    (event) => {
      if (language === "fa")
        event.target.setCustomValidity(
          "این مقدار را کامل و با قالب معتبر وارد کنید.",
        );
    },
    true,
  );
  document.addEventListener("input", (event) => {
    if (event.target.setCustomValidity) event.target.setCustomValidity("");
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-language-toggle]"))
      set(language === "fa" ? "en" : "fa");
  });
  apply();
})();
