import dataclasses
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, Profile, StateStore


@unittest.skipUnless(os.name == "posix", "POSIX state locking")
class ProfileTests(unittest.TestCase):
    def test_remove_rejects_profiles_still_assigned_to_an_app(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            profile = store.save_profile(Profile("referenced", "socks5", {}))
            store.save_app(AppBinding("app", ["/bin/true"], profile_id=profile.id))
            manager = ProtocolManager(store, Mock())
            with patch("splitforge.protocols.manager.require_root"), self.assertRaisesRegex(ValueError, "references"):
                manager.remove(profile.id)
            self.assertEqual(store.profile(profile.id).id, profile.id)
            manager.netns.destroy.assert_not_called()

    def test_replacement_preserves_identity_assignments_and_dns(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            manager = ProtocolManager(store, Mock())
            manager.netns.exists.return_value = False
            previous = store.save_profile(Profile("private", "socks5", {}, exit_ip="192.0.2.1",
                doh_url="https://dns.example.com/dns-query", doh_ip="192.0.2.53",
                probe_url="https://probe.example.com/trace", tls_ca_file="/root/ca.pem"))
            app = AppBinding("example", ["/bin/true"], profile_id=previous.id)
            store.save_app(app)
            inactive = subprocess.CompletedProcess([], 0, "inactive\n", "")
            with patch("splitforge.protocols.manager.run", return_value=inactive):
                updated = manager.import_profile("socks5://127.0.0.1:1081", replace_id=previous.id)
            self.assertEqual((updated.id, updated.slot, updated.name), (previous.id, previous.slot, previous.name))
            self.assertEqual(updated.tls_ca_file, previous.tls_ca_file)
            self.assertEqual(updated.doh_url, previous.doh_url)
            self.assertEqual(updated.probe_url, previous.probe_url)
            self.assertEqual(updated.exit_ip, "")
            self.assertEqual(store.app(app.id).profile_id, updated.id)
            manager.netns.exists.return_value = True
            with patch("splitforge.protocols.manager.run", return_value=inactive), self.assertRaises(ValueError):
                manager.import_profile("socks5://127.0.0.1:1082", replace_id=previous.id)
            self.assertEqual(store.profile(previous.id).config, updated.config)

    def test_dnstt_edit_can_preserve_pinned_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            manager = ProtocolManager(store, Mock())
            manager.netns.exists.return_value = False
            previous = manager.dns_tunnel("dns", "dnstt", "t.example.com", "udp://127.0.0.1:53", public_key="ab" * 32)
            with patch("splitforge.protocols.manager.run", return_value=subprocess.CompletedProcess([], 0, "inactive", "")):
                updated = manager.dns_tunnel("dns", "dnstt", "new.example.com", "udp://127.0.0.1:53", replace_id=previous.id)
            self.assertEqual(updated.config["public_key"], "ab" * 32)
            self.assertEqual(updated.id, previous.id)

    def test_dns_and_probe_urls_require_verified_https(self):
        profile = Profile("valid", "wireguard", {})
        for change in ({"doh_url": "http://example.com/dns-query"},
                       {"doh_url": "https://user:pass@example.com/dns-query"},
                       {"probe_url": "http://example.com/trace"},
                       {"tls_ca_file": "relative.pem"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                dataclasses.replace(profile, **change)
