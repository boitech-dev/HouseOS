import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .cinema import relay_router
from .music_outputs import relay_heartbeat, relay_router as music_relay_router


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=relay_heartbeat, name="relay-heartbeat", daemon=True).start()
    from .discovery import announce_loop, discovery_loop

    threading.Thread(target=discovery_loop, name="device-discovery", daemon=True).start()
    threading.Thread(target=announce_loop, name="mdns-announce", daemon=True).start()
    from .events import restart_on_request

    restart_on_request("media")
    yield


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(music_relay_router)
app.include_router(relay_router)
