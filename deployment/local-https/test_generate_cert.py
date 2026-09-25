"""Local certificate fixture checks; never modifies a trust store."""

from importlib.util import module_from_spec, spec_from_file_location
from ipaddress import ip_address
from pathlib import Path
import json
import sys

import pytest

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec


def test_local_certificate_chain_and_san(tmp_path, monkeypatch):
    source = Path(__file__).with_name("generate_cert.py")
    spec = spec_from_file_location("ariadne_local_cert", source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    # This fixture checks certificate contents; ACL denial is covered separately.
    monkeypatch.setattr(module, "_assert_secure_output", lambda path: None)
    paths = module.generate(tmp_path)
    ca = x509.load_pem_x509_certificate(paths["local-ca.pem"].read_bytes())
    leaf = x509.load_pem_x509_certificate(paths["localhost.pem"].read_bytes())
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "localhost" in san.get_values_for_type(x509.DNSName)
    assert ip_address("127.0.0.1") in san.get_values_for_type(x509.IPAddress)
    assert leaf.issuer == ca.subject
    ca.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes,
                           ec.ECDSA(leaf.signature_hash_algorithm))
    assert not leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert paths["localhost.pem"].read_bytes().count(b"BEGIN CERTIFICATE") == 2
    try:
        module.generate(tmp_path)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Existing certificate material must never be overwritten")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows ACL behavior")
def test_certificate_generation_refuses_broad_acl_before_writing_keys(tmp_path):
    source = Path(__file__).with_name("generate_cert.py")
    spec = spec_from_file_location("ariadne_local_cert_acl", source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(PermissionError, match="ACL"):
        module.generate(tmp_path)
    assert not list(tmp_path.glob("*.key"))


def test_ca_provenance_requires_receipt_matching_new_ca(tmp_path, monkeypatch):
    source = Path(__file__).with_name("generate_cert.py")
    spec = spec_from_file_location("ariadne_local_cert_provenance", source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_assert_secure_output", lambda path: None)
    module.generate(tmp_path)
    assert module.verify_issued_ca(tmp_path)
    receipt = tmp_path / "ca-provenance.json"
    proof = json.loads(receipt.read_text(encoding="utf-8"))
    proof["ca_sha256"] = "0" * 64
    receipt.write_text(json.dumps(proof), encoding="utf-8")
    assert not module.verify_issued_ca(tmp_path)
    receipt.unlink()
    assert not module.verify_issued_ca(tmp_path)
