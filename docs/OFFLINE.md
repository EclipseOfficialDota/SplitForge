# Offline Release bundles / بسته‌های آفلاین

Every new release publishes `splitforge-VERSION-offline-OS-VERSION-ARCH.zip`
assets, separately for Ubuntu 22.04/24.04 and Debian 12/13 on amd64/arm64.
Use **Releases → Assets**, not GitHub's automatically generated Source code ZIP.
Check `/etc/os-release` and `dpkg --print-architecture` on your VPS and download
the exact match. A bundle for another distribution, version or CPU is refused.

Each ZIP contains:

- SplitForge wheel and source distribution, with all transitive Python wheels
  for that OS's default Python, including cryptography and native extensions.
- Local Debian packages and their complete dependency closure: Python/venv,
  git, curl, unzip, certificates, iproute2, nftables, procps, WireGuard, OpenVPN,
  proxychains and nginx. No Iranian mirror is needed by this installer.
- Ready-to-run Xray, tun2socks, Slipstream, DNSTT and NoizDNS clients. Go builds
  run during release creation, not on your VPS. Pinned source archives, Go
  toolchain and module sources accompany the DNS clients.
- Certbot and its Python dependencies, ready for the web panel's HTTPS setup.
- Internal SHA256SUMS, component license notices and `install-offline.sh`.
  The release's outer SHA256SUMS also covers each whole ZIP.

Download on any connected device, verify the ZIP against the release's
SHA256SUMS, then upload it to the VPS. Extract it using `unzip` (or extract on
your computer first if unzip is unavailable on the VPS). Inside its directory:

```bash
sudo bash install-offline.sh
# Existing installation; stop managed workloads and restore saved assignments:
sudo bash install-offline.sh --upgrade --restore
```

The installer verifies every payload before changes, uses only local packages
and wheels, installs all bundled cores and does not change the host main routes.
Updates stop managed workloads before replacing their environment. Back up your
state first. The offline installer does not run the online updater's automatic
snapshot/rollback procedure or restart an already running web panel. After an
upgrade, restart `splitforge-web.service` if you use that managed panel.

This is an offline **dependency installation**, not offline Internet access.
Certificate issuance/renewal still requires ACME access; VPNs still require
reachable servers. Arbitrary third-party app dependencies, other Python ABIs,
custom kernels and other distributions are outside these bundles. Packages are
a release-time snapshot; security updates after that date are not included.
If a newer system has incompatible local packages, apt fails rather than
downloading replacements or silently downgrading them. Keep the extracted ZIP
to reinstall dependencies later. The ordinary `splitforge update` remains an
online source update; use the matching offline ZIP to update without mirrors.

---

## فارسی

در هر انتشار جدید، فایل ZIP مستقل برای **اوبونتو ۲۲٫۰۴ و ۲۴٫۰۴** و
**دبیان ۱۲ و ۱۳**، برای هر دو معماری **amd64 و arm64** منتشر می‌شود.
آن را از قسمت **Releases → Assets** دریافت کنید؛ فایل خودکار **Source code**
گیت‌هاب بستهٔ آفلاین نیست. نسخهٔ سیستم و معماری باید دقیقاً مطابق نام فایل باشد.

داخل فایل، برنامه و تمام وابستگی‌های پایتون، بسته‌های سیستم با وابستگی‌هایشان،
nginx و Certbot، و هسته‌های آمادهٔ Xray، tun2socks، DNSTT، NoizDNS و Slipstream
قرار دارد. سورس و اطلاعات مجوز هسته‌های DNS هم همراه آن است. نصب‌کننده ابتدا
صحت فایل‌ها را بررسی می‌کند و هیچ بسته‌ای از میرور یا اینترنت دانلود نمی‌کند.

فایل را روی دستگاه دارای اینترنت دانلود کنید، هش آن را با SHA256SUMS همان
انتشار بررسی و سپس به VPS منتقل و استخراج کنید. برای نصب جدید دستور اول و
برای ارتقا دستور دوم در کادر بالا را اجرا کنید. هنگام ارتقا، برنامه‌های مدیریت‌شده
موقتاً متوقف و با `--restore` دوباره اجرا می‌شوند. ابتدا از تنظیمات نسخهٔ پشتیبان
بگیرید. پنل فعال را بعد از ارتقا با `sudo systemctl restart splitforge-web.service`
راه‌اندازی مجدد کنید. این روش، بکاپ و بازگشت خودکار دستور آپدیت آنلاین را اجرا نمی‌کند.

صدور و تمدید گواهی HTTPS همچنان نیاز به دسترسی ACME دارد و اتصال تونل‌ها هم به
اینترنت نیاز دارد. وابستگی‌های اسکریپت‌های شخصی شما، کرنل سفارشی و نسخه‌های دیگر
سیستم در این بسته نیستند. برای آپدیت بدون میرور، ZIP آفلاین نسخهٔ جدید را بگیرید؛
دستور معمول `splitforge update` همچنان آنلاین است.
