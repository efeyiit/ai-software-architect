"""Run the T22 queue worker separately from the HTTP process."""

from app.security.identity.http import build_identity_http_from_env
from app.services.reporting import ApiRuntime


def main() -> None:
    from threading import Event

    identity = build_identity_http_from_env()
    try:
        runtime = ApiRuntime.from_env(identity)
        try:
            runtime.worker().run_forever(Event())
        except KeyboardInterrupt:
            pass
    finally:
        identity.close()


if __name__ == "__main__":
    main()
