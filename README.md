# VIBE MIX STUDIO server

Runs the studio locally and adds two features the browser-only version cannot do:

- Import a direct audio link, or an .m3u/.m3u8/.pls playlist of direct links.
- Split a song into vocals and instrumental with Demucs.

## Setup
1. Install Python 3.10+ and ffmpeg.
2. `pip install -r requirements.txt` (Demucs installs PyTorch; the first split downloads a model).
3. `python server.py`, then open http://127.0.0.1:8000

Settings: `VMS_PORT`, `VMS_HOST` (default 127.0.0.1; keep it local unless you add authentication), `VMS_MAX_MB` (default 100).

## Notes
- Links must point straight to an audio file. YouTube, Spotify and similar pages are not supported, and the server does not rip streaming services.
- The user must confirm they have the rights to the audio. Private and local addresses are blocked and redirects are re-checked, but this is not a hardened public service: add authentication and rate limits before exposing it to the internet.
- Separation jobs are stored in `work/` and deleted after 24 hours at the next start.
- A CPU split of a 4-minute song can take several minutes; a GPU is much faster.
