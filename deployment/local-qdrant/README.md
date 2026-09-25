# Local Qdrant for Ariadne on Windows

This setup is designed to run one Qdrant REST server at `http://127.0.0.1:6333`. It uses the
official Qdrant **v1.19.1 Windows x64** release archive and verifies its
published SHA-256 digest before extraction. The extracted executable is also
checked against its pinned digest before every start, including when it was
already installed. Docker and WSL are not required.
When started, the service binds to `127.0.0.1` only, disables gRPC and usage telemetry, and
keeps its database under `data/`. It reads the API key from `state/api-key.txt`,
encoded as 64 lowercase ASCII hex characters without a newline. The key is
passed to the Qdrant child process as
`QDRANT__SERVICE__API_KEY`; it is not placed in command arguments, logs or a
tracked config file. Runtime files, data, logs, and state are ignored by Git.
No repository data is sent to Qdrant Cloud.

Before start, `assert-private.ps1` reads the Windows ACLs and
refuses to proceed if the code path is writable by an untrusted account, or if
data, legacy storage, snapshots, logs, or state can be accessed by accounts
other than the current user, SYSTEM, or Administrators. The key file must have
a protected current-user-only ACL. This check does not change permissions or create a key. On the current
machine, the repository directory and `data/` inherit `BUILTIN\Users: Modify`,
so this preflight blocks startup. Installing the verified binary does not
require private data. The private storage, API key, and trusted code path must
be provisioned before Qdrant can start with repository data.

From the repository root in PowerShell:

Use **PowerShell 7 or newer** (`pwsh.exe`). The start script uses its
`Start-Process -Environment` option to pass the key only to the Qdrant child.

```powershell
& .\deployment\local-qdrant\install.ps1
& .\deployment\local-qdrant\start.ps1
& .\deployment\local-qdrant\ready.ps1
& .\deployment\local-qdrant\stop.ps1
```

The API and worker can use `http://127.0.0.1:6333` with the key from
`state/api-key.txt` in Qdrant's `api-key` header. Start Qdrant before them;
stop it after they have exited. The scripts refuse to replace an unrelated
process on port 6333, and `stop.ps1` checks the recorded executable path and
process creation time before stopping anything. It does not touch Ariadne's
site or worker processes. `stop.ps1` terminates only this Qdrant process;
the database stays on disk.

To verify the local server with synthetic data, with port 6333 initially
free, run:

```powershell
& .\deployment\local-qdrant\smoke.ps1
```

The smoke test starts Qdrant, checks that collection access without a key or
with a wrong key is rejected, creates a unique temporary collection, inserts
two small vectors, checks search, stops and restarts Qdrant, checks the same
point again, removes its temporary collection, and stops Qdrant. It does not
delete existing collections or data. It refuses to restart an existing
service. The HTTP readiness endpoint is `/readyz`. The current fail-closed
version has not completed this test because the repository ACL blocks startup.
Earlier auth and persistence test results do not verify this version.

The release asset is
[qdrant-x86_64-pc-windows-msvc.zip](https://github.com/qdrant/qdrant/releases/download/v1.19.1/qdrant-x86_64-pc-windows-msvc.zip),
with SHA-256
`9b6f69bd85f6abed4bc13f943099f55c6ffd55f5dd90388635320d8fbb569eb0`
from the [official release metadata](https://api.github.com/repos/qdrant/qdrant/releases/tags/v1.19.1).
The configuration follows Qdrant's
[configuration](https://qdrant.tech/documentation/operations/configuration/),
[network binding](https://qdrant.tech/documentation/security/), and
[monitoring](https://qdrant.tech/documentation/operations/monitoring/) docs.

This is a local single-node setup. It has no high availability, backup
automation, or remote access. The release archive contains only `qdrant.exe`,
so the optional web dashboard assets are absent; this integration uses the
REST API. Qdrant reports that it cannot check Windows filesystem
compatibility; persistence in the current version still needs a successful
protected-ACL smoke test and backups. API authentication is configured with a
key, but its current-version behavior awaits that smoke test. The repository
ACL does not provide private storage or trusted code against other Windows
users. A process running as the same Windows user can read that user's key and
remains inside the local trust boundary.
