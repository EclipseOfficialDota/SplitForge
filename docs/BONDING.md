# Real DNS tunnel aggregation / تجمیع واقعی تونل‌ها

[README](../README.md) · [Web panel](WEB_PANEL.md) · [Traffic limits](TRAFFIC.md)

An ordinary load balancer distributes separate connections. SplitForge's **bond**
profile instead stripes frames of each TCP connection across 2–8 independent
proxy tunnel paths and reconstructs the stream at an authenticated destination
relay. Apps select the bond just like any other profile. DNSTT, NoizDNS and
Slipstream can participate together, provided their remote SOCKS backends can
reach **the same relay instance**.

## 1. Install on the destination tunnel server

This is the server running dnstm/DNSTT/NoizDNS/Slipstream, not the client VPS
where applications run. You can install it yourself without sharing SSH access.

```sh
curl -fsSL https://raw.githubusercontent.com/EclipseOfficialDota/SplitForge/master/install-relay.sh -o /tmp/splitforge-install-relay.sh
sudo bash /tmp/splitforge-install-relay.sh
sudo systemctl status splitforge-bond-relay --no-pager
```

The installer creates `/opt/splitforge-relay/venv`, installs cryptography and the
release wheel after checking its SHA-256, and starts a permanent systemd relay.
It does not run the main network installer, replace your DNS tunnel services,
change port 53, open a firewall port or alter the host routing table. Installation
requires Internet access for apt/pip and release downloads. The relay program
runs as a dynamic unprivileged systemd user with a private credential mount.

Default listener: **127.0.0.1:28443**. Your existing remote SOCKS proxy reaches
that address locally on the destination server; it need not be exposed publicly.
If the SOCKS service runs in a container or blocks localhost targets, configure
an address reachable from that service and narrowly restrict access yourself.
Do not point each path at a different independent relay process.

Read `/etc/splitforge/relay.json` privately on that server. Copy only the 64-hex
`token` value into the client form. The token authorizes relay use: never put it
in an issue, screenshot, source file or public log. Re-running setup keeps the
token and restarts the service; existing application connections must reconnect.

Already installed SplitForge on that destination? Alternatively run:

```sh
sudo splitforge bond relay-setup
```

## 2. Create the output on the application VPS

1. Upgrade SplitForge and install required client cores in **Core installer**.
2. Import/register the individual member profiles. The DNS wizards support
   DNSTT, NoizDNS and Slipstream, including optional remote SOCKS credentials.
   Each member must work by itself against its configured backend.
3. Open **Tunnel profiles → Create bonded output**. Select 2–8 members and enter
   the destination-local relay address (`127.0.0.1` normally), port `28443`, and
   private token from step 1.
4. Save and start the group. Initial startup requires two authenticated paths;
   the profile card reports the number of currently authenticated paths.
5. Assign the group to apps in **App router**. The normal namespace kill-switch,
   DNS protection and per-app route test apply to the shared output.

CLI alternative (the token file contains just the 64 hex characters, owned by
root and mode 0600; provision it privately):

```sh
sudo splitforge bond create combined-dns --member dns-one --member noiz-two --member slip-three --token-file /root/bond-token
sudo splitforge profile start combined-dns
sudo splitforge bind my-worker --profile combined-dns
```

Check `splitforge bind --help` for the registered application's identifier/name
and binding flags on your installed version. No token is passed on the CLI.

## Limits, accounting and failure behavior

- TCP only, including namespace HTTPS/DoH. App UDP is rejected; this does not
  create generic UDP support for DNS tunnel transports.
- A shared bottleneck may prevent any speed increase. Five independent 20 KiB/s
  paths have a theoretical sum of 100 KiB/s before framing, encryption and
  retransmission overhead. Different latency/loss can substantially reduce gain.
- Upload/download frames have per-stream sequence numbers, bounded windows,
  acknowledgements and duplicate suppression. An individual failed path's
  unacknowledged frames are resent over healthy paths. Reconnecting paths can
  rejoin the session; no route falls back to the server's direct Internet.
- A restarted relay loses its destination TCP sockets. Its authenticated epoch
  changes, so old application streams close and apps must reconnect; requests
  are not silently replayed as new destination connections.
- If every path remains unavailable, existing streams close after approximately
  90 seconds. Initial startup can take up to 100 seconds while waiting for paths.
- At most 64 concurrent application streams per bond, 8 paths per relay session
  and 8 relay sessions. These bounded resources suit low-throughput DNS tunnels;
  this is not an unlimited high-throughput datacenter bonding fabric.
- Set speed/volume caps on the **bonded output**. Member paths connect through
  their host-side SOCKS transports, so their TUN counters cannot account for that
  traffic. SplitForge refuses limited members and refuses new member caps while
  a group references them. Per-app systemd counters remain independent and the
  group's TUN totals/quotas include its apps. Path status counters are live lane
  observations, not persistent billable traffic totals.
- Member profiles cannot be removed while referenced. Stop/remove the group
  first (after unbinding its apps). Stopping a member for maintenance is allowed;
  stopping a group does not stop members that other workloads may use.
- Group settings and its relay join token live in private root-owned state and
  are included in encrypted configuration backups. The destination relay's own
  private configuration is separate; retain it on that server.

Transport authentication uses a random 256-bit shared token, nonce-based mutual
HMAC authentication and separately derived directional ChaCha20-Poly1305 keys.
The relay permits public IPv4 destinations only, rejecting loopback/private/
link-local destinations to protect the destination server. This protects the
aggregation stream independently of each underlying DNS transport.

NoizDNS is downloaded/built from pinned verified upstream source with its pinned
DNSTT companion; the third-party binaries retain their upstream licenses.
[NoizDNS](https://github.com/anonvector/noizdns) is AGPL-3.0. SplitForge invokes
the separately installed binary and does not relicense or embed its source.

## راهنمای فارسی

این قابلیت دادهٔ **یک اتصال TCP** را بین چند تونل تقسیم و در سرور مقصد مرتب
می‌کند؛ صرفاً اتصال‌های جداگانه را پخش نمی‌کند. در سرور مقصدی که dnstm روی آن
نصب است، دستورهای نصب بالا را خودتان اجرا کنید. سرویس به‌صورت پیش‌فرض فقط روی
`127.0.0.1:28443` گوش می‌دهد و از طریق SOCKS همان سرور قابل دسترسی است.

در VPS برنامه‌ها، هسته‌ها را نصب و کانفیگ‌های DNSTT، NoizDNS و Slipstream را
ثبت کنید. از صفحهٔ کانفیگ‌ها **ساخت خروجی تجمیعی** را بزنید، ۲ تا ۸ عضو و توکن
خصوصی مقصد را وارد کنید، گروه را راه‌اندازی و در App Router به برنامه‌ها وصل
کنید. تمام مسیرها باید به یک سرویس تجمیع مشترک برسند. توکن را عمومی نفرستید.

سقف سرعت و حجم را روی خود گروه بگذارید؛ مسیرهای عضو از پراکسی میزبان عبور
می‌کنند و شمارندهٔ TUN آن‌ها این مصرف را پوشش نمی‌دهد. محدودیت اعضا به همین
دلیل رد می‌شود. قطع یک مسیر باعث ارسال مجدد از مسیرهای سالم می‌شود؛ ری‌استارت
سرویس مقصد اتصال‌های قبلی برنامه را می‌بندد و اتصال مجدد لازم است. UDP پشتیبانی
نمی‌شود. جمع‌شدن سرعت به ظرفیت مستقل مسیرها وابسته است و تضمین پنج‌برابرشدن نیست.
