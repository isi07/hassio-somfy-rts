"""aiohttp web server for the Somfy RTS Web UI.

Serves static files from web/static/ and registers REST API routes.
Compatible with Home Assistant Ingress (port 8099).
"""

import logging
from pathlib import Path

from aiohttp import web

from .api import AppContext, routes

STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)


def create_app(ctx: AppContext) -> web.Application:
    """Create and configure the aiohttp application.

    Args:
        ctx: Shared application context (gateway, config, wizard, log buffer).

    Returns:
        Configured aiohttp Application ready to be served.
    """
    app = web.Application()
    app["ctx"] = ctx
    app.add_routes(routes)

    # Static assets (CSS, JS)
    if STATIC_DIR.exists():
        app.router.add_static("/static", STATIC_DIR, show_index=False)

    # HTML pages — serve at clean paths and with .html extension
    async def _serve_index(request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def _serve_wizard(request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "wizard.html")

    async def _serve_settings(request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "settings.html")

    async def _serve_logs(request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "logs.html")

    app.router.add_get("/",             _serve_index)
    app.router.add_get("/wizard",       _serve_wizard)
    app.router.add_get("/wizard.html",  _serve_wizard)
    app.router.add_get("/settings",     _serve_settings)
    app.router.add_get("/settings.html",_serve_settings)
    app.router.add_get("/logs",         _serve_logs)
    app.router.add_get("/logs.html",    _serve_logs)

    return app


async def start_server(host: str, port: int, ctx: AppContext) -> web.AppRunner:
    """Start the aiohttp server as an asyncio task.

    Args:
        host: Bind address (e.g. "0.0.0.0").
        port: TCP port (8099 for HA Ingress).
        ctx:  Shared application context.

    Returns:
        AppRunner instance — call runner.cleanup() on shutdown.
    """
    app = create_app(ctx)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Web UI gestartet auf http://%s:%d", host, port)
    return runner
