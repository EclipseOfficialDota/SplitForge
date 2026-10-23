"""Actual encrypted multi-lane, single TCP stream transport tests."""
import asyncio
import secrets
import time
import unittest

from splitforge.core.bond import Lane, Mux, Relay, authenticate, socks_connect, token_bytes


class BondTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tasks, self.servers, self.writers, self.muxes = [], [], [], []
        self.token = secrets.token_hex(32)
        self.relay = Relay(self.token, allow_private=True)
        self.relay_server = await self.listen(self.relay.accept)

    async def listen(self, handler):
        async def guarded(reader, writer):
            self.writers.append(writer)
            await handler(reader, writer)
        server = await asyncio.start_server(guarded, '127.0.0.1', 0)
        self.servers.append(server)
        return server

    async def asyncTearDown(self):
        for mux in self.muxes:
            mux.closed = True
        for mux, task in self.relay.sessions.values():
            mux.closed = True
            task.cancel()
        for writer in self.writers:
            writer.close()
        for server in self.servers:
            server.close()
            await server.wait_closed()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def connect_mux(self, count, *, bytes_per_second=None):
        mux = Mux()
        self.muxes.append(mux)
        self.tasks.append(asyncio.create_task(mux.schedule()))
        session = secrets.token_bytes(16)
        relay_port = self.relay_server.sockets[0].getsockname()[1]
        async def limited_proxy(reader, writer):
            upstream_reader, upstream_writer = await asyncio.open_connection('127.0.0.1', relay_port)
            self.writers.append(upstream_writer)
            async def copy(source, destination):
                try:
                    while data := await source.read(1024):
                        if bytes_per_second:
                            await asyncio.sleep(len(data) / bytes_per_second)
                        destination.write(data)
                        await destination.drain()
                except (OSError, ConnectionError):
                    pass
                finally:
                    destination.close()
            await asyncio.gather(copy(reader, upstream_writer), copy(upstream_reader, writer))
        proxy = await self.listen(limited_proxy)
        for index in range(count):
            reader, writer = await asyncio.open_connection('127.0.0.1', proxy.sockets[0].getsockname()[1])
            self.writers.append(writer)
            _, outgoing, incoming, epoch = await authenticate(reader, writer, self.token, session=session)
            await mux.accept_epoch(epoch)
            lane = Lane(mux, reader, writer, outgoing, incoming, str(index))
            self.tasks.append(asyncio.create_task(lane.run()))
        for _ in range(100):
            if len(mux.lanes) == count:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(len(mux.lanes), count)
        frontend = await self.listen(mux.socks)
        return mux, frontend.sockets[0].getsockname()[1]

    async def test_single_connection_aggregates_five_independent_20k_paths(self):
        payload = secrets.token_bytes(120 * 1024)
        async def echo(reader, writer):
            try:
                data = await reader.readexactly(len(payload))
                writer.write(data)
                await writer.drain()
                writer.write_eof()
            finally:
                pass
        destination = await self.listen(echo)
        durations = []
        for paths in (1, 5):
            mux, port = await self.connect_mux(paths, bytes_per_second=20 * 1024)
            reader, writer = await socks_connect('127.0.0.1', port, '127.0.0.1', destination.sockets[0].getsockname()[1])
            self.writers.append(writer)
            started = time.monotonic()
            writer.write(payload)
            await writer.drain()
            writer.write_eof()
            received = await asyncio.wait_for(reader.readexactly(len(payload)), 35)
            durations.append(time.monotonic() - started)
            self.assertEqual(received, payload, 'Reordered striped data must be byte-exact')
            self.assertEqual(await asyncio.wait_for(reader.read(), 5), b'')
            self.assertTrue(all(lane.sent > len(payload) // (paths * 3) for lane in mux.lanes))
        self.assertGreater(durations[0] / durations[1], 2.5, f'Expected real single-stream gain, seconds={durations}')

    async def test_path_loss_retransmits_without_corrupting_a_stream(self):
        payload = secrets.token_bytes(256 * 1024)
        async def echo(reader, writer):
            while data := await reader.read(4096):
                writer.write(data)
                await writer.drain()
            writer.write_eof()
        destination = await self.listen(echo)
        mux, port = await self.connect_mux(3, bytes_per_second=60 * 1024)
        reader, writer = await socks_connect('127.0.0.1', port, '127.0.0.1', destination.sockets[0].getsockname()[1])
        self.writers.append(writer)
        writer.write(payload)
        await writer.drain()
        writer.write_eof()
        deadline = time.monotonic() + 5
        victim = None
        while time.monotonic() < deadline:
            candidates = [frame.lane for stream in mux.streams.values() for frame in stream.pending.values()
                          if frame.kind == 2 and frame.lane is not None]
            if candidates:
                victim = candidates[0]
                break
            await asyncio.sleep(.005)
        self.assertIsNotNone(victim, 'The failed path must hold unacknowledged application data')
        victim.writer.close()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)), 20), payload)
        self.assertEqual(await asyncio.wait_for(reader.read(), 5), b'')

    async def test_bad_authentication_target_guard_and_token_validation(self):
        for invalid in ('x', 'z' * 64, ' ' * 64, None):
            with self.assertRaises(ValueError):
                token_bytes(invalid)
        reader, writer = await asyncio.open_connection('127.0.0.1', self.relay_server.sockets[0].getsockname()[1])
        self.writers.append(writer)
        with self.assertRaises((ValueError, asyncio.IncompleteReadError)):
            await authenticate(reader, writer, secrets.token_hex(32), session=secrets.token_bytes(16))
        guarded = Mux(relay=True)
        with self.assertRaisesRegex(ValueError, 'public IPv4'):
            await guarded.target(b'["127.0.0.1",80]')

    async def test_completed_handshakes_do_not_exhaust_reconnect_capacity(self):
        mux, _ = await self.connect_mux(2)
        self.assertEqual(len(mux.lanes), 2)
        self.assertEqual(self.relay.handshakes, 0)
