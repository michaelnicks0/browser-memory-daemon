from __future__ import annotations

from http.server import ThreadingHTTPServer

from .application import MemoryApplication
from .config import RuntimeConfig
from .db import init_db
from .http_server import create_http_server


def make_server(config: RuntimeConfig) -> ThreadingHTTPServer:
    """Compose the initialized application with the stdlib HTTP adapter."""
    init_db(config)
    application = MemoryApplication(config, database_ready=True)
    return create_http_server(config, application)
