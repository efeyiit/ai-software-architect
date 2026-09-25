import pytest
from pydantic import ValidationError

from app.contracts.analysis import RepositorySnapshot


def test_github_wire_format_is_unchanged():
    wire = {"repository_id": "one", "commit_sha": "a" * 40}
    assert RepositorySnapshot.model_validate(wire).model_dump() == wire


def test_local_identity_round_trip_is_explicit():
    wire = {"repository_id": "one", "source_kind": "local", "commit_sha": None,
            "snapshot_id": "local:" + "a" * 64}
    identity = RepositorySnapshot.model_validate(wire)
    assert identity.model_dump() == wire
    assert identity.revision == wire["snapshot_id"]


@pytest.mark.parametrize("wire", [
    {"repository_id": "one"},
    {"repository_id": "one", "commit_sha": "local:" + "a" * 64},
    {"repository_id": "one", "source_kind": "local", "commit_sha": "a" * 40, "snapshot_id": "local:" + "a" * 64},
    {"repository_id": "one", "source_kind": "local", "snapshot_id": "a" * 40},
])
def test_ambiguous_identity_is_rejected(wire):
    with pytest.raises(ValidationError):
        RepositorySnapshot.model_validate(wire)
