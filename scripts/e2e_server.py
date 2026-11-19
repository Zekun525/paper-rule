"""Serve the real application against disposable synthetic memory for Playwright."""
import os
import tempfile
from pathlib import Path

import uvicorn
from e2e_sync_fixture import register_sync_fixture
from fastapi import Header, HTTPException

from paperrule.api.app import create_app


def main():
    root = Path(__file__).resolve().parents[1]
    temporary = root / ".test-tmp"
    temporary.mkdir(exist_ok=True)
    os.environ["PAPERRULE_PROVIDER"] = "manual"
    with (
        tempfile.TemporaryDirectory(prefix="browser-memory-", dir=temporary) as memory,
        tempfile.TemporaryDirectory(prefix="browser-sync-", dir=temporary) as sync_fixture,
    ):
        token = os.environ.get("PAPERRULE_E2E_TOKEN")
        if not token:
            raise RuntimeError("Playwright must supply the synthetic owner token")
        app = create_app(Path(memory), web_root=root / "frontend" / "dist",
                         owner_token=token)
        register_sync_fixture(app, Path(memory), Path(sync_fixture), token)
        server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=int(os.environ.get("PAPERRULE_E2E_PORT", "18765")),
            proxy_headers=False,
        ))

        @app.post("/__e2e/shutdown")
        def shutdown(x_test_token: str = Header(default="")):
            token = os.environ.get("PAPERRULE_E2E_TOKEN")
            if not token or x_test_token != token:
                raise HTTPException(403, "Invalid test shutdown token")
            server.should_exit = True
            return {"status": "stopping"}

        # Register the test-only route before the catch-all static mount.
        app.router.routes.insert(0, app.router.routes.pop())
        server.run()


if __name__ == "__main__":
    main()
