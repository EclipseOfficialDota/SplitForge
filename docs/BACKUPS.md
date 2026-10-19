# Encrypted backups and version recovery / پشتیبان و بازیابی

[README](../README.md) · [Web panel](WEB_PANEL.md) · [فارسی](README.fa.md)

## Export and inspect

The web panel's **Security & DNS** page exports a password-encrypted `.sfb`
download. A completed export offers **Download encrypted backup**. Only an
authenticated administrator can download it. The latest six exports remain in
server memory until restart; keep the downloaded file and its password separately.

The CLI also works without the panel:

```sh
sudo splitforge backup export /root/splitforge.sfb
sudo splitforge backup inspect /root/splitforge.sfb
```

Passwords are entered without echo; export asks twice. For unattended use,
`--password-file /root/backup-password` accepts a regular file owned by the
invoking user with mode 0600. Passwords are never command arguments. Use a long,
unique passphrase; there is no password recovery. Minimum length is 12 UTF-8
bytes, maximum 1024. The browser requires at least 12 characters.

The archive contains profile credentials/configuration, app command/user/cwd and
routes, DNS/failover policy, future user-manager bindings, public custom CA
certificates and saved web address/port settings. It does **not** contain scripts,
application data/venvs, original adopted service definitions, Linux accounts,
external VPN servers, web login tokens, ACME accounts or TLS private keys. Prepare
those separately on a replacement server. Custom CA bundles are restored under
`/etc/ssl/splitforge`, rather than writing arbitrary source paths.

The format uses [cryptography AESGCM](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM)
with a 256-bit key derived using [Scrypt](https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#scrypt)
(`N=131072, r=8, p=1`), a fresh 16-byte salt and 12-byte nonce for every archive,
and authenticated format metadata. Corruption or a wrong password fails before
resources change. Plaintext is limited to 8 MiB; encrypted browser uploads to
16 MiB. Exported CLI files and recovery files have mode 0600.

## Restore configuration

Inspect the backup first. It contains command definitions that may execute as
root; restore only backups you trust. Stop other administrators/automation from
changing configuration during maintenance. The panel serializes its own jobs;
update/rollback serialize against each other, not arbitrary external root tools.

```sh
sudo splitforge backup restore /root/splitforge.sfb
# After reviewing the imported commands, start saved enabled workloads:
sudo splitforge restore
# Or explicitly combine trusted restoration and startup:
sudo splitforge backup restore /root/splitforge.sfb --start
```

Restore replaces current registrations and stops/removes their owned units and
networks. It first writes an encrypted recovery archive under
`/var/backups/splitforge`, using the supplied password. With `--start`, an
activation failure attempts to restore the previous configuration/workloads;
if recovery itself fails the error identifies the retained archive. The default
and web-panel restore leave imported workloads stopped. Recreate missing users,
scripts and original services before restoration; adopted protected SSH/network
services cannot be restored as routed applications. Existing connections close.

Current web access and its token are retained. Saved web settings are written to
`restored-web.json` beside the state file. To explicitly redeploy those settings:

```sh
sudo splitforge backup restore /root/splitforge.sfb --web-settings --agree-tos
```

That may change the public address/ports, restart the panel and issue certificates
for the saved address. Use SSH and verify the domain/IP still belongs to this
server. `--agree-tos` is required for HTTPS certificate issuance. The current token
file is retained; certificates are issued through the normal transactional setup.

## Return to the pre-update version

`splitforge update` snapshots the **entire previous venv**, matching state, web
configuration and revision before installation. Snapshots are local, private
recovery copies: their JSON is **not password-encrypted**. Keep `/var/backups`
root-controlled and create a separate encrypted export for portable storage.

```sh
sudo splitforge update
sudo splitforge rollback --list
sudo splitforge rollback --backup update-REPLACE_WITH_ACTUAL_ID
```

Without `--backup`, rollback selects the latest matching installation snapshot.
It asks for confirmation unless `--yes` is provided. Custom installs use
`--prefix /opt/my-splitforge`; global custom `--state` must precede the command.
Only snapshots matching **both** installation prefix and state path are offered.

Rollback stops managed workloads, restores the old venv at its original path
(preserving console-script shebangs), restores the matching old state/revision,
and starts saved enabled assignments. Configuration changes made after that
snapshot are replaced. It snapshots the current installation first, so it can
recover it if old-version activation fails. An active web service belonging to
that prefix is restarted after successful maintenance; other installations are
not restarted. SSH and host routes are not reset.

The rollback is for installer-managed Python code/configuration. It does not
downgrade OS packages, kernels or separately installed tunnel cores, and does not
restore workload data. Keep enough disk space for environment copies. Snapshots
are retained until the administrator removes obsolete ones; there is no automatic
retention/deletion policy. Versions installed before this feature need one new
`splitforge update` to create a complete rollback snapshot.

## فارسی

در **امنیت و DNS** با یک رمز طولانی خروجی رمزگذاری‌شده بسازید و سپس دکمهٔ دانلود
را بزنید. رمز قابل بازیابی نیست؛ آن را جدا از فایل نگه دارید. فرمان‌های
`splitforge backup export`، `inspect` و `restore` نیز در دسترس‌اند و رمز را مخفی
دریافت می‌کنند. رمز یا توکن را در خط فرمان ننویسید.

بازیابی وب، ثبت‌های فعلی را جایگزین و برنامه‌ها را متوقف می‌کند؛ فرمان‌های فایل
ورودی خودکار اجرا نمی‌شوند. پس از بررسی آن‌ها، `sudo splitforge restore` را اجرا
کنید. `backup restore --start` اجرای هم‌زمان را صریحاً درخواست می‌کند. قبل از تغییر،
پشتیبان رمزگذاری‌شدهٔ تنظیمات فعلی با همان رمز ساخته می‌شود. فایل‌های اسکریپت،
دادهٔ برنامه‌ها، کاربران لینوکس و تعریف اصلی سرویس‌ها را باید جداگانه تهیه کنید.

دسترسی فعلی پنل حفظ می‌شود. برای اعمال آدرس و پورت ذخیره‌شده، از طریق SSH گزینهٔ
`--web-settings` را استفاده کنید؛ صدور گواهی HTTPS به `--agree-tos` نیاز دارد.

قبل از آپدیت، نسخهٔ قبلی محیط پایتون و تنظیمات به‌صورت خصوصی روی سرور ذخیره
می‌شود. این کپی محلی رمزگذاری‌شده نیست و فقط برای root در دسترس است. برای خروجی
قابل‌انتقال، پشتیبان رمزگذاری‌شدهٔ مستقل بسازید. با `splitforge rollback --list`
شناسه‌ها را ببینید و با `splitforge rollback --backup ID` نسخه و تنظیمات همان زمان
را برگردانید. برنامه‌ها دوباره اجرا می‌شوند و تغییرات تنظیماتِ بعد از آن نسخه
جایگزین می‌شوند. هسته‌های شبکه و بسته‌های سیستم‌عامل دانگرید نمی‌شوند.
