# Alternate authenticated server runtime

For the account-free local workspace, follow the [main README](../../README.md). This document covers the separate OAuth/PostgreSQL server configuration.

`open.ps1` starts the real Ariadne application at `https://localhost:8443/`.
The same origin serves the built frontend, GitHub OAuth routes, and authenticated
repository API. `stop.ps1` stops only processes recorded and verified by this
launcher. A second open reuses the healthy instance.

Both launchers require `%LOCALAPPDATA%\Ariadne\Control` to exist with a
protected ACL owned by the current Windows user. The preflight checks that
directory, its ancestors, process state and log files before reading or
writing control data. It never changes ACLs. On this host, permission changes
were blocked by policy, so a secure positive startup remains unverified.

The launcher prepares frontend assets when sources or public assets (such as
the login logo) changed, uses the local HTTPS
setup in `deployment/local-https`, starts the pinned native Qdrant server,
then starts an E5/Qwen model worker on loopback port 8767. The API and analysis
worker are separate child processes. A fresh model token is passed only through
their child environments. After its ACL preflight passes, Qdrant's private API
key is read from the ignored state file and passed only to the API and analysis worker.
Nothing is sent to a paid service. The old port 8766 demo worker is untouched.

Startup requires the configured GitHub OAuth app, a trusted local HTTPS CA,
PostgreSQL with the Ariadne schemas, the cached model files, and the local
Qdrant service. Missing requirements stop startup with an explicit error. The
`/health` endpoint alone reports process liveness; startup also requires
`/auth/me` to return 401 for an anonymous browser before opening the UI.

On this host, PostgreSQL startup through the available portable `pg_ctl.exe`
was blocked by Windows Application Control. The launcher must not bypass that
policy or claim a working authenticated application while the database is
unavailable. GitHub OAuth client credentials and local CA trust also require
the operator's own setup.
