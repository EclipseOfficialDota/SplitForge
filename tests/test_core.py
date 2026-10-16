"""Run with: python -m unittest discover -s tests -v (no root required)."""
import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from splitforge.core.netns import NetNS, unit_word
from splitforge.protocols.manager import import_uri, openvpn_config, wireguard_config
from splitforge.state import AppBinding, Profile, StateStore


class CoreTests(unittest.TestCase):
    def test_reality_uri(self):
        profile = import_uri("vless://2b1f7aec-8080-4e54-a4ee-498bc48674fd@example.com:443?"
                             "security=reality&sni=www.example.com&pbk=abcd&sid=aa&flow=xtls-rprx-vision#DE")
        self.assertEqual(profile.name, "DE")
        self.assertEqual(profile.config["outbound"]["streamSettings"]["realitySettings"]["serverName"], "www.example.com")

    def test_shadowsocks_password_keeps_colons(self):
        profile = import_uri("ss://YWVzLTI1Ni1nY206cGE6c3M@example.com:8388#SS")
        self.assertEqual(profile.config["outbound"]["settings"]["servers"][0]["password"], "pa:ss")

    def test_unsupported_plugin_rejected(self):
        with self.assertRaises(ValueError):
            import_uri("ss://YWVzLTI1Ni1nY206cGFzcw@example.com:8388?plugin=arbitrary")

    def test_wireguard_never_executes_hooks(self):
        with self.assertRaises(ValueError):
            wireguard_config("[Interface]\nAddress=10.8.0.2/32\nPostUp=ip route flush table main\n")
        text, addresses, mtu = wireguard_config("[Interface]\nPrivateKey=key\nAddress=10.8.0.2/32,fd00::2/128\n"
                                               "DNS=9.9.9.9\n[Peer]\nAllowedIPs=0.0.0.0/0,::/0\n")
        self.assertNotIn("Address", text)
        self.assertNotIn("DNS", text)
        self.assertEqual(addresses, ["10.8.0.2/32"])
        self.assertEqual(mtu, 1420)

    def test_wireguard_default_in_comment_does_not_count(self):
        with self.assertRaises(ValueError):
            wireguard_config("[Interface]\nAddress=10.8.0.2/32\n[Peer]\nAllowedIPs=10.0.0.0/8 # AllowedIPs=0.0.0.0/0\n")

    def test_openvpn_rejects_execution_and_includes(self):
        for directive in ("up /tmp/evil", "plugin /tmp/evil.so", "config /tmp/other", "iproute /tmp/evil", "daemon"):
            with self.subTest(directive=directive), self.assertRaises(ValueError):
                openvpn_config("client\n" + directive, Path("/"))
        text = openvpn_config("client\nremote vpn.example 1194\nredirect-gateway def1\n<ca>\nPEM\n</ca>", Path("/"))
        self.assertNotIn("redirect-gateway", text)
        self.assertIn("<ca>\nPEM\n</ca>", text)

    def test_guard_has_no_underlay_fallback(self):
        profile = Profile("dns", "dnstt", {}, slot=1)
        with patch("splitforge.core.netns.run", return_value=subprocess.CompletedProcess([], 1, "", "")) as execute:
            NetNS().guard(profile, proxy=True, udp=False)
        args, keywords = execute.call_args
        self.assertEqual(args[0][:4], ["ip", "netns", "exec", profile.namespace])
        self.assertIn("policy drop", keywords["input"])
        self.assertIn("meta l4proto udp reject", keywords["input"])
        self.assertIn(f"ip daddr {profile.gateway} tcp dport 1080 accept", keywords["input"])
        self.assertNotIn("ct state established,related accept\n  oifname", keywords["input"])

    def test_namespace_default_cannot_modify_host(self):
        profile = Profile("wg", "wireguard", {}, slot=1)
        with patch("splitforge.core.netns.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as execute:
            NetNS().activate(profile)
        for call in execute.call_args_list:
            self.assertEqual(call.args[0][:4], ["ip", "netns", "exec", profile.namespace])

    def test_unit_arguments_are_literal(self):
        self.assertEqual(unit_word("100% $HOME"), '"100%% $$HOME"')
        with self.assertRaises(ValueError):
            unit_word("safe\nExecStart=/bin/evil")
        with self.assertRaises(ValueError):
            AppBinding("evil", ["/bin/true"], service="ssh.service\nExecStart=evil")

    @unittest.skipUnless(os.name == "posix", "State durability uses Linux flock/fsync")
    def test_state_atomic_roundtrip_and_references(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            profile = store.save_profile(Profile("test", "socks5", {}))
            app = AppBinding("test", ["/usr/bin/true"], profile_id=profile.id)
            store.save_app(app)
            with self.assertRaises(ValueError):
                store.delete_profile(profile.id)
            self.assertEqual(store.profile("test").slot, 1)
            self.assertEqual(store.app(app.id).profile_id, profile.id)
            with store.operation():
                store.save_app(dataclasses.replace(app, profile_id=None))
            store.delete_profile(profile.id)
            self.assertEqual(json.loads(store.path.read_text())["profiles"], {})
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
