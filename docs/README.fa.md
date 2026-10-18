<div align="center">

# ⚡ SplitForge

[![English](assets/language-en.svg)](../README.md)
[![فارسی](assets/language-fa.svg)](README.fa.md)

**مستندات فارسی** · برای تغییر زبان، روی دکمهٔ **English** کلیک کنید.

### مسیر اینترنت هر برنامه را جداگانه انتخاب کنید.

[![License: MIT](https://img.shields.io/badge/License-MIT-34d399.svg)](../LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-38bdf8.svg)](../pyproject.toml)
[![CI](https://github.com/EclipseOfficialDota/SplitForge/actions/workflows/ci.yml/badge.svg)](https://github.com/EclipseOfficialDota/SplitForge/actions/workflows/ci.yml)

</div>

<div dir="rtl" align="right">

# راهنمای کامل فارسی

[صفحهٔ اصلی](../README.md) · [آموزش انگلیسی](GETTING_STARTED.md) · [پروتکل‌ها](PROTOCOLS.md) · [عیب‌یابی](TROUBLESHOOTING.md)

## برنامه چه کار می‌کند؟

با SplitForge برای هر برنامه، اسکریپت یا سرویس ثبت‌شده یک مسیر اینترنت انتخاب
می‌کنید؛ مثلاً ربات با WireGuard، اسکرپر با VLESS و بکاپ با اینترنت مستقیم سرور.
برنامه‌هایی که ثبت نکرده‌اید روی شبکهٔ قبلی می‌مانند. برای هر پروفایل فعال یک
network namespace ساخته می‌شود. تغییر مسیر، برنامهٔ مدیریت‌شده را متوقف و دوباره
اجرا می‌کند؛ اتصال TCP و حافظهٔ پردازش قبلی حفظ نمی‌شوند.

نسخهٔ فعلی رابط شش‌صفحه‌ای Textual، CLI، نصب‌کننده، نگهداری وضعیت خصوصی، مدیریت
systemd، DNS رمزگذاری‌شده و اجرای برنامه با **root یا کاربر عادی** دارد.
آداپتورهای VLESS/REALITY، VMess، Trojan، Shadowsocks، SOCKS5، WireGuard، OpenVPN،
DNSTT و Slipstream پیاده شده‌اند. وجود آداپتور به معنی آزمایش با تمام سرویس‌دهنده‌ها
نیست؛ [گزارش دقیق آزمون‌ها](VALIDATION.md) این تفاوت را مشخص می‌کند.

## پیش‌نیاز و نصب

Ubuntu/Debian با Python 3.10 یا جدیدتر، systemd به‌عنوان PID 1، دسترسی root،
`/dev/net/tun` و امکان ساخت namespace لازم است. ویندوز و macOS به‌صورت بومی
موتور شبکه را اجرا نمی‌کنند. تست واقعی این پروژه روی Ubuntu 24.04 داخل WSL2 با
systemd انجام شده است. کانتینر یا VPS محدود ممکن است حتی با root اجازهٔ TUN ندهد.
Ubuntu 22.04/24.04 و Debian 12/13 هدف نصب هستند؛ آزمایش همهٔ آن‌ها ادعا نشده است.

<div dir="ltr" align="left">

```sh
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/EclipseOfficialDota/SplitForge.git
cd SplitForge
sudo bash install.sh
sudo splitforge doctor
```

</div>

نصب‌کننده ابزارهای سیستم، محیط مستقل `/opt/splitforge/venv`، وابستگی‌های پایتون
با نسخه‌های محدودشده در `requirements.lock` و Xray/tun2socks با بررسی SHA-256 نصب
می‌کند. فرمان `/usr/local/bin/splitforge` به محیط نصب متصل می‌شود. کد و مسیر نصب
باید در اختیار مدیر سرور باشند. کلید VPN یا سرور رایگان همراه پروژه نیست.

<div dir="ltr" align="left">

```sh
sudo splitforge
splitforge --demo
splitforge --help
```

</div>

حالت demo بدون root و بدون تغییر شبکه/ذخیرهٔ وضعیت است؛ آدرس‌ها و اعدادش نمونه‌اند.
برای نصب بدون دریافت هسته‌های پروکسی از `--skip-proxy-cores` استفاده کنید؛ پیش از
اجرای پروفایل پروکسی باید خودتان آن‌ها را نصب کنید. مسیر نصب با `--prefix` قابل
تغییر است. رنج `10.203.0.0/18` و جدول‌ها/اولویت‌های اختصاصی را با شبکهٔ موجود
سرور تداخل ندهید؛ جزئیات در [معماری](ARCHITECTURE.md).

## کار با رابط ترمینال

| بخش | کاربرد |
| --- | --- |
| Home | تعداد تونل و برنامه، پهنای‌باند مشترک، وضعیت سرویس و آخرین تست خروجی |
| App Router | انتخاب برنامه و تغییر مسیر به Direct یا پروفایل |
| VPN Profiles | افزودن، جایگزینی تنظیمات پروفایل خاموش، شروع، توقف، تست و حذف |
| Add / Browse | مرور فایل، انتخاب فرمان از پردازش موجود یا انتخاب سرویس |
| Security & DNS | محافظ namespace و تنظیم DNS-over-HTTPS هر پروفایل |
| Logs & Tools | لاگ زندهٔ systemd و نصب وابستگی‌ها |

کلیدهای ۱ تا ۶ صفحه را عوض می‌کنند؛ Tab و جهت‌ها و Enter برای پیمایش، A افزودن
برنامه، N پروفایل جدید، C انتخاب مسیر، T تست پروفایل‌های فعال، R نوسازی و Q خروج.
Escape پنجره را می‌بندد. کلیک ماوس نیز کار می‌کند. اندازهٔ ۱۲۰×۴۰ یا بزرگ‌تر بهتر
است. بستن رابط سرویس‌ها را متوقف نمی‌کند. هنگام عملیات جاری صبر کنید تا تمام شود.

### آموزش پاپ‌آپی و نصب انتخابی هسته‌ها

از منوی کناری **Quick start** یا کلید **F1** راهنمای پاپ‌آپی را باز کنید. با دکمهٔ
**فارسی** زبان را تغییر دهید و با قبلی/بعدی مراحل نصب هسته، وارد کردن پروفایل،
ثبت اسکریپت یا سرویس، تغییر مسیر، محافظت و بازیابی را بخوانید. راهنما هیچ تغییری
روی شبکه یا تنظیمات اعمال نمی‌کند و با Escape بسته می‌شود.

کلید **F2** یا **Core checklist** در منوی کناری و Logs & Tools، چک‌لیست هسته‌ها
را باز می‌کند. موارد لازم را تیک بزنید، فهرست نهایی را ببینید و **Install selected**
را بزنید. پیش‌نیازهای Xray و tun2socks برای تونل‌های DNS خودکار اضافه می‌شوند.
هسته‌های نصب‌شده مشخص می‌شوند و دوباره دانلود نمی‌شوند. پیشنهاد اولیه بر اساس
پروفایل‌های موجود است؛ بدون پروفایل، Xray و tun2socks پیشنهاد می‌شوند.

نصب‌ها به‌ترتیب انجام می‌شوند و پیشرفت و نتیجهٔ هر مورد در Logs & Tools دیده
می‌شود. شکست یک دانلود نصب‌های موفق را حذف نمی‌کند و بقیهٔ انتخاب‌ها امتحان
می‌شوند؛ برای تلاش مجدد چک‌لیست را باز کنید. ساخت DNSTT ممکن است چند دقیقه طول
بکشد. تشخیص نصب‌شدن فقط وجود executable را بررسی می‌کند، نه نسخه یا سلامت اتصال.
این بخش پروفایل‌ها را شروع نمی‌کند. در demo هیچ نصبی انجام نمی‌شود.

وضعیت Active یعنی سرویس فعال است، نه اینکه همین لحظه خروجی VPN تأیید شده باشد.
برای بررسی تازه Test Egress را بزنید. زمان نمایش‌داده‌شده شامل DNS و TLS و HTTPS
و تلاش مجدد است؛ پینگ ICMP نیست. مصرف پهنای‌باند متعلق به کل رابط پروفایل است و
با بازسازی آن صفر می‌شود؛ سهم دقیق هر برنامه محاسبه نمی‌شود.

## پنل وب با ظاهر ترمینال macOS

دانلود هسته‌ها اکنون درصد و حجم واقعی انتقال را نشان می‌دهد، خطاهای موقت را تا
سه بار برای هر منبع دوباره امتحان می‌کند و از مسیرهای جایگزین رسمی استفاده می‌کند.
فایل‌های تأییدشده در `/var/cache/splitforge-downloads` برای نصب آفلاین بعدی نگه‌داری
می‌شوند. کش دستی `SPLITFORGE_DOWNLOAD_CACHE` نیز پشتیبانی می‌شود؛ SHA-256 همهٔ
منابع و فایل‌های کش بررسی می‌شود و فایل نامعتبر نصب نمی‌شود. ساخت DNSTT و انتقال
بدون حجم اعلام‌شده، به‌جای درصد ساختگی با وضعیت در حال انجام نمایش داده می‌شوند.

### راه‌اندازی خودکار وب و SSL از نسخهٔ ۲٫۴

در بخش **Live logs**، دکمهٔ **Check health** بررسی بدون تغییر را انجام می‌دهد.
دکمهٔ **Check & repair** پس از تأیید، هسته‌های ضروری و منابع اختصاصی SplitForge را
تعمیر می‌کند. نتیجه، خطا، راه‌حل و موارد تعمیرشده در جدول نمایش داده می‌شوند.
بازسازی تونل ممکن است برنامه‌های فعالش را ری‌استارت کند و اتصال‌های باز بسته شوند؛
تعمیر هیچ برنامه‌ای را خودکار به Direct منتقل نمی‌کند. مسیر اصلی میزبان و SSH
بازنشانی نمی‌شوند و فایروال شرکت ارائه‌دهنده به بررسی از بیرون نیاز دارد.

در اولین اجرای تعاملی `splitforge web`، پیش از باز شدن پنل، راه‌انداز دربارهٔ
دسترسی مستقیم یا محلی، فعال‌کردن SSL، دامنه یا IP، آدرس، ایمیل اختیاری و پورت
سؤال می‌کند. سپس سرویس دائمی را نصب می‌کند و آدرس ورود را می‌دهد؛ قطع SSH پنل
را متوقف نمی‌کند. برای تغییر تنظیمات، فرمان زیر را اجرا کنید:

<div dir="ltr" align="left">

```sh
sudo splitforge web setup
# Automatic domain HTTPS:
sudo splitforge web setup --address panel.example.com --port 443 --agree-tos
# Replace YOUR_PUBLIC_IP with your server IP:
sudo splitforge web setup --address YOUR_PUBLIC_IP --port 9090 --agree-tos
# Local-only access through SSH:
sudo splitforge web setup --local --port 9090
```

</div>

گواهی معتبر دامنه و IP از Let’s Encrypt دریافت می‌شود و تمدید خودکار دو بار در
روز بررسی می‌شود. گواهی IP حدود شش روز اعتبار دارد. برای دریافت و تمدید گواهی،
**پورت ۸۰ ورودی باید باز باشد**؛ پورت انتخابی پنل نیز باید در فایروال میزبان و
شرکت ارائه‌دهنده قابل دسترسی باشد. دامنه باید به همین سرور اشاره کند. اگر دریافت
گواهی یا اجرای پنل شکست بخورد، تنظیمات و سرویس قبلی بازگردانده می‌شوند.

برای اجرای مستقیم backend در ترمینال، بدون راه‌انداز، از
`splitforge web --foreground` استفاده کنید. راهنمای قدیمی اتصال SSH در ادامه مربوط
به همین حالت است. حالت `--no-tls` فقط با انتخاب صریح شما، HTTP عمومی بدون رمزگذاری
را فعال می‌کند. ورود در همهٔ حالت‌ها به توکن خصوصی نیاز دارد.

از نسخهٔ **۲٫۳** می‌توانید برنامه‌ها، مسیرها، پروفایل‌ها، DNS، هسته‌ها و لاگ‌ها را
در مرورگر مدیریت کنید. موتور شبکه روی سرور لینوکس اجرا می‌شود؛ مرورگر می‌تواند
روی مک، ویندوز، لینوکس یا موبایل باشد.

<div dir="ltr" align="left">

```sh
sudo splitforge update
sudo splitforge web --foreground
```

</div>

پنل روی `127.0.0.1:8765` اجرا می‌شود. در ترمینال SSH دیگری توکن ورود را بخوانید:

<div dir="ltr" align="left">

```sh
sudo cat /etc/splitforge/web.token
```

</div>

حالا روی کامپیوتر خودتان این اتصال را با آدرس واقعی VPS بسازید:

<div dir="ltr" align="left">

```sh
ssh -N -L 8765:127.0.0.1:8765 root@YOUR_VPS_HOST
```

</div>

آدرس [http://127.0.0.1:8765](http://127.0.0.1:8765) را در مرورگر خود باز کنید و
توکن را وارد کنید. توکن مثل دسترسی مدیریتی root محرمانه است. پورت عمومی باز نکنید؛
دسترسی از طریق SSH انجام می‌شود. برای نمایش آزمایشی بدون root و بدون تغییر شبکه
از `splitforge web --demo` استفاده کنید.

در App Router اسکریپت را ثبت و مسیرش را انتخاب کنید. مرورگر فایل، فایل‌های **روی
سرور** را نشان می‌دهد؛ فایل کامپیوتر شما آپلود نمی‌شود. پروفایل‌ها از لینک یا مسیر
تنظیمات سرور وارد می‌شوند. تعویض مسیر برنامه را ری‌استارت می‌کند. بستن مرورگر یا
پنل، سرویس‌های برنامه را متوقف نمی‌کند. در حالت demo فرم‌ها قابل مشاهده‌اند ولی
درخواست تغییر یا نصب رد می‌شود.

![پنل وب با داده‌های نمونه](assets/web-overview.png)

[راهنمای کامل پنل وب و نصب سرویس دائمی](WEB_PANEL.md) شامل مسیر سفارشی state،
پورت، توکن و تنظیمات systemd است. بعد از ارتقای بسته، سرویس وب را ری‌استارت کنید.

## اولین پروفایل

فایل واقعی سرویس‌دهنده را در پوشهٔ خصوصی مانند `/root/profiles` نگه دارید؛ مجوز
پوشه 0700 و فایل‌ها 0600 باشد. برای WireGuard فایل `.conf` باید Address از نوع
IPv4 و peer با `AllowedIPs=0.0.0.0/0` داشته باشد. دستورات PostUp و مانند آن
پذیرفته نمی‌شوند تا تنظیمات شبکهٔ میزبان اجرا نشوند.

<div dir="ltr" align="left">

```sh
sudo splitforge profile import /root/profiles/client.conf --name wg-europe
sudo splitforge profile start wg-europe
sudo splitforge profile test wg-europe
sudo splitforge status
```

</div>

وارد کردن فقط ذخیره می‌کند. شروع پروفایل سرویس را برای بوت فعال و DNS و HTTPS
خروجی را بررسی می‌کند. اگر بررسی شکست بخورد، مسیر مستقیم جایگزین نمی‌شود.
برای URI حاوی رمز، لینک را با ویرایشگر در فایل خصوصی ذخیره کنید تا وارد تاریخچهٔ
شل و آرگومان پردازش نشود:

<div dir="ltr" align="left">

```sh
sudo splitforge profile import /root/profiles/private.uri --uri-file --name proxy-europe
sudo splitforge profile import /root/profiles/client.ovpn --name ovpn-europe
sudo splitforge profile import /root/profiles/outbound.json --name xray-europe
```

</div>

فایل Xray فقط یک outbound می‌پذیرد؛ routing دلخواه و bypass وارد نمی‌شود. فایل
OpenVPN با فهرست مجاز کنترل می‌شود و script/plugin/include رد می‌شود. فایل‌های
کلید و گواهیِ ارجاع‌شده باید بعد از import هم موجود بمانند.

## اجرای یک‌باره با root

<div dir="ltr" align="left">

```sh
sudo splitforge exec --profile wg-europe --user root --cwd /root -- /usr/bin/python3 /root/bot.py
sudo splitforge exec --profile wg-europe --user root -- /bin/bash /root/backup.sh
sudo splitforge exec --profile direct --user root -- /usr/bin/id
```

</div>

فرمان بعد از `--` قرار می‌گیرد؛ آرگومان‌ها مستقیماً ارسال می‌شوند و شل ضمنی ندارند.
برای پروژهٔ دارای venv، مسیر پایتون همان پروژه را بدهید. CLI به‌طور پیش‌فرض root
است؛ API پایتون پیش‌فرض `nobody` دارد. `exec` تا پایان فرمان منتظر می‌ماند و کد
خروج را برمی‌گرداند. root پشتیبانی می‌شود ولی capabilityها حذف می‌شوند؛ این مسیر
برای اسکریپت‌های مورد اعتماد است، نه اجرای کد مخرب در یک sandbox کامل.

## اجرای دائمی و تغییر مسیر

<div dir="ltr" align="left">

```sh
sudo splitforge app add telegram-bot --user root --cwd /root/bot -- /root/bot/venv/bin/python /root/bot/main.py
sudo splitforge bind telegram-bot --profile wg-europe
sudo splitforge bind telegram-bot --profile proxy-europe
sudo splitforge bind telegram-bot --profile direct
sudo splitforge app stop telegram-bot
```

</div>

ثبت برنامه به‌تنهایی آن را اجرا نمی‌کند. bind سرویس تولیدشده را شروع و برای بوت
فعال می‌کند؛ خرابی پردازش باعث تلاش برای اجرای مجدد می‌شود. `bind --stopped`
مسیر را ذخیره می‌کند ولی اجرا نمی‌کند. تعویض مسیر اتصال‌های جاری را قطع می‌کند؛
در شکست شروع، بازگرداندن واحد و نگاشت قبلی تلاش می‌شود، نه بازگرداندن دادهٔ برنامه.

انتخاب پردازش موجود در رابط فقط فرمانش را کپی می‌کند؛ آن پردازش جابه‌جا نمی‌شود.
اگر اجرای دو نمونه مشکل‌ساز است، نمونهٔ اصلی را خودتان متوقف کنید. هنگام انتخاب
فایل، کاربر، پوشهٔ کاری، interpreter و مجوز اجرا را بررسی کنید.

## سرویس systemd و نگاشت کاربر

<div dir="ltr" align="left">

```sh
sudo splitforge app add my-worker --user root --service my-worker.service
sudo splitforge bind my-worker --profile wg-europe
sudo splitforge user bind worker wg-europe
sudo splitforge user bind worker direct
```

</div>

کاربر ثبت‌شده باید با کاربر مؤثر سرویس برابر باشد. سرویس بدون User= یا با User=0
نیز root محسوب می‌شود و پشتیبانی می‌شود. سرویس‌های SSH، شبکه، resolver، داخلی
SplitForge و socket-activated پذیرفته نمی‌شوند. Drop-in اختصاصی
`90-splitforge.conf` اضافه می‌شود؛ Direct آن را حذف و سرویس اصلی را ری‌استارت
می‌کند. فعال‌سازی بوتِ سرویس اصلی در اختیار مدیر باقی می‌ماند.

نگاشت user فقط user-manager حساب عادی با UID حداقل 1000 را برای اجرای آینده
تنظیم می‌کند؛ پس از ری‌استارت عمدی آن manager اعمال می‌شود و می‌تواند سرویس‌های
کاربر را قطع کند. همهٔ پردازش‌های UID، SSH موجود، cron و root را یکجا شکار نمی‌کند.
برای root هر اسکریپت یا سرویس را جدا ثبت کنید.

## DNS، Kill Switch و پروتکل‌ها

IPv6 در namespace غیرفعال است. Kill Switch و DNS Guard برای برنامه‌های دارای
پروفایل اجباری‌اند، چون چند برنامه namespace مشترک دارند. با قطع هستهٔ تونل،
دسترسی مستقیم به اینترنت میزبان جایگزین نمی‌شود. جدول اصلی routing میزبان تغییر
نمی‌کند، ولی veth و جدول‌ها/قوانین اختصاصی ساخته می‌شوند. تغییرات بیرونیِ فایروال،
کرنل یا سرویس‌دهنده همچنان می‌توانند شبکه را مختل کنند؛ تضمین مطلق قطعی‌ناپذیری SSH
وجود ندارد.

<div dir="ltr" align="left">

```sh
sudo splitforge profile stop wg-europe
sudo splitforge profile dns wg-europe https://cloudflare-dns.com/dns-query 1.1.1.1
sudo splitforge profile start wg-europe
```

</div>

آدرس bootstrap باید گواهی معتبر برای hostname تنظیم‌شده ارائه دهد. DNS برنامه
از stub محلی به HTTPS داخل تونل می‌رود. برای شبکهٔ خصوصی می‌توانید endpoint تست
و CA معتبر مخصوص را با `profile probe` تنظیم کنید؛ نمونه در آموزش انگلیسی است.
TLS را برای رفع خطا خاموش نکنید. سرویس پیش‌فرض DNS و تست Cloudflare است و IP
خروجی تونل را می‌بیند.

DNSTT و Slipstream به دامنهٔ delegated و سرور سازگار نیاز دارند. مقصد سمت سرور
باید SOCKS5 باشد؛ آداپتور فعلی آن‌ها TCP است و UDP عمومی ارائه نمی‌کند.
Slipstream گواهی PEM پین‌شده و DNSTT کلید عمومی ۳۲ بایتی hex می‌خواهد.
روش راه‌اندازی در [راهنمای پروتکل‌ها](PROTOCOLS.md) آمده است.

<div dir="ltr" align="left">

```sh
sudo splitforge dependencies install dnstt-client
sudo splitforge profile dns-tunnel dns-main dnstt t.example.com udp://1.1.1.1:53 --public-key-file /root/server.pub
sudo splitforge dependencies install slipstream-client
sudo splitforge profile dns-tunnel dns-backup slipstream t.example.com 1.1.1.1:53 --certificate /root/server.pem
```

</div>

نمونه‌ها به سرور و دامنهٔ واقعی خودتان نیاز دارند. ساخت DNSTT از سورس پین‌شده است
و دسترسی به رجیستری Go لازم دارد؛ فیلترینگ دانلود می‌تواند نصب را متوقف کند.

## ویرایش، ارتقا، توقف و بازیابی

<div dir="ltr" align="left">

```sh
sudo splitforge profile stop wg-europe
sudo splitforge profile import /root/profiles/new.conf --replace wg-europe
sudo splitforge profile start wg-europe
sudo splitforge bind telegram-bot --profile wg-europe
```

</div>

جایگزینی شناسه، اتصال برنامه‌ها، DNS و تنظیم تست را حفظ و اندازه‌گیری قبلی را پاک
می‌کند. شروع مجدد پروفایل به‌تنهایی همهٔ برنامه‌های متوقف‌شده را راه نمی‌اندازد؛
bind یا restore را آگاهانه اجرا کنید. برای ارتقا ابتدا از state، کلیدهای اصلی،
واحدهای systemd و دادهٔ برنامه بکاپ خصوصی بگیرید:

<div dir="ltr" align="left">

```sh
git pull --ff-only
sudo bash install.sh --upgrade --restore
sudo splitforge status
sudo splitforge logs --follow
```

</div>

ارتقا workloadها را متوقف، intent فعال‌بودن را حفظ و بسته را نصب می‌کند؛ restore
دوباره همان intent را اعمال می‌کند. بدون آن می‌توانید بعداً `sudo splitforge restore`
بزنید. شکست نصب ممکن است برنامه‌ها را متوقف باقی بگذارد؛ نسخهٔ قبلی را دوباره نصب
و بازیابی کنید. rollback تراکنشیِ بسته یا دادهٔ برنامه پیاده نشده است. رفتار ریبوت
و upstream را روی سرور خودتان تمرین کنید.

### آپدیت با یک فرمان

از نسخهٔ **۲٫۲** به بعد، از هر پوشه‌ای می‌توانید اجرا کنید:

<div dir="ltr" align="left">

```sh
sudo splitforge update
```

</div>

اگر با root وارد شده‌اید، فقط `splitforge update` کافی است. برنامه آخرین نسخهٔ
شاخهٔ رسمی master را دریافت می‌کند، مسیر نصب را خودکار تشخیص می‌دهد و از state
در `/var/backups/splitforge` بکاپ خصوصی می‌گیرد. سپس ارتقا و بازیابی برنامه‌های
فعال ذخیره‌شده انجام می‌شود. هنگام ارتقا برنامه‌های مدیریت‌شده ری‌استارت می‌شوند؛
اگر همان revision نصب باشد، نصب و ری‌استارت تکرار نمی‌شود. پوشهٔ سورس قبلی لازم
نیست و تغییرات محلی آن دست‌نخورده می‌ماند. هسته‌های اختیاری دوباره دانلود نمی‌شوند.

برای نصب مجدد همان نسخه `--force`، برای مسیر سفارشی `--prefix` و برای state
سفارشی گزینهٔ عمومی `--state` قبل از update را بدهید. در شکست دانلود، نصب قبلی
تغییر نمی‌کند. شکست مرحلهٔ نصب ممکن است برنامه‌ها را متوقف باقی بگذارد؛ بکاپ
حفظ می‌شود و پس از تعمیر نصب، `splitforge restore` را با همان state اجرا کنید.
این فرمان rollback خودکارِ بسته یا دادهٔ برنامه ندارد.

اگر نسخهٔ فعلی شما قدیمی‌تر از ۲٫۲ است، یک بار با روش `git pull` و
`install.sh --upgrade --restore` بالا آپدیت کنید تا این فرمان اضافه شود.

<div dir="ltr" align="left">

```sh
sudo splitforge app remove telegram-bot
sudo splitforge profile stop wg-europe
sudo splitforge profile remove wg-europe
sudo splitforge stop-all
```

</div>

قبل از حذف پروفایل، ارجاع برنامه‌ها و کاربرانش را بردارید. حذف ثبت سرویس موجود
خودِ unit اصلی یا داده‌ها را حذف نمی‌کند ولی آن را متوقف می‌کند. برای uninstall
اول نگاشت کاربران، برنامه‌ها و پروفایل‌ها را حذف کنید؛ سپس symlink فرمان و پوشهٔ
نصب را بردارید. ابزارهای مشترک سیستم را بدون بررسی حذف نکنید. stop-all وضعیت را
نگه می‌دارد؛ گزینهٔ `--preserve` intent بوت را هم برای restore حفظ می‌کند.

## امنیت، آزمون و گزارش مشکل

state شامل رمز و کلید است؛ در GitHub، اسکرین‌شات یا لاگ عمومی منتشرش نکنید.
namespace جداسازی شبکه است، نه جداسازی کامل فایل و کد مخرب. روی حساب root فقط
برنامهٔ مورد اعتماد اجرا کنید. [مدل امنیت](../SECURITY.md) را بخوانید.

آزمون‌ها شامل اجرای واقعی namespace، SOCKS5، WireGuard، DoH با TLS معتبر،
root، تعویض برنامه و جلوگیری از fallback هستند. تست کنترل‌شدهٔ محلی جای آزمایش
همهٔ VPNهای عمومی، توزیع‌ها و ریبوت را نمی‌گیرد. فرمان بازتولید و جزئیات در
[VALIDATION.md](VALIDATION.md) است. برای گزارش، نسخهٔ سیستم و هسته‌ها، خطای دقیق
و لاگ پاک‌سازی‌شده از اطلاعات حساس را در
[Issues](https://github.com/EclipseOfficialDota/SplitForge/issues) بفرستید.

</div>
