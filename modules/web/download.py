"""Download a file from a URL to a local path (streamed)."""

from __future__ import annotations

from pathlib import Path

import httpx

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0 Safari/537.36")
MAX_BYTES = 500 * 1024 * 1024  # 500 MB guard


def download_file(url: str, save_path: str) -> dict:
    dest = Path(save_path).expanduser()
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with httpx.Client(follow_redirects=True, timeout=60.0,
                          headers={"User-Agent": USER_AGENT}) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        written += len(chunk)
                        if written > MAX_BYTES:
                            f.close()
                            dest.unlink(missing_ok=True)
                            return {"error": "Download exceeded 500 MB limit; aborted."}
                        f.write(chunk)
        return {"status": "downloaded", "path": str(dest.resolve()),
                "bytes": written}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code} downloading {url}"}
    except Exception as e:
        return {"error": f"Failed to download {url}: {e}"}
