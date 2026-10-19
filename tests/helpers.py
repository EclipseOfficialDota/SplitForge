"""Local verified-TLS/DoH fixture: no public Internet or real VPN credentials."""
import http.server
import socket
import ssl
import struct
import subprocess
import threading


class TLSFixture:
    def __init__(self, directory):
        self.directory = directory

    def __enter__(self):
        self.cert = self.directory / "fixture-ca.pem"
        key = self.directory / "fixture-key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=dns.splitforge.test", "-addext",
            "subjectAltName=DNS:dns.splitforge.test,DNS:probe.splitforge.test,IP:127.0.0.1",
            "-keyout", str(key), "-out", str(self.cert)], capture_output=True, check=True)

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                data = (b'x' * min(int(self.path.rsplit('/', 1)[-1]), 1048576)
                        if self.path.startswith('/bytes/') else b"ip=192.0.2.80\nloc=ZZ\n")
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (ConnectionError, ssl.SSLError):
                    pass  # Quota integration deliberately closes active connections.

            def do_POST(self):
                query = self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 4096))
                if len(query) < 12:
                    self.send_error(400)
                    return
                end = 12
                while end < len(query) and query[end]:
                    end += query[end] + 1
                end += 1
                qtype = struct.unpack("!H", query[end:end + 2])[0]
                question = query[12:end + 4]
                answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + socket.inet_aton("192.0.2.80") if qtype == 1 else b""
                data = query[:2] + struct.pack("!HHHHH", 0x8180, 1, int(bool(answer)), 0, 0) + question + answer
                self.send_response(200)
                self.send_header("Content-Type", "application/dns-message")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def configure(self, profile):
        profile.doh_url = "https://dns.splitforge.test/dns-query"
        profile.doh_ip = "192.0.2.53"
        profile.probe_url = "https://probe.splitforge.test/trace"
        profile.tls_ca_file = str(self.cert)
        return profile

    def vpn_certificate(self, name, usage):
        key, csr, cert, extensions = [self.directory / (name + suffix) for suffix in ('.key', '.csr', '.crt', '.ext')]
        extensions.write_text(f'basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage={usage}\n')
        subprocess.run(['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-subj', f'/CN={name}',
                        '-keyout', str(key), '-out', str(csr)], capture_output=True, check=True)
        subprocess.run(['openssl', 'x509', '-req', '-in', str(csr), '-CA', str(self.cert),
                        '-CAkey', str(self.directory / 'fixture-key.pem'), '-CAcreateserial', '-days', '1',
                        '-extfile', str(extensions), '-out', str(cert)], capture_output=True, check=True)
        return cert, key
