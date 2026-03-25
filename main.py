import os
import asyncio
import httpx
import aiofiles
import tempfile
from urllib.parse import urlparse

from fastapi import FastAPI, File, UploadFile, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
load_dotenv()

WORKER      = os.getenv("WORKER", "rx2")
ROOT        = os.getenv("ROOT", "converter.app")
SLUG        = os.getenv("SLUG", "audio-to-text")
API_KEY     = os.getenv("API_KEY", "changeme")
USE_HTTP    = os.getenv("USE_HTTP", "false").lower() == "true"

PROTOCOL    = "http" if USE_HTTP else "https"

UPLOAD_URL  = f"{PROTOCOL}://{WORKER}.{ROOT}/{SLUG}/uploader.php"
PROCESS_URL = f"{PROTOCOL}://{WORKER}.{ROOT}/{SLUG}/process.php"
DISPLAY_URL = f"{PROTOCOL}://{WORKER}.{ROOT}/{SLUG}/display.php"
RESULT_URL  = f"{PROTOCOL}://{ROOT}/{SLUG}/result.php"

ALLOWED_TYPES = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
    "audio/ogg", "audio/aac", "audio/x-m4a", "audio/mp4",
    "video/mp4", "video/webm", "video/quicktime"
}

POLL_INTERVAL_SEC = 3      # seconds between status polls
MAX_POLL_ATTEMPTS = 400    # ~20 minutes max wait

# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────
app = FastAPI(
    title="MP3 to Text API",
    description="Converts audio/video files to text using converter.app backend",
    version="1.0.0"
)

# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────
async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
async def upload_file(file_bytes: bytes, filename: str, speaker_detect: str = "Off") -> str:
    """
    Step 1: Upload file to converter.app uploader.
    Returns jobid string.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": f"https://{ROOT}",
        "Referer": f"https://{ROOT}/{SLUG}/",
    }

    # Build options blob (speaker detection)
    options_json = f'{{"speakerDetect": "{speaker_detect}"}}'

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        files = {
            "files[]": (filename, file_bytes, "audio/mpeg"),
            "options":  ("options.json", options_json.encode(), "application/json"),
        }
        data = {"ajax": "1"}

        response = await client.post(UPLOAD_URL, files=files, data=data, headers=headers)

        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Upload failed: HTTP {response.status_code} — {response.text[:300]}"
            )

        try:
            result = response.json()
        except Exception:
            raise HTTPException(
                status_code=502,
                detail=f"Upload response not JSON: {response.text[:300]}"
            )

        jobid = result.get("jobid")
        if not jobid:
            raise HTTPException(
                status_code=502,
                detail=f"No jobid in upload response: {result}"
            )

        return jobid


async def trigger_processing(jobid: str) -> None:
    """
    Step 2: Trigger the processing job.
    """
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://{ROOT}/{SLUG}/",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.post(f"{PROCESS_URL}?jobid={jobid}", headers=headers)


async def poll_progress(jobid: str) -> None:
    """
    Step 3: Poll display.php until progress == 100 or error.
    """
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://{ROOT}/{SLUG}/",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(MAX_POLL_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL_SEC)

            try:
                resp = await client.get(
                    f"{DISPLAY_URL}?jobid={jobid}",
                    headers=headers
                )
                progress = resp.text.strip()
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Polling error: {e}")

            # DRM error
            if progress == "drm-error":
                raise HTTPException(
                    status_code=422,
                    detail="File has DRM protection and cannot be converted."
                )

            # Try parse as float
            try:
                pct = float(progress)
            except ValueError:
                continue  # ignore unexpected responses, keep polling

            if pct >= 100:
                return  # Done!

    raise HTTPException(
        status_code=504,
        detail=f"Conversion timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SEC}s"
    )


async def fetch_result(jobid: str) -> str:
    """
    Step 4: Fetch the transcription result page and extract text.
    """
    result_url = f"{RESULT_URL}?lang=en&w={WORKER}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://{ROOT}/{SLUG}/",
        "Cookie": f"jobId={jobid}",  # site reads jobId from localStorage/cookie
    }

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        # Pass jobid as both cookie and query param for compatibility
        resp = await client.get(
            f"{result_url}&jobid={jobid}",
            headers=headers
        )

        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Result fetch failed: HTTP {resp.status_code}"
            )

        # Try to extract plain text from response
        text = extract_text_from_result(resp.text, jobid)
        return text


def extract_text_from_result(html: str, jobid: str) -> str:
    """
    Parse the result HTML to extract transcribed text.
    Falls back to returning raw HTML if parsing fails.
    """
    try:
        # Try to find text between common result containers
        import re

        # Pattern 1: JSON embedded in page
        json_match = re.search(r'"text"\s*:\s*"(.*?)"(?=\s*[,}])', html, re.DOTALL)
        if json_match:
            return json_match.group(1).replace("\\n", "\n").replace('\\"', '"')

        # Pattern 2: <div id="result"> or <textarea> content
        for pattern in [
            r'<textarea[^>]*>(.*?)</textarea>',
            r'<div[^>]*id=["\']result["\'] [^>]*>(.*?)</div>',
            r'<div[^>]*class=["\']result["\'] [^>]*>(.*?)</div>',
            r'<pre[^>]*>(.*?)</pre>',
        ]:
            match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if match:
                # Strip HTML tags
                raw = match.group(1)
                clean = re.sub(r'<[^>]+>', '', raw).strip()
                if clean:
                    return clean

        # Fallback: strip all HTML
        clean = re.sub(r'<[^>]+>', ' ', html)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean[:5000] if clean else "Could not extract text from result."

    except Exception as e:
        return f"Parse error: {e}\n\nRaw response (first 2000 chars):\n{html[:2000]}"


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "mp3-to-text-api"}


@app.post(
    "/transcribe",
    summary="Convert audio/video file to text",
    response_description="Transcribed text with metadata"
)
async def transcribe(
    file: UploadFile = File(..., description="Audio file (MP3, WAV, M4A, OGG, AAC, MP4, etc.)"),
    speaker_detect: str = "Off",
    _: str = Depends(verify_api_key)
):
    """
    ## Upload an audio file and get back transcribed text.

    **Flow:**
    1. Upload file → get `jobid`
    2. Trigger processing
    3. Poll progress until 100%
    4. Fetch and return transcribed text

    **Headers required:**
    - `x-api-key`: Your API key (set in `.env`)

    **Query params:**
    - `speaker_detect`: `Off` (default) or `On` — distinguish different speakers
    """

    # ── Validate file type ──────────────────────────────────────────
    content_type = file.content_type or ""
    filename     = file.filename or "audio.mp3"
    extension    = filename.rsplit(".", 1)[-1].lower()

    allowed_extensions = {
        "mp3", "wav", "m4a", "ogg", "aac",
        "wma", "mp4", "webm", "mov", "flac"
    }

    if extension not in allowed_extensions and content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: .{extension} ({content_type}). "
                   f"Allowed: {', '.join(sorted(allowed_extensions))}"
        )

    # ── Read file ───────────────────────────────────────────────────
    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(file_bytes) > 500 * 1024 * 1024:  # 500MB limit
        raise HTTPException(status_code=413, detail="File too large. Max 500MB.")

    # ── Run pipeline ────────────────────────────────────────────────
    try:
        # Step 1: Upload
        jobid = await upload_file(file_bytes, filename, speaker_detect)

        # Step 2: Trigger processing
        await trigger_processing(jobid)

        # Step 3: Poll until done
        await poll_progress(jobid)

        # Step 4: Get result
        text = await fetch_result(jobid)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

    return JSONResponse(content={
        "success":        True,
        "jobid":          jobid,
        "filename":       filename,
        "file_size_kb":   round(len(file_bytes) / 1024, 2),
        "speaker_detect": speaker_detect,
        "text":           text,
        "worker":         WORKER,
    })


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
