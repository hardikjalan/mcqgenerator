"""Server-only database access. Environment is loaded by main before first use."""
import os
from functools import lru_cache
import httpx
from supabase import Client, ClientOptions, create_client


@lru_cache(maxsize=1)
def get_db() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Server database credentials are not configured.")
    transport = httpx.HTTPTransport(retries=2, http2=False)
    http = httpx.Client(transport=transport, timeout=30, limits=httpx.Limits(keepalive_expiry=5))
    return create_client(url, key, options=ClientOptions(httpx_client=http, persist_session=False,
                                                      auto_refresh_token=False))
