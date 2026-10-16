import hashlib
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from splitforge.core.dependencies import component_plan, download, unpack_verified_tar


class DependencyTests(unittest.TestCase):
    def test_component_plan_includes_proxy_helpers_and_rejects_unknown_names(self):
        self.assertEqual(component_plan(["dnstt-client"]), ["base", "xray", "tun2socks", "dnstt-client"])
        self.assertEqual(component_plan(["wireguard", "wireguard"]), ["base", "wireguard"])
        self.assertEqual(component_plan([]), [])
        with self.assertRaises(ValueError):
            component_plan(["arbitrary-command"])

    def test_offline_cache_requires_the_pinned_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "core.zip"
            artifact.write_bytes(b"verified-test-artifact")
            expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
            with patch.dict(os.environ, {"SPLITFORGE_DOWNLOAD_CACHE": directory}):
                self.assertEqual(download("https://example.com/core.zip", expected, 100), artifact.read_bytes())
                artifact.write_bytes(b"tampered")
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    download("https://example.com/core.zip", expected, 100)

    def test_source_archive_cannot_escape_or_create_links(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("link", tarfile.SYMTYPE)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                memory = io.BytesIO()
                with tarfile.open(fileobj=memory, mode="w:gz") as archive:
                    entry = tarfile.TarInfo(name)
                    entry.type = kind
                    entry.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
                    archive.addfile(entry, io.BytesIO())
                with self.assertRaisesRegex(RuntimeError, "Unsafe"):
                    unpack_verified_tar(memory.getvalue(), Path(directory))
