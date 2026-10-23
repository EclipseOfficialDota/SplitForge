"""Persistent group references, protected limits and destination restart state."""
import asyncio
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from splitforge.core.bond import Mux, Stream
from splitforge.core.speed import set_limits
from splitforge.core.traffic import TrafficStore, new_row
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import Profile, StateStore


@unittest.skipUnless(os.name == 'posix', 'Private state uses POSIX locking')
class BondProfileTests(unittest.TestCase):
    def test_members_cannot_disappear_become_recursive_or_bypass_budgets(self):
        with tempfile.TemporaryDirectory() as folder:
            store = StateStore(Path(folder) / 'state.json')
            manager = ProtocolManager(store)
            members = [manager.import_profile('socks5://127.0.0.1:1080', name=str(index)) for index in range(2)]
            token = secrets.token_hex(32)
            bond = manager.bond('combined', [p.id for p in members], '127.0.0.1', 28443, token)
            self.assertEqual(store.profile(bond.id).config['token'], token)
            with self.assertRaisesRegex(ValueError, 'member'):
                store.delete_profile(members[0].id)
            with self.assertRaisesRegex(ValueError, 'existing independent'):
                store.save_profile(Profile('other', 'wireguard', {}, id=members[0].id))
            with patch('splitforge.core.speed.require_root'), self.assertRaisesRegex(ValueError, 'bonded output'):
                set_limits(store, members[0].id, 1000, 1000)
            with patch('splitforge.core.traffic.require_root'), self.assertRaisesRegex(ValueError, 'bonded output'):
                TrafficStore(store).set_quota('profiles', members[0].id, 1024)
            with self.assertRaises(ValueError):
                manager.bond('recursive', [bond.id, members[0].id], '127.0.0.1', 28443, token)
            store.delete_profile(bond.id)
            meter = TrafficStore(store)
            data = meter.snapshot()
            data['profiles'][members[0].id] = dict(new_row(), quota=1024)
            meter.write(data)
            with self.assertRaisesRegex(ValueError, 'bonded output'):
                manager.bond('bypass', [p.id for p in members], '127.0.0.1', 28443, token)

    def test_clear_removes_groups_before_members(self):
        from splitforge.core.backup import _clear
        store, manager, runner = Mock(), Mock(), Mock()
        store.apps.return_value = []
        store.snapshot.return_value = {'users': {}}
        store.profiles.return_value = [Profile('member', 'socks5', {}), Mock(protocol='bond', id='aa000001')]
        with patch('splitforge.core.traffic.stop_service'), patch('splitforge.core.backup.run') as run:
            run.return_value.returncode = 1
            _clear(store, manager, runner)
        self.assertEqual(manager.remove.call_args_list[0].args[0], 'aa000001')


class BondRestartTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_new_relay_epoch_closes_old_streams_without_replay(self):
        mux = Mux()
        writer = Mock()
        stream = Stream(mux, 1, writer=writer)
        mux.streams[1] = stream
        stream.abort = AsyncMock(wraps=stream.abort)
        await mux.accept_epoch(b'a' * 16)
        await stream.send(1, b'["example.com",443]')
        await mux.accept_epoch(b'a' * 16)
        self.assertFalse(stream.closed)
        await mux.accept_epoch(b'b' * 16)
        self.assertTrue(stream.closed)
        self.assertFalse(mux.streams)
        self.assertFalse(stream.pending)
        writer.close.assert_called_once()
        await asyncio.sleep(0)
