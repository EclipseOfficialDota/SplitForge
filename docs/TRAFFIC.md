# Traffic graphs and budgets / مصرف و سقف ترافیک

[README](../README.md) · [Web panel](WEB_PANEL.md) · [Backups](BACKUPS.md)

Open **Traffic & quotas** in the web panel. Each registered application and
tunnel has cumulative receive/send totals, a rate graph, a configurable byte
budget and a warning threshold. Collection starts with managed app/profile
startup and runs in its own permanent systemd service, so closing the panel does
not disable it. **Enable collector** starts it explicitly on an idle installation.

## Profile speed limits / محدودیت سرعت کانفیگ

Open **Tunnel profiles → Speed limit**, or use the same button on a tunnel's
**Traffic & quotas** card. Enter separate download/upload caps in decimal Mbps;
zero means unlimited in that direction. For example, 10 Mbps download and 2 Mbps
upload are shared by all applications using that profile, not assigned to each
application separately. **Set budget** controls the separate cumulative volume
limit in MiB (1024 MiB = 1 GiB). A profile can have both types of limit.

```sh
sudo splitforge traffic speed my-tunnel --download-kbps 10000 --upload-kbps 2000
sudo splitforge traffic quota my-tunnel --kind profile --mib 10240 --warning 80
# Disable both speed caps; this does not disable the volume budget:
sudo splitforge traffic speed my-tunnel
```

Speed settings persist in the private traffic registry and encrypted backups.
Running profiles change live; stopped profiles apply them on activation before
managed apps start. Recreating a tunnel restores its saved caps. Failed changes
restore previous rules; if recovery also fails, the tunnel interface is disabled
and must be restarted. No host interface, host route or SSH setting is shaped.

The Linux `tc` tool and kernel TBF/u32/police support are required. Upload uses
[TBF shaping](https://man7.org/linux/man-pages/man8/tc-tbf.8.html). Download uses
[ingress policing](https://man7.org/linux/man-pages/man8/tc-police.8.html), dropping
excess packets; TCP adapts, UDP may lose data. Token buckets allow short bursts
(at least 64 KiB). This caps traffic delivered through the namespace's tunnel,
not bytes already received/billed by the provider or encrypted transport overhead.
Existing host-side proxychains workloads do not traverse that interface: stop
them and use normal namespace execution. New `--proxychains` launches are refused
for limited profiles. Root administration and changes outside SplitForge can
override these controls; they are not a security boundary against the host owner.

در صفحهٔ کانفیگ‌ها روی **محدودیت سرعت** کلیک کنید و سقف دانلود و آپلود را به
مگابیت بر ثانیه وارد کنید؛ صفر یعنی نامحدود. سقف بین تمام برنامه‌های استفاده‌کننده
از کانفیگ مشترک است. دکمهٔ تنظیم سقف حجم، محدودیت تجمعی را به MiB تعیین می‌کند؛
مثلاً ۱۰۲۴۰ MiB برابر ۱۰ GiB است. هر دو محدودیت هم‌زمان قابل استفاده‌اند و با
راه‌اندازی مجدد حفظ می‌شوند. دانلود مازاد با حذف بسته محدود می‌شود و ممکن است
UDP داده از دست بدهد؛ این گزینه صورتحساب ارائه‌دهنده را محدود نمی‌کند. برنامه‌های
قدیمی proxychains را متوقف و با اجرای معمول در namespace راه‌اندازی کنید.

## Independent application counters

Managed system services enable systemd's
[`IPAccounting`](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html#IPAccounting=).
Each service cgroup counts its own IPv4/IPv6 sockets, including child processes
and local IP traffic. Two apps with the same Linux UID in the same network
namespace still have separate counters. App totals are not obtained by dividing
tunnel usage. Socket-activated adopted services are rejected by the existing
service adoption guard; sockets passed across unrelated services are attributed
according to the kernel's socket ownership, not guessed from process names.

The feature requires kernel cgroup/eBPF accounting support. An unavailable counter
is shown as unavailable, rather than a zero-byte measurement. Apply/reapply an
app's route after upgrading so its unit receives the accounting settings and
startup/final-sample hooks. Tunnel upgrades likewise recreate an activation ID
to distinguish new interface counters from earlier runs.

Tunnel graphs read the actual tunnel interface counters and include shared
encrypted DNS/protocol traffic. They need not equal the sum of per-app socket
counters. Unregistered host processes and anonymous one-off `splitforge exec`
commands are not assigned fictional per-app totals; their tunnel traffic still
appears in that tunnel's interface counters.

## Set a budget

Choose **Set budget**, enter a limit in MiB and a warning percentage (1–99).
Zero disables the budget. The default warning is 80%. Applications must have
produced a verified counter reading before a limit can be enabled. Profile
budgets can also be saved before the first start; missing live accounting then
stops the limited profile. Profile cards have a **Set budget** shortcut.

```sh
sudo splitforge traffic enable
sudo splitforge traffic status
sudo splitforge traffic quota my-worker --mib 1024 --warning 80
sudo splitforge traffic quota my-tunnel --kind profile --mib 4096
sudo splitforge traffic quota my-worker --reset
sudo splitforge traffic quota my-worker --disable
```

Budgets use a manual usage period, beginning when first enabled or explicitly
reset. Changing routes or restarting does not reset that period. The rate graph
retains the latest 120 observations (normally about ten minutes); cumulative
usage and budgets persist in `STATE_PATH.traffic.json`, mode 0600. Invocation
high-water marks prevent duplicate/stale samples from being counted twice.
Final app counters are collected by `ExecStopPost`; tunnel counters are saved
before namespace destruction. Encrypted configuration backups include these
records, and installation rollback restores the matching traffic snapshot.

### Enforcement and recovery

The volume budget is a **sampled stop budget**, separate from the speed limits
below. The collector normally samples every five seconds. Detection, service
shutdown, busy hosts or bursts can cause overshoot; this is unsuitable for
enforcing a carrier's exact billable byte limit. Abrupt host crashes can lose
usage since the last durable sample. Counter totals measure IP traffic, rather
than application payload sizes or a provider's billing algorithm.

An exhausted app is stopped with its enabled intent cleared. An exhausted tunnel
is stopped and cannot be started until its budget is reset, disabled or increased.
Apps with a backup policy may switch to another healthy tunnel; the app's own
budget continues across that switch. A startup `ExecCondition` also prevents
bypassing an exhausted app budget by directly restarting its generated unit.
Quota-protected startup requires a running collector and usable native counters.

Missing accounting while a limited target is running stops that target. Invalid
quota storage fails closed; it does not silently remove limits. Warnings and
blocked reasons appear in **Budget alerts**. Resetting/increasing a budget permits
an explicit restart; it does not automatically start a workload. Keep the traffic
registry root-controlled and use a valid backup if it becomes corrupt.

Snapshots restore the usage/budget state **as of that snapshot**. Restoring an old
backup intentionally replaces later observations; this is an administrator
recovery tool, not a tamper-proof billing ledger. A stopped collector is shown in
the panel, and old readings are labelled separately from current counters.

## فارسی

در صفحهٔ **مصرف و سقف ترافیک** نمودار و مصرف هر برنامه و هر تونل جداگانه نمایش
داده می‌شود. برنامه‌های ثبت‌شده، حتی با کاربر root و داخل یک تونل مشترک، شمارندهٔ
مستقل کرنل دارند. ترافیک تونل شامل DNS و سربار مشترک است و لزوماً با جمع مصرف
برنامه‌ها برابر نیست. پشتیبانی cgroup/eBPF کرنل لازم است؛ مقدار ناموجود به‌جای
عدد صفر نمایش داده می‌شود.

با **تنظیم سقف مصرف** مقدار مِبی‌بایت و درصد هشدار را مشخص کنید. دورهٔ مصرف با
ری‌استارت یا تغییر تونل صفر نمی‌شود؛ گزینهٔ شروع دورهٔ جدید آن را از نو آغاز
می‌کند. شمارنده‌ها و تنظیمات ذخیره می‌شوند و در پشتیبان رمزگذاری‌شده هم قرار
می‌گیرند. بعد از آپدیت، مسیر برنامه یا تونل را دوباره اعمال کنید تا قابلیت‌های
شمارش جدید فعال شوند.

اعمال سقف با نمونه‌برداری و توقف انجام می‌شود؛ محدودیت دقیقِ تک‌تک بسته‌ها یا
شکل‌دهی سرعت نیست. معمولاً هر ۵ ثانیه بررسی می‌شود و قبل از توقف ممکن است مصرف
از سقف عبور کند. برای محدودیت دقیق صورتحساب سرویس‌دهنده به آن تکیه نکنید.
در رسیدن به سقف، برنامه یا تونل متوقف می‌شود؛ برای اجرا باید دوره را بازنشانی
کنید یا سقف را افزایش/غیرفعال کنید و سپس دستی آن را شروع کنید. تغییر تونل
پشتیبان، سقف خود برنامه را دور نمی‌زند. بستن پنل، پایشگر دائمی را متوقف نمی‌کند.
