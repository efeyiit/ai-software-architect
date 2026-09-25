# Folder ingestion validation

The local importer accepts relative paths and text supplied by the browser; it
does not open filesystem paths or execute repository code. It validates paths,
normalizes Unicode, rejects duplicates and enforces 2,000 files, 1 MiB per file
and 20 MiB total UTF-8 content. These are server-side limits; the browser upload
flow is not connected yet.

Generated directories, dependency directories, environment files and private-key
files are excluded with reasons. Binary and unsupported contents are excluded.
Excluded content is not stored. This is a filename/content guard, not a promise
to detect every secret embedded in otherwise valid source code.

Content identities are independent of upload order. Reimport can retain the
repository ID while producing a new content identity. Separate imports receive
separate repository IDs, including when their display names are identical.

Validation: 69 local-storage, identity, ingestion and GitHub-reader tests passed
on 2026-09-25. Tests first failed because the importer was absent. Inputs covered
path escape, Windows paths, duplicates, Unicode normalization, exclusions,
changed contents, reimport and UTF-8 byte/count limits at and above boundaries.
