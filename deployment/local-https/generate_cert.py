"""Generate a local-only CA and HTTPS certificate. Never changes OS trust stores."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _write_private(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)


def _assert_secure_output(output_dir: Path) -> None:
    """Refuse to write keys when repository code or the output ACL is shared."""
    if not output_dir.is_dir():
        raise PermissionError("ACL check requires an existing owner-protected certificate directory")
    if sys.platform == "win32":
        powershell = shutil.which("pwsh") or shutil.which("powershell.exe")
        if powershell is None:
            raise PermissionError("ACL check requires PowerShell")
        guard = Path(__file__).with_name("assert-local-acl.ps1")
        repository = Path(__file__).resolve().parents[2]
        for path, protected in ((repository, False), (Path(__file__), False),
                                (guard, False), (output_dir, True)):
            command = [powershell, "-NoProfile", "-NonInteractive", "-File", str(guard),
                       "-LiteralPath", str(path)]
            if protected:
                command.append("-RequireProtected")
            try:
                checked = subprocess.run(command, capture_output=True, text=True, timeout=15,
                                         check=False)
            except (OSError, subprocess.TimeoutExpired):
                raise PermissionError("ACL check could not complete") from None
            if checked.returncode != 0:
                raise PermissionError("ACL check failed; local certificate operation refused")
    else:
        status = output_dir.stat()
        if status.st_uid != os.getuid() or status.st_mode & 0o077:
            raise PermissionError("ACL check requires an owner-only certificate directory")


def verify_issued_ca(output_dir: Path) -> bool:
    """Reject old local CAs without a receipt from the guarded generator."""
    try:
        with (output_dir / "ca-provenance.json").open("rb") as source:
            encoded = source.read(1025)
        if len(encoded) > 1024:
            return False
        proof = json.loads(encoded)
        certificate = x509.load_pem_x509_certificate((output_dir / "local-ca.pem").read_bytes())
    except (OSError, ValueError, UnicodeError):
        return False
    return (isinstance(proof, dict) and set(proof) == {"format", "ca_sha256"}
            and proof["format"] == "ariadne-local-ca-v1"
            and proof["ca_sha256"] == certificate.fingerprint(hashes.SHA256()).hex().upper())


def generate(output_dir: Path) -> dict[str, Path]:
    _assert_secure_output(output_dir)
    paths = {name: output_dir / name for name in
             ("local-ca.key", "local-ca.pem", "localhost.key", "localhost.pem",
              "ca-provenance.json")}
    if any(path.exists() for path in paths.values()):
        raise FileExistsError("Local certificates already exist; leave them in place or remove them deliberately")
    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ariadne Local Development CA")])
    ca_cert = (x509.CertificateBuilder()
               .subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(minutes=5))
               .not_valid_after(now + timedelta(days=365))
               .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
               .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False,
                   key_encipherment=False, data_encipherment=False, key_agreement=False,
                   key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
               .sign(ca_key, hashes.SHA256()))
    server_key = ec.generate_private_key(ec.SECP256R1())
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    server_cert = (x509.CertificateBuilder()
                   .subject_name(server_name).issuer_name(ca_name)
                   .public_key(server_key.public_key())
                   .serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=5))
                   .not_valid_after(now + timedelta(days=90))
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .add_extension(x509.SubjectAlternativeName([
                       x509.DNSName("localhost"),
                       x509.IPAddress(ip_address("127.0.0.1")),
                       x509.IPAddress(ip_address("::1")),
                   ]), critical=False)
                   .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                       key_encipherment=False, data_encipherment=False, key_agreement=False,
                       key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
                   .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                                  critical=False)
                   .sign(ca_key, hashes.SHA256()))
    secret_format = serialization.PrivateFormat.PKCS8
    no_encryption = serialization.NoEncryption()
    _write_private(paths["local-ca.key"], ca_key.private_bytes(
        serialization.Encoding.PEM, secret_format, no_encryption))
    _write_private(paths["local-ca.pem"], ca_cert.public_bytes(serialization.Encoding.PEM))
    _write_private(paths["localhost.key"], server_key.private_bytes(
        serialization.Encoding.PEM, secret_format, no_encryption))
    _write_private(paths["localhost.pem"], server_cert.public_bytes(serialization.Encoding.PEM)
                   + ca_cert.public_bytes(serialization.Encoding.PEM))
    receipt = {"format": "ariadne-local-ca-v1",
               "ca_sha256": ca_cert.fingerprint(hashes.SHA256()).hex().upper()}
    _write_private(paths["ca-provenance.json"],
                   (json.dumps(receipt, sort_keys=True) + "\n").encode("utf-8"))
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create local HTTPS material without installing trust")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "certs")
    parser.add_argument("--verify", action="store_true", help="check guarded local CA provenance")
    args = parser.parse_args()
    if args.verify:
        _assert_secure_output(args.output)
        if not verify_issued_ca(args.output):
            raise SystemExit("Local CA provenance is unverified. Do not trust the existing CA.")
        print("Local CA provenance receipt matches the certificate.")
        raise SystemExit(0)
    written = generate(args.output)
    certificate = x509.load_pem_x509_certificate(written["local-ca.pem"].read_bytes())
    print("Local certificate files created in:", args.output.resolve())
    print("CA SHA-256 fingerprint:", certificate.fingerprint(hashes.SHA256()).hex().upper())
    print("No certificate was installed into an OS or browser trust store.")
