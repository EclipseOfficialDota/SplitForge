# راهنمای کامل فارسی SplitForge

[صفحهٔ اصلی](../README.md) · [آموزش عملی انگلیسی](GETTING_STARTED.md) ·
[پروتکل‌ها](PROTOCOLS.md) · [مرجع API](API.md) · [عیب‌یابی](TROUBLESHOOTING.md)

## ۱. SplitForge چیست؟

SplitForge برای انتخاب مسیر اینترنتِ هر برنامه روی سرور لینوکسی طراحی شده است.
مثلاً ربات تلگرام از یک پروفایل WireGuard، اسکرپر از VLESS و اسکریپت پشتیبان از
OpenVPN استفاده کنند، در حالی که برنامه‌های ثبت‌نشده و شبکهٔ اصلی سرور مسیر قبلی
خود را داشته باشند. هر پروفایل فعال یک فضای شبکهٔ مستقل یا Network Namespace دارد.

برنامه از داخل همان فضا اجرا می‌شود و فرزندانش نیز آن فضا را به ارث می‌برند.
ثبت یک مسیر فایل به‌تنهایی فرایندهای ازقبل‌اجراشده را پیدا و منتقل نمی‌کند.
این پروژه سرویس‌دهندهٔ VPN، فروشندهٔ کانفیگ، نصب‌کنندهٔ سرور DNSTT یا مدیر شبکهٔ
کانتینرها نیست؛ باید اتصال و سرور سمت مقابل را از قبل داشته باشید.

## ۲. الان دقیقاً چه چیزی آماده است؟

نسخهٔ موجود **بک‌اند مرحلهٔ اول** است و این کدها را دارد:

- ذخیرهٔ پروفایل‌ها، برنامه‌ها و نگاشت کاربران در فایل state با نوشتن اتمیک و قفل.
- خواندن URIها و فایل‌های پشتیبانی‌شده و ردکردن بخشی از تنظیمات نامعتبر/خطرناک.
- ساخت namespace، رابط شبکه، مسیرهای محدود و قواعد nftables.
- DNS محلی در namespace که درخواست‌ها را از طریق HTTPS معتبر ارسال می‌کند.
- اجرای یک‌بارهٔ فرمان یا ساخت سرویس پایدار systemd با کاربر غیر root.
- نسبت‌دادن سرویس واجد شرایط به پروفایل و تغییر تخصیص با توقف/اجرای مجدد.
- بررسی IP خروجی، کد کشور، زمان درخواست HTTPS و شمارندهٔ ترافیک رابط تونل.

این بخش‌ها **هنوز وجود ندارند**: رابط Textual، ماتریس تعاملی، فایل‌براوزر، نمایشگر
لاگ داخل برنامه، فرمان عمومی `splitforge`، نصب‌کنندهٔ `install.sh` و بسته‌بندی
`pyproject.toml`. بنابراین فعلاً دستورهایی مثل `splitforge exec` یا نصب با
`pip install .` راه استفاده از این مخزن نیستند.

نتیجهٔ ثبت‌شدهٔ تست روی ویندوز: **۹ تست موفق و ۱ تست مخصوص POSIX ردشده از اجرا**.
تست‌های شبکه فرمان‌های تولیدشده را با mock بررسی می‌کنند؛ اتصال واقعی VPN و
رفتار کرنل/systemd، قطع تونل، راه‌اندازی مجدد و ایمنی SSH هنوز روی لینوکس تأیید
نشده‌اند. عدد نسخه در سورس هم به معنی انتشار نسخهٔ پایدار یا تأیید تولید نیست.

## ۳. پیش‌نیازها و سطح دسترسی

| مورد | توضیح |
| --- | --- |
| میزبان | لینوکس با systemd به‌عنوان PID 1؛ ماشین مجازی یا VPS آزمایشی |
| پایتون | مبنای پیشنهادی 3.10 یا جدیدتر |
| دسترسی مدیریتی | برای ساخت namespace، قواعد فایروال و سرویس سیستم |
| کاربر برنامه | کاربر موجودِ غیر root؛ Runner اجرای UID صفر را رد می‌کند |
| قابلیت کرنل | namespace و TUN؛ برای WireGuard پشتیبانی کرنل هم لازم است |
| اتصال سمت مقابل | کانفیگ واقعی، سرور فعال و اطلاعات احراز هویت معتبر |
| ابزار پروتکل | ابزارهای سیستم و باینری‌های لازم برای آداپتور انتخابی |

Ubuntu 22.04/24.04 و Debian 12 هدف‌های معقول برای آزمایش‌اند؛ فهرست توزیع‌های
تأییدشده نیستند. صرف وجود پایتون روی ویندوز، macOS، WSL یا یک کانتینر محدود برای
اجرای بخش شبکه کافی نیست. برای آزمایش سرور، کنسول بازیابی ارائه‌دهنده را در دسترس
داشته باشید؛ این مستند ادعای «قطع‌نشدن قطعی SSH» نمی‌کند.

## ۴. شروع بدون تغییر شبکه

برای دیدن سورس و اجرای تست‌های غیرمدیریتی:

```sh
git clone https://github.com/EclipseOfficialDota/SplitForge.git
cd SplitForge
python3 -m unittest discover -s tests -v
```

بک‌اند فعلی فقط از کتابخانهٔ استاندارد پایتون استفاده می‌کند. اجرای این تست‌ها به
کانفیگ VPN یا root نیاز ندارد. روی ویندوز تست دوام state اجرا نمی‌شود و خودِ
Runner نیز به ماژول لینوکسی `pwd` وابسته است.

## ۵. آماده‌سازی دستی محیط آزمایشی لینوکس

این روش موقتِ توسعه است تا زمان انتشار نصب‌کننده. دستورهای کامل و قابل پیگیری در
[آموزش عملی](GETTING_STARTED.md#manual-linux-lab-setup) آمده‌اند. ترتیب کار:

1. ابزارهای سیستم را با مدیر بستهٔ توزیع نصب کنید.
2. سورس را در مسیر ثابت و متعلق به root قرار دهید.
3. یک venv ثابت بسازید و پوشهٔ پکیج را در site-packages آن کپی کنید.
4. import را بیرون از پوشهٔ سورس بررسی کنید.
5. کاربر غیر root و مسیر مناسب برای اسکریپت بسازید.
6. فایل کانفیگ واقعی را بیرون از Git و با دسترسی محدود نگه دارید.

ابزارهای پایه و آداپتورهای WireGuard/OpenVPN:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends \
  python3 python3-venv git ca-certificates curl \
  iproute2 nftables procps wireguard-tools openvpn
```

برای پروفایل‌های پروکسی، `xray` و `tun2socks` هم لازم‌اند. DNSTT به
`dnstt-client` و Slipstream به `slipstream-client` نیاز دارد. آن‌ها را از پروژه‌های
اصلیِ لینک‌شده در [راهنمای پروتکل](PROTOCOLS.md) تهیه کنید، معماری پردازنده و
اطلاعات صحت انتشار را بررسی کنید و در مسیر سیستمی متعلق به root قرار دهید.
این مخزن فعلاً آن‌ها را خودکار نصب یا نسخهٔ آن‌ها را pin نمی‌کند.

برای نصب دستیِ تازه، مسیرهای زیر نباید از قبل دارای نصب دیگری باشند:

```sh
sudo install -d -m 0755 /opt/splitforge
sudo git clone https://github.com/EclipseOfficialDota/SplitForge.git /opt/splitforge/source
sudo python3 -m venv /opt/splitforge/venv

sudo /opt/splitforge/venv/bin/python - <<'PY'
import shutil
import sysconfig
from pathlib import Path

source = Path('/opt/splitforge/source/splitforge')
target = Path(sysconfig.get_paths()['purelib']) / 'splitforge'
if target.exists():
    raise SystemExit('Existing installation: follow the update guide.')
shutil.copytree(source, target)
print(target)
PY

cd /tmp
sudo /opt/splitforge/venv/bin/python -c \
  'import splitforge; print(splitforge.__file__)'
```

خروجی import باید داخل venv باشد. این نکته مهم است: systemd از همان مسیر مطلق
مفسر استفاده می‌کند و ممکن است پوشهٔ کاریِ ترمینال شما را نداشته باشد. صرف اجرای
پایتون از داخل مخزن، نصب پایدارِ helperها محسوب نمی‌شود.

نمونهٔ ساخت کاربر و مسیرهای آزمایشی:

```sh
sudo useradd --system --create-home \
  --home-dir /var/lib/splitforge-demo \
  --shell /usr/sbin/nologin splitforge-demo
sudo install -d -m 0755 /srv/splitforge-demo
sudo install -d -m 0700 /root/splitforge-profiles
```

اگر کاربر وجود دارد، ابتدا وضعیتش را بررسی کنید. کانفیگ واقعی WireGuard را به
`/root/splitforge-profiles/client.conf` منتقل و دسترسی فایل را `0600` کنید.
اسکریپت برنامه باید برای کاربر برنامه خواندنی و پوشه‌هایش قابل عبور باشند؛ مسیر
`/root/bot.py` معمولاً برای کاربر غیر root مناسب نیست.

## ۶. ساخت و آزمایش اولین پروفایل

فایل WireGuard باید IPv4 در `Address` و یک peer با `AllowedIPs = 0.0.0.0/0`
داشته باشد. hookهایی مثل `PostUp` پذیرفته نمی‌شوند. `DNS` داخل فایل هم جایگزین
می‌شود. نمونهٔ اجرای API با دسترسی مدیریتی:

```sh
sudo /opt/splitforge/venv/bin/python - <<'PY'
from splitforge.state import StateStore
from splitforge.protocols.manager import ProtocolManager

store = StateStore()
manager = ProtocolManager(store)
existing = [p for p in store.profiles() if p.name == 'wg-lab']
profile = existing[0] if existing else manager.import_profile(
    '/root/splitforge-profiles/client.conf', name='wg-lab'
)
print('ID:', profile.id)
print('Missing:', manager.missing(profile.protocol))
manager.start(profile.id)
print(manager.test(profile.id))
PY
```

نام پروفایل باید یکتا باشد. import مجدد با نام یکسان، ویرایش پروفایل قبلی نیست.
`start()` سرویس پروفایل را می‌سازد، اجرا و برای بوت فعال می‌کند. همچنین در شروع،
بررسی واقعی DNS/HTTPS انجام می‌دهد؛ شکست این مرحله ممکن است کمی طول بکشد.

خروجی تست شامل IP مشاهده‌شده، کد کشور و زمان درخواست است. این زمان، DNS، TLS،
HTTP و تلاش‌های مجدد را در بر می‌گیرد؛ **پینگ ICMP نیست**. بررسی از مسیر
`https://www.cloudflare.com/cdn-cgi/trace` انجام می‌شود و وابستگی به همان مقصد
دارد. فیلد `active` در `status()` وضعیت سرویس systemd است و به‌تنهایی سلامت
لحظه‌ای اتصال را ثابت نمی‌کند.

## ۷. اجرای یک فرمان یا اسکریپت

پس از آماده‌سازی محیط، نمونه‌های API با این اشیا کار می‌کنند:

```python
from splitforge.state import StateStore
from splitforge.protocols.manager import ProtocolManager
from splitforge.core.runner import Runner

store = StateStore()
manager = ProtocolManager(store)
runner = Runner(store, manager)
```

در همین زمینهٔ پایتون مدیریتی، برای یک اسکریپت واقعی:

```python
exit_code = runner.execute(
    ['/usr/bin/python3', '/srv/my-app/bot.py'],
    profile_name='wg-lab', user='my-app-user', cwd='/srv/my-app'
)
print(exit_code)
```

نام کاربر و مسیرها را با موارد موجود عوض کنید. برای فایل شل:

```python
runner.execute(
    ['/bin/sh', '/srv/my-app/job.sh'],
    profile_name='wg-lab', user='my-app-user', cwd='/srv/my-app'
)
```

این اجرا یک سرویس موقت systemd است و رکورد برنامهٔ دائمی نمی‌سازد. shell خودکار
بین آرگومان‌ها قرار نمی‌گیرد. اگر نام پروفایل در `execute()` داده نشود، نگاشت ذخیره‌شدهٔ
کاربر بررسی می‌شود؛ اگر نگاشتی نباشد، اجرا Direct است. در این نسخه گزینهٔ جداگانهٔ
«Direct با نادیده‌گرفتن نگاشت موجود کاربر» برای اجرای یک‌باره وجود ندارد.

## ۸. اجرای دائمی و تعویض تونل

برای اسکریپت موجود و خواندنی با کاربر برنامه:

```python
from splitforge.state import AppBinding

app = AppBinding(
    name='my-bot', argv=['/usr/bin/python3', '/srv/my-app/bot.py'],
    user='my-app-user', cwd='/srv/my-app',
)
store.save_app(app)
app = runner.bind(app.id, 'wg-lab')
print(app.id, runner.unit(app))
```

ذخیرهٔ `AppBinding` به‌تنهایی برنامه را اجرا نمی‌کند؛ `bind()` سرویس را می‌سازد و
به‌صورت پیش‌فرض اجرا/فعال می‌کند. برای ثبت تخصیص و باقی‌گذاشتن برنامه در حالت متوقف:

```python
runner.bind(app.id, 'wg-lab', start=False)
```

اگر پروفایل واقعی دوم را قبلاً با نام `vless-lab` وارد کرده‌اید:

```python
runner.bind(app.id, 'vless-lab')
```

ابتدا پروفایل مقصد آماده می‌شود، سپس برنامهٔ قبلی متوقف و با namespace جدید
اجرا می‌شود. **اتصال‌های باز و حافظهٔ فرایند حفظ نمی‌شوند.** اگر مرحله‌ای شکست
بخورد، بازگردانی تنظیمات و وضعیت قبلی تلاش می‌شود؛ خودِ rollback هم ممکن است
شکست بخورد و باید لاگ و وضعیت واقعی سرویس را بررسی کنید.

بازگشت برنامهٔ ثبت‌شده به اینترنت مستقیم:

```python
runner.bind(app.id, None)
```

در حالت Direct، محافظ namespace/DNS مربوط به SplitForge اعمال نمی‌شود. برای
سرویسِ ازقبل‌موجود، drop-in متعلق به SplitForge حذف می‌شود و تنظیم اصلی سرویس
دوباره ملاک است؛ اگر آن سرویس خودش محدودیت شبکه دارد، آن محدودیت باقی می‌ماند.

## ۹. سرویس موجود و نگاشت کاربر

برای نمونه، اگر `my-worker.service` از قبل loaded و دارای `User=my-worker` است:

```python
service_app = AppBinding(
    name='worker-service', service='my-worker.service', user='my-worker'
)
store.save_app(service_app)
runner.bind(service_app.id, 'wg-lab')
```

سرویس root، سرویس socket-activated و واحدهای داخلی SplitForge از این راه پذیرفته
نمی‌شوند. فایل اصلی سرویس جایگزین نمی‌شود؛ یک `90-splitforge.conf` در پوشهٔ drop-in
اضافه می‌شود و تخصیص باعث restart سرویس خواهد شد.

نگاشت کاربر قابلیت محدودتری دارد:

```python
unit = runner.bind_user('labuser', 'wg-lab')
print(unit)
```

`labuser` باید کاربر واقعی با UID حداقل ۱۰۰۰ باشد؛ کاربر سیستمیِ نمونهٔ بالا
واجد این شرط نیست. این API برای `user@UID.service` فایل می‌نویسد و systemd را
reload می‌کند، ولی user manager را خودکار restart نمی‌کند. اعمال آن روی manager
درحال‌اجرا به restart آگاهانهٔ همان واحد نیاز دارد و برنامه‌های زیرمجموعه‌اش را
می‌تواند متوقف کند. فرایندها، نشست SSH و jobهای هم‌UID خارج از این manager خودکار
منتقل نمی‌شوند. برای حذف نگاشت، `runner.bind_user('labuser', None)` را فراخوانی
کنید و برای تغییر فضای manager درحال‌اجرا همان نکتهٔ restart را در نظر بگیرید.

## ۱۰. تفاوت پروتکل‌ها و DNS

| پروتکل | نکتهٔ مهم این نسخه |
| --- | --- |
| VLESS / VMess / Trojan / Shadowsocks | Xray به‌همراه tun2socks؛ سازگاری UDP به سرور و تنظیمات وابسته است |
| SOCKS5 | برای UDP باید سرویس سمت مقابل واقعاً UDP relay بدهد |
| WireGuard | IPv4 و peer مسیر پیش‌فرض لازم است؛ hookهای wg-quick اجرا نمی‌شوند |
| OpenVPN | TUN و مجموعهٔ محدود تنظیمات؛ plugin، include و اسکریپت دلخواه رد می‌شوند |
| DNSTT | سرور، دامنه، کلید عمومی و SOCKS5 سمت مقابل لازم است؛ آداپتور TCP است |
| Slipstream | SOCKS5 سمت مقابل، resolver IPv4 و گواهی PEM pin‌شده لازم است؛ TCP است |

DNSTT و Slipstream خودشان معادل SOCKS سرور نیستند. تنظیم DNS delegation و سرور
مقابل خارج از این پروژه است. UDP عمومی برنامه روی این دو آداپتور رد می‌شود؛
DNS محلی همچنان با UDP/TCP به stub می‌رسد و از آنجا با HTTPS/TCP در تونل می‌رود.

resolver برنامه در namespace روی `127.0.0.53` قرار می‌گیرد. پیش‌فرض DoH، آدرس
`https://cloudflare-dns.com/dns-query` با IP راه‌انداز `1.1.1.1` است. IP راه‌انداز
باید برای نام URL گواهی معتبر داشته باشد. ذخیرهٔ تنظیمات DNS، helper درحال‌اجرا
را خودکار reload نمی‌کند. DNS حاملِ خود DNSTT/Slipstream با DNS برنامه متفاوت است.

چون چند برنامه یک namespace پروفایل را شریک‌اند، خاموش‌کردن Kill Switch یا
DNS isolation برای یک برنامهٔ تونل‌شده مستقل از بقیه در این نسخه مجاز نیست.
Proxychains هم صرفاً wrapper راحتِ TCP است و ضمانت namespace را ندارد.

## ۱۱. لاگ، اطلاعات و عیب‌یابی

نام واحد برنامه را از `runner.unit(app)` بگیرید و همان نام واقعی را استفاده کنید:

```sh
sudo systemctl status splitforge-app-APP_ID.service --no-pager
sudo journalctl -u splitforge-app-APP_ID.service -b --no-pager -n 100
sudo journalctl -u splitforge-profile-PROFILE_ID.service -b --no-pager -n 100
sudo journalctl -u splitforge-core-PROFILE_ID.service -b --no-pager -n 100
sudo journalctl -u splitforge-dns-PROFILE_ID.service -b --no-pager -n 100
```

`APP_ID` و `PROFILE_ID` در این فرمان‌ها نمونه‌اند؛ شناسهٔ واقعی را جایگزین کنید.
برای سرویس پذیرفته‌شده، نام واحد اصلی سرویس را بررسی کنید. واحدهای موقت ممکن
است بعد از خروج collect شوند، اما رکورد journal باقی مانده باشد.

خطاهای رایج:

- **ماژول پیدا نمی‌شود:** پکیج باید برای مفسر ثابتِ استفاده‌شده توسط systemd هم
  قابل import باشد؛ import از پوشهٔ سورس کافی نیست.
- **فایل برنامه باز نمی‌شود:** کاربر برنامه باید به فایل، مفسر و پوشهٔ کاری دسترسی
  داشته باشد؛ برنامه با root اجرا نمی‌شود.
- **ابزار پیدا نمی‌شود:** alias یا PATH مخصوص shell ورود برای helper کافی نیست.
- **تداخل subnet/rule:** مسیرهای میزبان یا کانتینر را بررسی کنید؛ مسیر نامرتبط را
  برای رفع خطا پاک نکنید. انتخاب خودکار pool جایگزین فعلاً وجود ندارد.
- **تست IP/DNS شکست می‌خورد:** لاگ DNS، core و tun را کنار هم ببینید؛ ساعت سیستم،
  CA، bootstrap IP، upstream و دسترسی به مقصد تست را بررسی کنید.
- **OpenVPN منتظر می‌ماند:** احراز هویت باید غیرتعاملی و فایل‌های بیرونی موجود باشند.
- **DNSTT/Slipstream پورت باز دارند ولی کار نمی‌کنند:** سمت مقابل باید واقعاً SOCKS5
  باشد؛ صرف یک TCP listener یا پورت SSH به‌تنهایی کافی نیست.
- **IP/ترافیک قدیمی دیده می‌شود:** دادهٔ state آخرین اندازه‌گیری است؛ شمارنده‌ها هم
  مجموع رابط پروفایل‌اند و با ایجاد دوبارهٔ رابط از نو آغاز می‌شوند.

راهنمای [عیب‌یابی کامل](TROUBLESHOOTING.md) فرمان‌های تشخیصی مرحله‌به‌مرحله دارد.
برای رفع خطا فایروال کل میزبان یا routing table اصلی را flush نکنید.

## ۱۲. توقف، حذف و نگهداری

در زمینهٔ API دارای `store`، `manager`، `runner` و `app`:

```python
runner.stop(app.id)       # توقف؛ نگه‌داشتن تخصیص
```

برای حذف ثبت برنامه و واحد/drop-in متعلق به آن:

```python
runner.remove(app.id)
```

پس از حذف یا تغییر همهٔ ارجاع‌های برنامه/کاربر به پروفایل:

```python
profile = store.profile('wg-lab')
manager.stop(profile.id)
```

توقف پروفایل می‌تواند برنامه‌های وابسته را هم متوقف کند. فیلد `enabled` در state
وضعیت زندهٔ فرایند نیست. با روشن‌کردن دوبارهٔ پروفایل، همهٔ برنامه‌های قبلاً متوقف‌شده
خودکار زنده نمی‌شوند؛ آن‌ها را صریحاً restart یا دوباره bind کنید.

برای حذف دائمی، ابتدا teardown را انجام دهید، سپس واحد متوقف‌شدهٔ همان پروفایل
را بردارید و در آخر state بدون ارجاعش را حذف کنید. نمونهٔ دقیق و محدود به همان
شناسه در [بخش پاک‌سازی](GETTING_STARTED.md#inspection-stop-and-cleanup) آمده است.
پاک‌کردن JSON به‌تنهایی شبکهٔ فعال را جمع نمی‌کند؛ helperها نیز برای جمع‌کردن منابع
به state نیاز دارند.

در نصب دستی، پکیج داخل venv کپی شده است؛ `git pull` روی checkout به‌تنهایی آن را
به‌روز نمی‌کند. قبل از تعویض نسخه، برنامه‌ها و پروفایل‌های مربوط را متوقف کنید،
state و credentialهای بیرونی را با دسترسی محدود پشتیبان بگیرید و مسیر مفسر مورد
استفادهٔ سرویس‌ها را حفظ کنید. راهنمای [به‌روزرسانی](GETTING_STARTED.md#updating-the-manual-installation)
جزئیات ترتیب کار و لزوم آزمایش reboot را توضیح می‌دهد.

## ۱۳. اطلاعات حساس و مشارکت

state پیش‌فرض در `/etc/splitforge/state.json` است و می‌تواند کلید خصوصی، رمز و
کانفیگ کامل را داشته باشد. مجوز فایل محدود است، اما داده **در حالت ذخیره رمزگذاری
نشده** است. نسخهٔ پشتیبان هم حساس محسوب می‌شود. فایل state، کانفیگ واقعی و URI
اشتراک را در Issue یا Git قرار ندهید. جزئیات در [SECURITY.md](../SECURITY.md) است.

برای گزارش باگ، commit سورس، نسخهٔ توزیع/کرنل/پایتون/systemd و باینری پروتکل،
فراخوانی API ناموفق و بخش پاک‌سازی‌شدهٔ خطا/لاگ را بنویسید. مشخص کنید تست واقعی
اتصال انجام داده‌اید یا فقط تست واحد را اجرا کرده‌اید. برای گزارش امنیتی، وجود
گزینهٔ گزارش خصوصی GitHub را بررسی کنید؛ کانال خصوصی یا SLA از قبل اعلام نشده است.

## ۱۴. ادامهٔ پروژه

مرحلهٔ دوم برای رابط Textual، داشبورد، ماتریس انتخاب تونل، انتخاب فایل/فرایند،
تنظیمات محافظ و نمایش لاگ برنامه‌ریزی شده است. مرحلهٔ سوم برای CLI عمومی،
نصب‌کننده و بسته‌بندی است. آزمایش واقعی پروتکل‌ها، شکست تونل، DNS، IPv6، rollback
و reboot قبل از ادعای آمادگی تولید لازم است. زمان انتشار یا نتیجهٔ بنچمارک
تأییدشده‌ای فعلاً اعلام نشده است.

مجوز خود SplitForge، [MIT](../LICENSE) است. ابزارهای بیرونی مجوز و الزامات خودشان
را دارند. راهنمای مشارکت در [CONTRIBUTING.md](../CONTRIBUTING.md) قرار دارد.
