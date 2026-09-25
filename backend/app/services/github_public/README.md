# Public GitHub repository reader

`GitHubPublicService.fetch_repository(github_url)` reads public GitHub metadata, resolves the default branch once, and returns its commit SHA and complete Git tree. Each file has a blob SHA, size, detected language and a filter decision. `fetch_file(snapshot, file)` reads a selected UTF-8 file by blob SHA, so a moving branch cannot change its content. The service never clones, extracts, imports or executes repository code.

Only canonical HTTPS `github.com/owner/repo` URLs are accepted. The API client uses only `api.github.com`, rejects redirects, has response time and byte limits, and does not send credentials. Private repositories are rejected; authorization for those belongs to a separate feature.

The tree is limited to 10,000 entries. At most 2,000 source files and 20 MB of selected source may be imported. A single selected file is limited to 512 KB. Unsupported types, generated/dependency directories and oversized individual files remain in the tree with an exclusion reason. An incomplete GitHub tree or an over-limit selected set returns `REPOSITORY_TOO_LARGE` rather than silently giving a partial snapshot.

Errors expose a stable `code`, message and `retryable` flag. Notable codes include `INVALID_REPOSITORY`, `REPOSITORY_NOT_FOUND`, `ACCESS_DENIED`, `UNSUPPORTED_LANGUAGE`, `RATE_LIMITED`, `REPOSITORY_TOO_LARGE`, `INVALID_GITHUB_RESPONSE` and `GITHUB_UNAVAILABLE`. A GitHub 404 cannot distinguish a missing repository from a private one without authorization.

Frameworks are conservative filename-based hints. Language counts cover selected files only. HTTP endpoint, persistence and analysis orchestration are handled by later integration work.

## Document sources

`document_files(snapshot)` lists `pyproject.toml`, `package.json`, `openapi.json`, `Dockerfile`, `.env.example`, `.env.sample`, and `.env.template` in non-generated, non-sensitive paths. It also lists root `README.md`, `README.rst`, `README.txt`, and `.md`, `.rst`, `.txt` files below `docs/` or `doc/` in safe paths. These remain excluded from the normal source-code filter. At most 64 document sources and 2 MB of document data can be selected; each still has the 512 KB file limit. `fetch_document_file(snapshot, file)` reads a listed file by its immutable blob SHA and checks the returned UTF-8 bytes against the Git blob SHA and declared size. A caller can pass the resulting `{file.path: text}` mapping to a documentation or retrieval component, treating every line as untrusted data.

Real `.env` files, key/token/secret files, and sensitive directories are not eligible. Example env files are untrusted too: this reader returns only uppercase variable names and line positions, replacing every value and comment with empty text before returning. Other document contents remain untrusted input; callers must parse them as data and avoid executing declared scripts or container instructions.
