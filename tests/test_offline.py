"""Small local checks; release CI also installs every ZIP without networking."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.build_offline import checksums


class OfflineBundleTests(unittest.TestCase):
    def test_manifest_covers_nested_payload_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'wheels').mkdir()
            payload = folder / 'wheels/runtime.whl'
            payload.write_bytes(b'wheel contents')
            (folder / 'TARGET').write_text('ubuntu 24.04 amd64\n')
            checksums(folder)
            manifest = (folder / 'SHA256SUMS').read_text()
            self.assertEqual(len(manifest.splitlines()), 2)
            digest, relative = manifest.splitlines()[1].split('  ', 1)
            self.assertEqual(relative, 'wheels/runtime.whl')
            self.assertEqual(digest, hashlib.sha256(payload.read_bytes()).hexdigest())
            payload.write_bytes(b'changed')
            self.assertNotEqual(digest, hashlib.sha256(payload.read_bytes()).hexdigest())
            checksums(folder)
            self.assertEqual(len((folder / 'SHA256SUMS').read_text().splitlines()), 2)


if __name__ == '__main__':
    unittest.main()
