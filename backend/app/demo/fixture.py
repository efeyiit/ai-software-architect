"""Bundled synthetic source used exclusively by the local demo."""

from hashlib import sha1

from app.services.github_public.service import RepositoryFile, RepositorySnapshot


DEMO_OWNER = "local-demo"
DEMO_REPOSITORY_ID = "demo-commerce-api"
DEMO_SOURCE_ID = "bundled-synthetic-commerce-api"
DEMO_COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"
DEMO_SOURCES = {
    "src/api/orders.ts": (
        "export function createOrder(customerId: string): string {\n"
        "  return `order-for-${customerId}`;\n"
        "}\n"
    ),
}


def demo_snapshot() -> RepositorySnapshot:
    files = []
    for path, source in DEMO_SOURCES.items():
        raw = source.encode("utf-8")
        blob_sha = sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        files.append(RepositoryFile(path, blob_sha, len(raw), "TypeScript", True, None))
    return RepositorySnapshot(DEMO_SOURCE_ID, "https://github.com/ariadne-demo/commerce-api",
                              "commerce-api", "main", DEMO_COMMIT_SHA, "a" * 40,
                              tuple(files), (("TypeScript", 1),), ())
