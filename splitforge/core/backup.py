"""Versioned, password-encrypted configuration backups; no executable archives."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import ssl
import tempfile
import time
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from splitforge import __version__
from splitforge.core.netns import atomic_secret, require_root, run
from splitforge.state import AppBinding, StateStore

MAGIC = 'SPLITFORGE-BACKUP-1\n'
LIMIT = 8 * 1024 * 1024
BACKUPS = Path('/var/backups/splitforge')
CA_ROOT = Path('/etc/ssl/splitforge')


def _key(password: str, salt: bytes) -> bytes:
    if not isinstance(password, str) or not 12 <= len(password.encode()) <= 1024:
        raise ValueError('Backup password must contain 12–1024 UTF-8 bytes')
    return Scrypt(salt=salt, length=32, n=2**17, r=8, p=1).derive(password.encode())


def encrypt(document: dict, password: str) -> str:
    data = json.dumps(document, ensure_ascii=False).encode()
    if len(data) > LIMIT:
        raise ValueError('Backup exceeds the 8 MiB plaintext limit')
    salt, nonce = os.urandom(16), os.urandom(12)
    ciphertext = AESGCM(_key(password, salt)).encrypt(nonce, data, MAGIC.encode())
    return MAGIC + base64.b64encode(salt + nonce + ciphertext).decode() + '\n'


def decrypt(text: str, password: str) -> dict:
    if not isinstance(text, str) or len(text) > LIMIT * 2 or not text.startswith(MAGIC):
        raise ValueError('Unsupported or oversized encrypted backup')
    try:
        data = base64.b64decode(text[len(MAGIC):].strip(), validate=True)
        if len(data) < 44 or len(data) > LIMIT + 44:
            raise ValueError('Invalid encrypted backup length')
        plain = AESGCM(_key(password, data[:16])).decrypt(data[16:28], data[28:], MAGIC.encode())
        document = json.loads(plain)
    except (InvalidTag, ValueError, UnicodeError) as error:
        raise ValueError('Incorrect backup password or damaged backup; nothing was restored') from error
    return validate(document)


def validate(document: dict) -> dict:
    if not isinstance(document, dict) or document.get('format') != 1:
        raise ValueError('Unsupported backup document')
    with tempfile.TemporaryDirectory(prefix='splitforge-validate-') as directory:
        candidate = StateStore(Path(directory) / 'state.json')
        with candidate.operation():
            candidate._write(document['state'])
        candidate.snapshot()
    profiles = document['state']['profiles']
    enabled = document.get('enabled_profiles', [])
    if not isinstance(enabled, list) or any(not isinstance(key, str) or key not in profiles for key in enabled):
        raise ValueError('Invalid saved profile activation list')
    certificates = document.get('certificates', {})
    if not isinstance(certificates, dict) or set(certificates) - profiles.keys():
        raise ValueError('Invalid saved certificate references')
    for pem in certificates.values():
        if not isinstance(pem, str) or len(pem) > 1048576:
            raise ValueError('Invalid saved CA certificate')
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cadata=pem)
    if any(profile.get('tls_ca_file') and key not in certificates for key, profile in profiles.items()):
        raise ValueError('Backup is missing a referenced CA certificate')
    if document.get('web') is not None:
        from splitforge.web.setup import WebSettings
        WebSettings(**document['web']).validate()
    if document.get('traffic') is not None:
        from splitforge.core.traffic import validate_data
        validate_data(document['traffic'])
    return document


def capture(store: StateStore) -> dict:
    from splitforge.web.setup import load_settings
    from splitforge.core.traffic import TrafficStore
    snapshot = store.snapshot()
    certificates = {}
    for key, profile in snapshot['profiles'].items():
        if profile.get('tls_ca_file'):
            path = Path(profile['tls_ca_file'])
            if path.stat().st_size > 1048576:
                raise ValueError('CA certificate file exceeds the backup limit')
            certificates[key] = path.read_text()
    settings = load_settings()
    enabled = [key for key in snapshot['profiles'] if run(
        ['systemctl', 'is-enabled', '--quiet', f'splitforge-profile-{key}.service'], check=False).returncode == 0]
    return validate({'format': 1, 'created': time.time(), 'version': __version__, 'state': snapshot,
                     'enabled_profiles': enabled, 'certificates': certificates,
                     'web': dataclasses.asdict(settings) if settings else None,
                     'traffic': TrafficStore(store).snapshot()})


def export_backup(store, destination, password):
    require_root()
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('Choose a new backup filename; existing files are never overwritten')
    atomic_secret(destination, encrypt(capture(store), password))
    return destination


def read_backup(source, password):
    source = Path(source)
    if not source.is_file() or source.stat().st_size > LIMIT * 2:
        raise ValueError('Backup must be a regular file within the size limit')
    return decrypt(source.read_text(), password)


def _clear(store, manager, runner):
    from splitforge.core.failover import unit_name
    from splitforge.core.traffic import stop_service
    stop_service(store)
    run(['systemctl', 'disable', '--now', unit_name(store)], check=False, timeout=310)
    if run(['systemctl', 'is-active', '--quiet', unit_name(store)], check=False).returncode == 0:
        raise RuntimeError('Stop the failover monitor before restoring configuration')
    for app in store.apps():
        runner.remove(app.id)
    for user in list(store.snapshot()['users']):
        runner.bind_user(user, None)
    for profile in store.profiles():
        manager.remove(profile.id)


def restore_backup(store, manager, runner, document, password, *, start=True, report=print):
    require_root()
    from splitforge.core.traffic import TrafficStore, empty_data
    validate(document)  # Authenticate and validate before touching any current resources.
    previous = capture(store)
    for item in document['state']['apps'].values():
        binding = AppBinding(**item)
        runner._identity(binding.user)
        runner._validate_service(binding)
    for user in document['state']['users']:
        if runner._identity(user).pw_uid < 1000:
            raise ValueError('User-manager binding requires a non-system account')
    recovery = BACKUPS / f'before-restore-{time.time_ns()}.sfb'
    atomic_secret(recovery, encrypt(previous, password))
    report(f'Encrypted recovery backup: {recovery}')
    target = json.loads(json.dumps(document['state']))
    for key, pem in document.get('certificates', {}).items():
        # Trust anchors are public certificates, never private keys. Use a fixed
        # readable directory instead of restoring arbitrary source file paths.
        if CA_ROOT.is_symlink():
            raise ValueError('Refusing a symlink CA directory')
        CA_ROOT.mkdir(mode=0o755, parents=True, exist_ok=True)
        path = CA_ROOT / f'{key}-{hashlib.sha256(pem.encode()).hexdigest()[:16]}.pem'
        atomic_secret(path, pem, 0o644)
        target['profiles'][key]['tls_ca_file'] = str(path)
    try:
        _clear(store, manager, runner)
        with store.operation():
            store._write(target)
        traffic = TrafficStore(store)
        with traffic.locked():
            traffic.write(document.get('traffic') or empty_data())
        if document.get('web'):
            # Preserve current login/listener; the CLI can explicitly redeploy it.
            atomic_secret(store.path.parent / 'restored-web.json', json.dumps(document['web'], indent=2))
        if start:
            runner.restore(document.get('enabled_profiles', []))
    except Exception as error:
        try:
            _clear(store, manager, runner)
            with store.operation():
                store._write(previous['state'])
            traffic = TrafficStore(store)
            with traffic.locked():
                traffic.write(previous.get('traffic') or empty_data())
            runner.restore(previous.get('enabled_profiles', []))
        except Exception as rollback:
            raise RuntimeError(f'Restore and recovery restart failed; encrypted recovery retained at {recovery}') from rollback
        raise RuntimeError('Restore failed; previous configuration and enabled workloads were restored') from error
    report('Configuration restored. Saved web settings are in restored-web.json; current panel access was retained.')
    if not start:
        report('Workloads remain stopped; run splitforge restore when ready.')
    return recovery
