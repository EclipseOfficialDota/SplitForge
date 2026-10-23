"""Authenticated multipath TCP streams over independent SOCKS tunnel paths.

Each application stream has its own ordered, acknowledged sliding window.
Frames survive an individual path loss; there is no direct network fallback.
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import ipaddress
import json
import secrets
import socket
import struct
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.exceptions import InvalidTag

MAGIC = b'SFB1'
HEADER = struct.Struct('!BII')
CHUNK = 4096
WINDOW = 32
MAX_STREAMS = 64
OPEN, DATA, FIN, ACK, RESET, READY, PING, PONG = range(1, 9)


def token_bytes(token):
    if not isinstance(token, str) or len(token) != 64:
        raise ValueError('Bond relay token must be 32 random bytes encoded as hex')
    try:
        decoded = bytes.fromhex(token)
        if len(decoded) != 32:
            raise ValueError('Invalid token length')
        return decoded
    except ValueError:
        raise ValueError('Invalid bond relay token') from None


async def read_exact(reader, size):
    return await asyncio.wait_for(reader.readexactly(size), 45)


async def socks_connect(host, port, target, target_port):
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, limit=16384), 15)
    try:
        writer.write(b'\x05\x01\x00')
        await writer.drain()
        if await read_exact(reader, 2) != b'\x05\x00':
            raise ValueError('Member SOCKS proxy must accept local no-auth connections')
        encoded = target.encode('idna')
        if not 1 <= len(encoded) <= 253:
            raise ValueError('Invalid relay hostname')
        writer.write(b'\x05\x01\x00\x03' + bytes([len(encoded)]) + encoded + struct.pack('!H', target_port))
        await writer.drain()
        version, result, reserved, address_type = await read_exact(reader, 4)
        if version != 5 or result or reserved:
            raise ConnectionError('Member tunnel could not reach the aggregation relay')
        size = {1: 4, 4: 16}.get(address_type)
        if address_type == 3:
            size = (await read_exact(reader, 1))[0]
        if size is None:
            raise ValueError('Invalid SOCKS response')
        await read_exact(reader, size + 2)
        return reader, writer
    except BaseException:
        writer.close()
        raise


async def authenticate(reader, writer, token, *, session=None, server_epoch=None):
    key = token_bytes(token)
    if session is not None:
        client_nonce = secrets.token_bytes(32)
        hello = MAGIC + session + client_nonce
        writer.write(hello + hmac.digest(key, b'client' + hello, 'sha256'))
        await writer.drain()
        response = await read_exact(reader, 80)
        server_nonce = response[:32]
        epoch = response[32:48]
        if not hmac.compare_digest(response[48:], hmac.digest(key, b'server' + hello + server_nonce + epoch, 'sha256')):
            raise ValueError('Aggregation relay authentication failed')
        client = True
    else:
        hello = await read_exact(reader, 84)
        if hello[:4] != MAGIC or not hmac.compare_digest(hello[52:], hmac.digest(key, b'client' + hello[:52], 'sha256')):
            raise ValueError('Aggregation client authentication failed')
        session, client_nonce = hello[4:20], hello[20:52]
        server_nonce = secrets.token_bytes(32)
        epoch = server_epoch or secrets.token_bytes(16)
        writer.write(server_nonce + epoch + hmac.digest(key, b'server' + hello[:52] + server_nonce + epoch, 'sha256'))
        await writer.drain()
        client = False
    material = HKDF(algorithm=SHA256(), length=64, salt=client_nonce + server_nonce, info=MAGIC).derive(key)
    outgoing, incoming = (material[:32], material[32:]) if client else (material[32:], material[:32])
    return session, ChaCha20Poly1305(outgoing), ChaCha20Poly1305(incoming), epoch


class Lane:
    def __init__(self, mux, reader, writer, outgoing, incoming, name):
        self.mux, self.reader, self.writer = mux, reader, writer
        self.outgoing, self.incoming, self.name = outgoing, incoming, name
        self.tx_counter = self.rx_counter = 0
        self.sent = self.received = self.outstanding = 0
        self.alive = True
        self.lock = asyncio.Lock()

    async def send(self, kind, stream, sequence=0, payload=b''):
        if not self.alive:
            raise ConnectionError('Bond path is down')
        async with self.lock:
            nonce = self.tx_counter.to_bytes(12, 'big')
            encrypted = self.outgoing.encrypt(nonce, HEADER.pack(kind, stream, sequence) + payload, MAGIC)
            self.tx_counter += 1
            self.writer.write(struct.pack('!I', len(encrypted)) + encrypted)
            await asyncio.wait_for(self.writer.drain(), 30)
            self.sent += len(payload)

    async def run(self):
        self.mux.lanes.add(self)
        self.mux.changed.set()
        try:
            while True:
                length = struct.unpack('!I', await read_exact(self.reader, 4))[0]
                if not HEADER.size + 16 <= length <= HEADER.size + CHUNK + 16:
                    raise ValueError('Invalid bond frame length')
                encrypted = await read_exact(self.reader, length)
                plain = self.incoming.decrypt(self.rx_counter.to_bytes(12, 'big'), encrypted, MAGIC)
                self.rx_counter += 1
                kind, stream, sequence = HEADER.unpack(plain[:HEADER.size])
                payload = plain[HEADER.size:]
                self.received += len(payload)
                await self.mux.receive(self, kind, stream, sequence, payload)
        finally:
            self.alive = False
            self.mux.lanes.discard(self)
            self.writer.close()
            for stream in self.mux.streams.values():
                for frame in stream.pending.values():
                    if frame.lane is self:
                        frame.lane = None
            self.mux.changed.set()


@dataclass
class Pending:
    kind: int
    payload: bytes
    lane: Lane | None = None
    sent: float = 0


class Stream:
    def __init__(self, mux, identifier, reader=None, writer=None):
        self.mux, self.id, self.reader, self.writer = mux, identifier, reader, writer
        self.next_tx = self.next_rx = 0
        self.pending, self.reorder = {}, {}
        self.rx_lock = asyncio.Lock()
        self.ready = asyncio.Event()
        self.closed = self.sent_fin = self.received_fin = False
        self.error = ''
        self.task = None

    async def send(self, kind, payload=b''):
        deadline = time.monotonic() + 90
        while len(self.pending) >= WINDOW:
            if self.closed or time.monotonic() > deadline:
                raise ConnectionError('Bond stream is closed or stalled')
            await self.mux.wait_change()
        if self.closed or self.next_tx >= 2**32:
            raise ConnectionError('Bond stream closed')
        sequence = self.next_tx
        self.next_tx += 1
        self.pending[sequence] = Pending(kind, payload)
        self.mux.changed.set()

    async def pump(self):
        try:
            while not self.closed:
                payload = await self.reader.read(CHUNK)
                await self.send(DATA if payload else FIN, payload)
                if not payload:
                    self.sent_fin = True
                    return
        except (ConnectionError, OSError, asyncio.TimeoutError):
            await self.abort('Application connection failed')

    async def abort(self, message, *, notify=True):
        if self.closed:
            return
        self.error, self.closed = message, True
        self.ready.set()
        for frame in self.pending.values():
            if frame.lane:
                frame.lane.outstanding = max(0, frame.lane.outstanding - 1)
        self.pending.clear()
        self.reorder.clear()
        if self.writer:
            self.writer.close()
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
        self.mux.streams.pop(self.id, None)
        self.mux.finished[self.id] = None if message else self.next_rx
        while len(self.mux.finished) > 2048:
            del self.mux.finished[next(iter(self.mux.finished))]
        self.mux.changed.set()
        if notify:
            await self.mux.control(RESET, self.id)


class Mux:
    def __init__(self, *, relay=False, allow_private=False):
        self.relay, self.allow_private = relay, allow_private
        self.lanes, self.streams, self.finished = set(), {}, {}
        self.changed = asyncio.Event()
        self.counter = 0
        self.closed = False
        self.last_lane = time.monotonic()
        self.cursor = 0
        self.remote_epoch = None

    async def accept_epoch(self, epoch):
        if self.remote_epoch is not None and self.remote_epoch != epoch:
            # A restarted relay cannot recover the original destination TCP
            # sockets. Close old app streams, rather than silently replaying them.
            for stream in list(self.streams.values()):
                await stream.abort('Destination relay restarted; reconnect the application', notify=False)
            for lane in list(self.lanes):
                lane.writer.close()
        self.remote_epoch = epoch

    async def wait_change(self):
        self.changed.clear()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self.changed.wait(), 0.1)

    async def control(self, kind, stream=0, sequence=0):
        for lane in sorted(self.lanes, key=lambda item: item.outstanding):
            try:
                await lane.send(kind, stream, sequence)
                return
            except (OSError, ConnectionError, asyncio.TimeoutError):
                lane.writer.close()

    async def target(self, payload):
        host, port = json.loads(payload)
        if not isinstance(host, str) or len(host) > 253 or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid aggregation target')
        addresses = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM), 15)
        candidates = [item[4][0] for item in addresses]
        if not candidates or (not self.allow_private and any(not ipaddress.ip_address(ip).is_global for ip in candidates)):
            raise ValueError('Aggregation relay permits public IPv4 targets only')
        return await asyncio.wait_for(asyncio.open_connection(candidates[0], port, limit=16384), 15)

    async def receive(self, lane, kind, identifier, sequence, payload):
        if kind in (PING, PONG):
            if identifier or payload:
                raise ValueError('Invalid heartbeat')
            if kind == PING:
                await lane.send(PONG, 0)
            return
        if not identifier or kind not in (OPEN, DATA, FIN, ACK, RESET, READY):
            raise ValueError('Invalid bond message')
        stream = self.streams.get(identifier)
        if kind == RESET:
            if stream:
                await stream.abort('Remote stream reset', notify=False)
            return
        if stream is None:
            if identifier in self.finished:
                if kind != ACK:
                    completed = self.finished[identifier]
                    await self.control(ACK if completed is not None else RESET, identifier, completed or 0)
                return
            if not self.relay or kind in (ACK, READY) or len(self.streams) >= MAX_STREAMS or identifier <= self.counter - 2048:
                await self.control(RESET, identifier)
                return
            stream = Stream(self, identifier)
            self.streams[identifier] = stream
            self.counter = max(self.counter, identifier)
        if kind == ACK:
            if payload or sequence > stream.next_tx:
                raise ValueError('Invalid acknowledgement')
            for number in list(stream.pending):
                if number < sequence:
                    frame = stream.pending.pop(number)
                    if frame.lane:
                        frame.lane.outstanding = max(0, frame.lane.outstanding - 1)
            self.changed.set()
        else:
            async with stream.rx_lock:
                if sequence < stream.next_rx:
                    await self.control(ACK, identifier, stream.next_rx)
                    return
                if sequence >= stream.next_rx + WINDOW:
                    raise ValueError('Bond reorder window exceeded')
                old = stream.reorder.get(sequence)
                if old is not None and old != (kind, payload):
                    raise ValueError('Conflicting bond frame')
                stream.reorder[sequence] = kind, payload
                while stream.next_rx in stream.reorder and not stream.closed:
                    current_kind, current_payload = stream.reorder.pop(stream.next_rx)
                    try:
                        if current_kind == OPEN and self.relay and stream.next_rx == 0:
                            stream.reader, stream.writer = await self.target(current_payload)
                            await stream.send(READY)
                            stream.task = asyncio.create_task(stream.pump())
                        elif current_kind == READY and not self.relay and stream.next_rx == 0 and not current_payload:
                            stream.ready.set()
                        elif current_kind == DATA and stream.writer and not stream.received_fin:
                            stream.writer.write(current_payload)
                            await asyncio.wait_for(stream.writer.drain(), 30)
                        elif current_kind == FIN and stream.writer and not current_payload and not stream.received_fin:
                            stream.received_fin = True
                            if stream.writer.can_write_eof():
                                stream.writer.write_eof()
                        else:
                            raise ValueError('Invalid bond stream state')
                        stream.next_rx += 1
                    except (OSError, ConnectionError, ValueError, asyncio.TimeoutError):
                        await stream.abort('Aggregation target or stream failed')
                        return
                await self.control(ACK, identifier, stream.next_rx)
        if stream.sent_fin and stream.received_fin and not stream.pending:
            await stream.abort('', notify=False)

    async def schedule(self):
        heartbeat = 0
        try:
            while not self.closed:
                now = time.monotonic()
                if self.lanes:
                    self.last_lane = now
                elif now - self.last_lane > 90:
                    for stream in list(self.streams.values()):
                        await stream.abort('All aggregation paths are unavailable', notify=False)
                streams = list(self.streams.values())
                if streams:
                    self.cursor = (self.cursor + 1) % len(streams)
                    streams = streams[self.cursor:] + streams[:self.cursor]
                for stream in streams:
                    for sequence, frame in list(stream.pending.items()):
                        if frame.lane and frame.lane.alive and now - frame.sent < 15:
                            continue
                        choices = [lane for lane in self.lanes if lane.alive and lane.outstanding < 4]
                        if not choices:
                            continue
                        selected = min(choices, key=lambda lane: (lane.outstanding, lane.sent))
                        if frame.lane:
                            frame.lane.outstanding = max(0, frame.lane.outstanding - 1)
                        frame.lane, frame.sent = selected, now
                        selected.outstanding += 1
                        try:
                            await selected.send(frame.kind, stream.id, sequence, frame.payload)
                        except (OSError, ConnectionError, asyncio.TimeoutError):
                            selected.writer.close()
                            frame.lane = None
                if now - heartbeat >= 10:
                    heartbeat = now
                    # Each lane needs its own heartbeat to detect a black hole.
                    for lane in list(self.lanes):
                        try:
                            await lane.send(PING, 0)
                        except (OSError, ConnectionError, asyncio.TimeoutError):
                            lane.writer.close()
                await self.wait_change()
        finally:
            for stream in list(self.streams.values()):
                await stream.abort('Aggregation stopped', notify=False)
            for lane in list(self.lanes):
                lane.writer.close()

    async def socks(self, reader, writer):
        stream = None
        try:
            version, count = await read_exact(reader, 2)
            methods = await read_exact(reader, count)
            if version != 5 or 0 not in methods:
                raise ValueError('SOCKS5 no-auth required')
            writer.write(b'\x05\x00')
            await writer.drain()
            version, command, reserved, address_type = await read_exact(reader, 4)
            if version != 5 or command != 1 or reserved:
                raise ValueError('Aggregation supports TCP CONNECT only')
            if address_type == 1:
                host = socket.inet_ntoa(await read_exact(reader, 4))
            elif address_type == 3:
                host = (await read_exact(reader, (await read_exact(reader, 1))[0])).decode('ascii')
            else:
                raise ValueError('Aggregation supports IPv4 and DNS targets')
            port = struct.unpack('!H', await read_exact(reader, 2))[0]
            if len(self.streams) >= MAX_STREAMS or self.counter >= 2**32 - 1:
                raise ValueError('Aggregation stream capacity reached')
            self.counter += 1
            stream = Stream(self, self.counter, reader, writer)
            self.streams[stream.id] = stream
            await stream.send(OPEN, json.dumps([host, port]).encode())
            await asyncio.wait_for(stream.ready.wait(), 45)
            if stream.error:
                raise ConnectionError(stream.error)
            writer.write(b'\x05\x00\x00\x01' + b'\x00' * 6)
            await writer.drain()
            stream.task = asyncio.current_task()
            await stream.pump()
        except (OSError, ValueError, ConnectionError, asyncio.TimeoutError, asyncio.IncompleteReadError, InvalidTag):
            if not writer.is_closing():
                writer.write(b'\x05\x01\x00\x01' + b'\x00' * 6)
            if stream:
                await stream.abort('Aggregation connection failed')
            else:
                writer.close()


class Relay:
    def __init__(self, token, *, allow_private=False):
        token_bytes(token)
        self.token, self.allow_private = token, allow_private
        self.epoch = secrets.token_bytes(16)
        self.sessions = {}
        self.handshakes = 0

    async def accept(self, reader, writer):
        mux = None
        pending_handshake = True
        self.handshakes += 1
        try:
            if self.handshakes > 32:
                raise ConnectionError('Relay handshake capacity reached')
            session, outgoing, incoming, _ = await authenticate(reader, writer, self.token, server_epoch=self.epoch)
            self.handshakes -= 1
            pending_handshake = False
            if session not in self.sessions:
                if len(self.sessions) >= 8:
                    raise ConnectionError('Relay session capacity reached')
                mux = Mux(relay=True, allow_private=self.allow_private)
                task = asyncio.create_task(mux.schedule())
                self.sessions[session] = mux, task
            mux = self.sessions[session][0]
            if len(mux.lanes) >= 8:
                raise ConnectionError('Relay path capacity reached')
            await Lane(mux, reader, writer, outgoing, incoming, 'relay').run()
        except (OSError, ValueError, ConnectionError, asyncio.TimeoutError, asyncio.IncompleteReadError, InvalidTag):
            pass
        finally:
            if pending_handshake:
                self.handshakes -= 1
            writer.close()
            if mux and not mux.lanes:
                await asyncio.sleep(95)
                if not mux.lanes and self.sessions.get(session, (None,))[0] is mux:
                    mux.closed = True
                    self.sessions.pop(session)[1].cancel()


async def client(config):
    mux = Mux()
    session = secrets.token_bytes(16)
    token_bytes(config['token'])
    members = config['members']
    if not isinstance(members, list) or not 2 <= len(members) <= 8:
        raise ValueError('Select 2–8 independent aggregation member tunnels')

    async def connect(member):
        while True:
            writer = None
            try:
                reader, writer = await socks_connect(member['host'], member['port'], config['relay_host'], config['relay_port'])
                _, outgoing, incoming, epoch = await authenticate(reader, writer, config['token'], session=session)
                await mux.accept_epoch(epoch)
                await Lane(mux, reader, writer, outgoing, incoming, member['id']).run()
            except (OSError, ValueError, ConnectionError, asyncio.TimeoutError, asyncio.IncompleteReadError, InvalidTag):
                await asyncio.sleep(2)
            finally:
                if writer:
                    writer.close()

    tasks = [asyncio.create_task(connect(member)) for member in members]
    tasks.append(asyncio.create_task(mux.schedule()))
    async def report():
        from pathlib import Path
        from splitforge.core.netns import atomic_secret
        while True:
            if config.get('status_path'):
                data = {'updated': time.time(), 'paths': len(mux.lanes), 'streams': len(mux.streams),
                        'members': [{'id': lane.name, 'sent': lane.sent, 'received': lane.received} for lane in mux.lanes]}
                atomic_secret(Path(config['status_path']), json.dumps(data))
            await asyncio.sleep(2)
    tasks.append(asyncio.create_task(report()))
    try:
        deadline = time.monotonic() + 90
        while len(mux.lanes) < 2:
            if time.monotonic() > deadline:
                raise TimeoutError('At least two authenticated relay paths must be reachable')
            await mux.wait_change()
        server = await asyncio.start_server(mux.socks, '127.0.0.1', config['listen_port'], limit=16384)
        async with server:
            await server.serve_forever()
    finally:
        mux.closed = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def setup_relay():
    """Install only the local, authenticated aggregation endpoint."""
    import sys
    import stat
    from pathlib import Path
    from splitforge.core.netns import atomic_secret, require_root, run, unit_word
    require_root()
    path = Path('/etc/splitforge/relay.json')
    if path.exists():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
            raise ValueError('Existing relay configuration must be root-owned and private')
        config = json.loads(path.read_text())
        token_bytes(config['token'])
    else:
        atomic_secret(path, json.dumps({'token': secrets.token_hex(32), 'listen_host': '127.0.0.1', 'listen_port': 28443}))
    unit = Path('/etc/systemd/system/splitforge-bond-relay.service')
    marker = '# SplitForge authenticated aggregation relay\n'
    if unit.exists() and not unit.read_text().startswith(marker):
        raise ValueError('Refusing to replace an unrelated relay service')
    content = marker + f'''[Unit]
Description=SplitForge authenticated multipath relay
After=network-online.target
Wants=network-online.target
[Service]
DynamicUser=yes
LoadCredential=relay.json:{path}
ExecStart={unit_word(sys.executable)} -m splitforge.core.bond relay --config %d/relay.json
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
CapabilityBoundingSet=
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0077
[Install]
WantedBy=multi-user.target
'''
    atomic_secret(unit, content, 0o644)
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', unit.name])
    run(['systemctl', 'restart', unit.name])
    async def verify():
        config = json.loads(path.read_text())
        for _ in range(30):
            writer = None
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(config.get('listen_host', '127.0.0.1'), config.get('listen_port', 28443)), 2)
                await authenticate(reader, writer, config['token'], session=secrets.token_bytes(16))
                return
            except (OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError):
                await asyncio.sleep(.2)
            finally:
                if writer:
                    writer.close()
        raise RuntimeError('Relay service did not become ready; inspect journalctl -u splitforge-bond-relay')
    asyncio.run(verify())
    print('Aggregation relay installed on 127.0.0.1:28443; no public port was opened.')
    print('Private join settings: /etc/splitforge/relay.json (read on this server only).')


def main():
    import argparse
    import os
    import stat
    from pathlib import Path
    parser = argparse.ArgumentParser(description='SplitForge authenticated TCP aggregation')
    parser.add_argument('action', choices=['client', 'relay', 'setup'])
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    if args.action == 'setup':
        setup_relay()
        return
    if args.config is None:
        parser.error('--config is required')
    info = args.config.lstat()
    credential_dir = os.environ.get('CREDENTIALS_DIRECTORY')
    credential = (credential_dir and args.config.parent == Path(credential_dir)
                  and args.config.name == 'relay.json' and info.st_uid == 0
                  and stat.S_IMODE(info.st_mode) == 0o440
                  and args.config.parent.is_relative_to('/run/credentials'))
    private = info.st_uid == os.geteuid() and not info.st_mode & 0o077
    if not stat.S_ISREG(info.st_mode) or not (private or credential) or info.st_size > 32768:
        raise ValueError('Bond configuration must be a private owned regular file')
    config = json.loads(args.config.read_text())
    token_bytes(config['token'])
    async def serve():
        if args.action == 'client':
            await client(config)
        else:
            relay = Relay(config['token'])
            server = await asyncio.start_server(relay.accept, config.get('listen_host', '127.0.0.1'), config.get('listen_port', 28443), limit=16384)
            async with server:
                await server.serve_forever()
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
