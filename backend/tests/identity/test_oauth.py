import base64
import hashlib
from datetime import datetime, timedelta, timezone
from email.message import Message
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet

from app.security.identity import IdentityError, OAuthConfig, OAuthService, TokenCipher
from app.security.identity.service import GitHubOAuthHTTP
from app.services.github_private import GitHubPrivateService
from app.services.github_private.service import GitHubPrivateHTTPClient
from app.services.github_public import GitHubPublicError


NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)
SHA = "a" * 40
TREE = "b" * 40
BLOB = hashlib.sha1(b"blob 12\0print('ok')\n").hexdigest()


class FakeStore:
    def __init__(self):
        self.states = {}
        self.tokens = {}
        self.links = {}

    def create_state(self, digest, user_id, purpose, verifier_ciphertext, expires_at):
        self.states[digest] = (user_id, purpose, verifier_ciphertext, expires_at)

    def consume_state(self, digest, user_id, purpose):
        saved = self.states.get(digest)
        if saved and saved[0:2] == (user_id, purpose) and saved[3] > NOW:
            del self.states[digest]
            return saved[2]
        return None

    def save_verified_token(self, user_id, github_id, purpose, token_ciphertext,
                            refresh_ciphertext, scopes, expires_at, refresh_expires_at):
        if self.links.get(user_id, github_id) != github_id:
            return False
        self.links[user_id] = github_id
        self.tokens[user_id, purpose] = (github_id, token_ciphertext, refresh_ciphertext,
                                         scopes, expires_at, refresh_expires_at)
        return True

    def load_token(self, user_id, purpose):
        return self.tokens.get((user_id, purpose))


class FakeOAuthAPI:
    def __init__(self):
        self.response = {"access_token": "secret-token", "scope": "repo", "token_type": "bearer"}
        self.user_id = 42
        self.fields = None
        self.blocked = False

    def exchange(self, fields):
        self.fields = fields
        return self.response

    def current_user(self, token):
        if self.blocked:
            raise IdentityError("GITHUB_ACCESS_DENIED", "GitHub denied the credential")
        return {"id": self.user_id}


@pytest.fixture
def setup():
    store = FakeStore()
    api = FakeOAuthAPI()
    cipher = TokenCipher(Fernet.generate_key().decode())
    service = OAuthService(OAuthConfig("client-id", "client-secret", "https://app.example/callback"),
                           cipher, store, api, lambda: NOW)
    return service, store, api, cipher


def begin(service, user="alice", purpose="private"):
    url = service.start(user, purpose)
    return parse_qs(urlsplit(url).query)


def finish(service, params, user="alice", purpose="private"):
    return service.finish(user, purpose, params["state"][0], "one-time-code")


def assert_code(code, fn):
    with pytest.raises((IdentityError, GitHubPublicError)) as error:
        fn()
    assert error.value.code == code


def test_pkce_state_encryption_user_binding_and_replay(setup):
    service, store, api, cipher = setup
    params = begin(service)
    state = params["state"][0]
    digest = hashlib.sha256(state.encode()).digest()
    assert state.encode() not in repr(store.states).encode()
    assert store.states[digest][2] != api.response["access_token"].encode()
    assert params["scope"] == ["repo offline_access"]
    assert params["code_challenge_method"] == ["S256"]
    assert_code("INVALID_STATE", lambda: finish(service, params, "bob"))
    assert finish(service, params) == "42"
    verifier = api.fields["code_verifier"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == params["code_challenge"][0]
    assert api.fields["redirect_uri"] == "https://app.example/callback"
    assert_code("INVALID_STATE", lambda: finish(service, params))
    saved = store.load_token("alice", "private")
    assert b"secret-token" not in saved[1]
    assert cipher.decrypt(saved[1]) == "secret-token"


def test_scope_denial_account_mismatch_and_expired_state(setup):
    service, store, api, _ = setup
    params = begin(service)
    api.response["scope"] = "read:user"
    assert_code("INSUFFICIENT_SCOPE", lambda: finish(service, params))
    assert store.tokens == {}
    api.response["scope"] = "repo"
    store.links["alice"] = "99"
    assert_code("ACCOUNT_MISMATCH", lambda: finish(service, begin(service)))
    params = begin(service)
    digest = hashlib.sha256(params["state"][0].encode()).digest()
    user, purpose, ciphertext, _ = store.states[digest]
    store.states[digest] = user, purpose, ciphertext, NOW
    assert_code("INVALID_STATE", lambda: finish(service, params))


def test_expiry_refresh_and_permission_loss(setup):
    service, store, api, _ = setup
    api.response.update({"expires_in": 120, "refresh_token": "refresh-secret",
                         "refresh_token_expires_in": 3600})
    finish(service, begin(service))
    saved = store.tokens["alice", "private"]
    assert b"refresh-secret" not in saved[2]
    service.clock = lambda: NOW + timedelta(seconds=100)
    api.response = {"access_token": "new-token", "refresh_token": "new-refresh",
                    "expires_in": 120, "refresh_token_expires_in": 3600, "scope": "repo"}
    assert service.valid_token("alice", "private") == "new-token"
    api.blocked = True
    assert_code("GITHUB_ACCESS_DENIED", lambda: service.valid_token("alice", "private"))


def test_refresh_without_repo_permission_fails_closed(setup):
    service, _, api, _ = setup
    api.response.update({"expires_in": 120, "refresh_token": "refresh-secret",
                         "refresh_token_expires_in": 3600})
    finish(service, begin(service))
    service.clock = lambda: NOW + timedelta(seconds=100)
    api.response = {"access_token": "new-token", "refresh_token": "new-refresh",
                    "expires_in": 120, "refresh_token_expires_in": 3600,
                    "scope": "read:user"}
    assert_code("INSUFFICIENT_SCOPE", lambda: service.valid_token("alice", "private"))


def test_missing_configuration_and_wrong_key_are_product_errors(monkeypatch):
    monkeypatch.delenv("ARIADNE_OAUTH_FERNET_KEYS", raising=False)
    assert_code("CONFIGURATION_ERROR", TokenCipher.from_env)
    assert_code("CONFIGURATION_ERROR", lambda: OAuthConfig("", "", "http://app.example/callback"))
    assert_code("CONFIGURATION_ERROR", lambda: TokenCipher("not-a-key"))


class FakeRepoAPI:
    def __init__(self):
        self.revoked = False
        self.calls = []

    def get_json(self, path, max_bytes):
        self.calls.append(path)
        if self.revoked:
            raise GitHubPublicError("ACCESS_DENIED", "Private repository access denied")
        if path == "/repos/owner/secret":
            return {"id": 123, "full_name": "owner/secret", "name": "secret",
                    "private": True, "default_branch": "main"}
        if path == "/repos/owner/secret/commits/main":
            return {"sha": SHA, "commit": {"tree": {"sha": TREE}}}
        if path == f"/repos/owner/secret/git/trees/{TREE}?recursive=1":
            return {"truncated": False, "tree": [
                {"type": "blob", "path": "src/main.py", "sha": BLOB, "size": 12},
                {"type": "blob", "path": "node_modules/skip.js", "sha": "d" * 40, "size": 5}]}
        if path == f"/repos/owner/secret/git/blobs/{BLOB}":
            return {"sha": BLOB, "encoding": "base64",
                    "content": base64.b64encode(b"print('ok')\n").decode()}
        raise AssertionError(path)


def test_private_snapshot_file_owner_and_permission_recheck(setup):
    identity, _, _, _ = setup
    finish(identity, begin(identity))
    api = FakeRepoAPI()
    service = GitHubPrivateService(identity, lambda token: api)
    snapshot = service.fetch_repository("alice", "https://github.com/owner/secret")
    assert snapshot.repository.commit_sha == SHA
    assert [f.path for f in snapshot.repository.included_files] == ["src/main.py"]
    file = snapshot.repository.included_files[0]
    assert_code("ACCESS_DENIED", lambda: service.fetch_file("bob", snapshot, file))
    assert service.fetch_file("alice", snapshot, file) == "print('ok')\n"
    api.revoked = True
    assert_code("ACCESS_DENIED", lambda: service.fetch_file("alice", snapshot, file))


def test_private_reader_rejects_unverified_account_and_public_metadata(setup):
    identity, _, oauth_api, _ = setup
    finish(identity, begin(identity))
    api = FakeRepoAPI()
    service = GitHubPrivateService(identity, lambda token: api)
    oauth_api.user_id = 43
    assert_code("ACCOUNT_MISMATCH", lambda: service.fetch_repository("alice", "https://github.com/owner/secret"))
    assert api.calls == []
    oauth_api.user_id = 42
    original = api.get_json
    def public_metadata(path, max_bytes):
        result = original(path, max_bytes)
        if path == "/repos/owner/secret":
            result["private"] = False
        return result
    api.get_json = public_metadata
    assert_code("ACCESS_DENIED", lambda: service.fetch_repository("alice", "https://github.com/owner/secret"))


def test_http_denials_hide_credentials_and_do_not_follow_redirects():
    class Deny:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 404, "secret-token should not appear", Message(), None)
    private = GitHubPrivateHTTPClient("secret-token")
    private._opener = Deny()
    with pytest.raises(GitHubPublicError) as denied:
        private.get_json("/repos/owner/secret", 100)
    assert denied.value.code == "ACCESS_DENIED"
    assert "secret-token" not in str(denied.value)
    oauth = GitHubOAuthHTTP()
    oauth._opener = Deny()
    with pytest.raises(IdentityError) as denied:
        oauth.exchange({"client_id": "id", "client_secret": "client-secret", "code": "code"})
    assert denied.value.code == "GITHUB_ACCESS_DENIED"
    assert "client-secret" not in str(denied.value)
