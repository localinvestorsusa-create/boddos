"""Generate a self-signed TLS certificate so LAN traffic is encrypted.

For a private mesh, a self-signed cert (pinned/trusted once on your devices) is
enough to stop passive eavesdropping on the wire. For zero-trust remote access,
prefer a WireGuard/Tailscale overlay in addition.
"""
from __future__ import annotations

import datetime
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def ensure_self_signed(cert_path: str | Path, key_path: str | Path,
                       hostnames: list[str] | None = None,
                       ips: list[str] | None = None) -> tuple[Path, Path]:
    cert_path, key_path = Path(cert_path).expanduser(), Path(key_path).expanduser()
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path
    cert_path.parent.mkdir(parents=True, exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "boddos.local")])
    alt = [x509.DNSName(h) for h in (hostnames or ["boddos.local", "localhost"])]
    for ip in (ips or ["127.0.0.1"]):
        try:
            alt.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            pass
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(alt), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    try:
        key_path.chmod(0o600)
    except OSError:
        pass
    return cert_path, key_path
