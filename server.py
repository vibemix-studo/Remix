"""VIBE MIX STUDIO companion server: serves the app, imports direct audio links
and .m3u/.pls playlists, and splits vocals/instrumental with Demucs."""
import hashlib, ipaddress, os, re, shutil, socket, subprocess, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

ROOT = Path(__file__).parent
WORK = ROOT / "work"
WORK.mkdir(exist_ok=True)
MAX = int(os.getenv("VMS_MAX_MB", "100")) * 1024 * 1024
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus"}
RIGHTS_MSG = "Confirm that you have the rights to use this audio."

# Remove separation jobs older than 24 hours.
for d in WORK.iterdir():
    if d.is_dir() and time.time() - d.stat().st_mtime > 86400:
        shutil.rmtree(d, ignore_errors=True)

app = FastAPI(title="VIBE MIX STUDIO server")


class ImportReq(BaseModel):
    url: str
    rights: bool = False


def check_url(url: str):
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise HTTPException(400, "Use a full http or https link.")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))
    except socket.gaierror:
        raise HTTPException(400, "That host could not be found.")
    for i in infos:
        ip = ipaddress.ip_address(i[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(400, "Links to private or local addresses are blocked.")


def fetch(url: str):
    for _ in range(4):  # follow redirects manually so every hop is checked
        check_url(url)
        try:
            r = requests.get(url, stream=True, timeout=15, allow_redirects=False,
                             headers={"User-Agent": "VibeMixStudio/1.0"})
        except requests.RequestException:
            raise HTTPException(502, "The link could not be reached.")
        if r.status_code in (301, 302, 303, 307, 308):
            url = urljoin(url, r.headers.get("location", ""))
            continue
        if r.status_code != 200:
            raise HTTPException(502, f"The source answered with status {r.status_code}.")
        return url, r
    raise HTTPException(400, "Too many redirects.")


def read_limited(chunks, limit: int) -> bytes:
    buf = bytearray()
    for c in chunks:
        buf += c
        if len(buf) > limit:
            raise HTTPException(413, f"File is larger than the {limit // 1048576} MB limit.")
    return bytes(buf)


@app.post("/api/import")
def import_url(req: ImportReq):
    if not req.rights:
        raise HTTPException(400, RIGHTS_MSG)
    url, r = fetch(req.url)
    ctype = r.headers.get("content-type", "").split(";")[0].strip()
    ext = Path(urlparse(url).path).suffix.lower()
    if not (ctype.startswith("audio/") or ext in AUDIO_EXT):
        raise HTTPException(415, "This is not a direct audio file. Pages from streaming services such as YouTube or Spotify are not supported.")
    data = read_limited(r.iter_content(65536), MAX)
    name = re.sub(r"[^\w.\- ]", "_", Path(urlparse(url).path).name or "track" + (ext or ".mp3"))
    return Response(data, media_type=ctype or "audio/mpeg", headers={"X-Filename": name})


@app.post("/api/playlist")
def playlist(req: ImportReq):
    if not req.rights:
        raise HTTPException(400, RIGHTS_MSG)
    url, r = fetch(req.url)
    text = read_limited(r.iter_content(65536), 1048576).decode("utf-8", "ignore")
    urls = []
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"(?i)file\d+=", line):
            line = line.split("=", 1)[1]
        elif not line or line.startswith("#") or line.startswith("["):
            continue
        full = urljoin(url, line)
        if urlparse(full).scheme in ("http", "https"):
            urls.append(full)
    if not urls:
        raise HTTPException(415, "No audio links found in that playlist.")
    return {"urls": urls[:20]}


@app.post("/api/separate")
def separate(file: UploadFile = File(...), rights: str = Form("")):
    if rights != "true":
        raise HTTPException(400, RIGHTS_MSG)
    data = read_limited(iter(lambda: file.file.read(65536), b""), MAX)
    ext = Path(file.filename or "").suffix.lower()
    ext = ext if ext in AUDIO_EXT else ".mp3"
    job = hashlib.sha256(data).hexdigest()[:16]
    d = WORK / job
    if not (d / "vocals.wav").exists():
        d.mkdir(exist_ok=True)
        src = d / ("in" + ext)
        src.write_bytes(data)
        p = subprocess.run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-o", str(d / "out"), str(src)],
                           capture_output=True, text=True)
        found = list((d / "out").glob("*/in/vocals.wav"))
        if p.returncode or not found:
            raise HTTPException(500, "Separation failed. Is demucs installed? " + p.stderr[-300:])
        shutil.move(found[0], d / "vocals.wav")
        shutil.move(found[0].parent / "no_vocals.wav", d / "instrumental.wav")
        shutil.rmtree(d / "out", ignore_errors=True)
        src.unlink()
    base = re.sub(r"[^\w.\- ]", "_", Path(file.filename or "track").stem)
    return {"base": base, "stems": {k: f"/api/stem/{job}/{k}" for k in ("vocals", "instrumental")}}


@app.get("/api/stem/{job}/{name}")
def stem(job: str, name: str):
    if not re.fullmatch(r"[0-9a-f]{16}", job) or name not in ("vocals", "instrumental"):
        raise HTTPException(404)
    f = WORK / job / f"{name}.wav"
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, media_type="audio/wav")


@app.get("/addon.js")
def addon():
    return FileResponse(ROOT / "addon.js", media_type="text/javascript")


@app.get("/", response_class=HTMLResponse)
def index():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    return html.replace("</body>", '<script src="/addon.js"></script></body>')


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("VMS_HOST", "127.0.0.1"), port=int(os.getenv("VMS_PORT", "8000")))
