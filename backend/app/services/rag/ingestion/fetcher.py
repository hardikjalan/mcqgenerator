"""
fetcher.py
==========
Downloads a source file over HTTP so it can be ingested.

The dashboard never uploads file bytes to this API. It puts the file in a
private Supabase bucket and sends a short-lived signed URL, so this module is
what turns that URL back into bytes.

Two limits are enforced here rather than trusted from the caller:

* **Size** — the browser reports a size in the request, but a request is just
  JSON and anyone can write any number in it. The cap is applied to the bytes
  actually arriving, streamed, so an oversized file is abandoned mid-download
  instead of being fully buffered and then rejected.
* **Time** — a signed URL that hangs would otherwise hold a worker open for
  as long as the client waits.
"""

from __future__ import annotations

import httpx

from app.config import MAX_FILE_BYTES
from app.services.rag.ingestion.exceptions import IngestionError

# Connect / read timeouts. A signed URL points at Supabase storage, which is
# either fast or broken — a long read timeout only delays the error.
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)

_CHUNK = 64 * 1024


class DownloadError(IngestionError):
    """Raised when a source file could not be retrieved."""


def download(url: str, *, file_name: str, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    """
    Fetch *url* and return its bytes.

    Parameters
    ----------
    url:
        A signed, short-lived download URL.
    file_name:
        Original filename — used only to write a readable error message.
    max_bytes:
        Hard ceiling. Exceeding it aborts the download.

    Raises
    ------
    DownloadError
        On a network failure, a non-2xx response, or an oversized file. The
        message is user-safe; the underlying cause goes in ``detail``.
    """
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
            with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise DownloadError(
                        f"Could not download {file_name}. The upload link may "
                        "have expired — try uploading the file again.",
                        detail=f"HTTP {response.status_code} for {file_name}",
                    )

                # Trust-but-verify: if the server declares a length, reject
                # before transferring anything.
                declared = response.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise DownloadError(_too_large(file_name, max_bytes))

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes(_CHUNK):
                    total += len(chunk)
                    if total > max_bytes:
                        raise DownloadError(_too_large(file_name, max_bytes))
                    chunks.append(chunk)

    except DownloadError:
        raise
    except httpx.HTTPError as exc:
        raise DownloadError(
            f"Could not download {file_name}. Please try again.",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    content = b"".join(chunks)
    if not content:
        raise DownloadError(f"{file_name} downloaded as an empty file.")
    return content


def _too_large(file_name: str, max_bytes: int) -> str:
    return (
        f"{file_name} is larger than the {max_bytes // (1024 * 1024)} MB limit."
    )
