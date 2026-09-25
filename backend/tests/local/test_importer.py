import pytest

from app.local.importer import ImportLimits, UploadedSource, import_files


def test_identity_is_order_independent_and_changes_with_content():
    files = [UploadedSource(path="src/main.py", content="print(1)"), UploadedSource(path="README.md", content="# Example")]
    first = import_files("Example", files)
    assert import_files("Example", list(reversed(files))).snapshot_id == first.snapshot_id
    assert import_files("Example", files[:1]).snapshot_id != first.snapshot_id
    assert import_files("Example", [UploadedSource(path="src/main.py", content="print(2)")]).snapshot_id != first.snapshot_id
    assert first.snapshot_id.startswith("local:")


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "C:/data.py", "\\\\host\\file", "a/../b", "a//b", "a\x00b", "a\\b"])
def test_unsafe_paths_rejected(path):
    with pytest.raises(ValueError):
        import_files("Example", [UploadedSource(path=path, content="x")])


def test_duplicate_and_unicode_normalized_collision_rejected():
    for paths in [("a.py", "a.py"), ("caf\u00e9.py", "cafe\u0301.py")]:
        with pytest.raises(ValueError, match="duplicate"):
            import_files("Example", [UploadedSource(path=p, content="x") for p in paths])
    source = import_files("Example", [UploadedSource(path="çalışma.py", content="print('merhaba')")])
    assert "çalışma.py" in source.sources


def test_sensitive_generated_binary_files_never_stored():
    paths = [".env", "src/.env.local", "id_rsa", "cert.pem", ".git/config", "node_modules/index.js", "build/main.py", "logo.png"]
    files = [UploadedSource(path=p, content="PRIVATE") for p in paths]
    result = import_files("Example", files + [UploadedSource(path="main.py", content="print(1)")])
    assert result.sources == {"main.py": "print(1)"}
    assert set(result.excluded) == set(paths)


def test_inclusive_limits_and_utf8_byte_count():
    limits = ImportLimits(max_files=2, max_file_bytes=4, max_total_bytes=6)
    assert len(import_files("Example", [UploadedSource(path="a.py", content="éé"), UploadedSource(path="b.py", content="ab")], limits=limits).sources) == 2
    cases = [[UploadedSource(path="a.py", content="ééé")],
             [UploadedSource(path="a.py", content="abcd"), UploadedSource(path="b.py", content="abc")],
             [UploadedSource(path=f"{i}.py", content="x") for i in range(3)]]
    for files in cases:
        with pytest.raises(ValueError, match="limit"):
            import_files("Example", files, limits=limits)


def test_repository_id_can_be_preserved_on_reimport():
    first = import_files("Example", [UploadedSource(path="a.py", content="one")])
    second = import_files("Renamed", [UploadedSource(path="a.py", content="two")], repository_id=first.repository_id)
    assert second.repository_id == first.repository_id
    assert second.snapshot_id != first.snapshot_id


def test_key_detection_does_not_exclude_a_detector_source_file():
    sources = [UploadedSource(path="detector.py", content='if "PRIVATE KEY-----" in content: pass'),
               UploadedSource(path="unsafe.txt", content='-----BEGIN RSA PRIVATE KEY-----\nsecret\n-----END RSA PRIVATE KEY-----')]
    result = import_files("Detector", sources)
    assert "detector.py" in result.sources
    assert result.excluded["unsafe.txt"] == "private_key_content"
