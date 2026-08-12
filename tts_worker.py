import asyncio
import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent
JOB_PATH = ROOT / "job.json"
OUT_DIR = ROOT / "voice_v2"
CACHE_DIR = ROOT / ".tts_cache"


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(r.stdout.strip())


def pct_to_int(rate: str) -> int:
    s = str(rate).strip().replace("%", "")
    return int(s or "0")


def fmt_rate(value: int) -> str:
    value = int(value)
    return f"{value:+d}%" if value else "+0%"


def cache_key(text: str, voice: str, rate: str, pitch: str) -> str:
    payload = json.dumps({"text": text, "voice": voice, "rate": rate, "pitch": pitch}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def synth_to(text: str, voice: str, rate: str, pitch: str, dest: Path, retries: int = 3):
    key = cache_key(text, voice, rate, pitch)
    cached = CACHE_DIR / f"{key}.mp3"
    if cached.exists() and cached.stat().st_size > 1024:
        shutil.copy2(cached, dest)
        return "cache"

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            tmp = dest.with_suffix(f".attempt{attempt}.mp3")
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
            await communicate.save(str(tmp))
            if not tmp.exists() or tmp.stat().st_size <= 1024:
                raise RuntimeError("TTS returned an empty/tiny file")
            tmp.replace(dest)
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, cached)
            return f"generated:{attempt}"
        except Exception as exc:
            last_exc = exc
            await asyncio.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"TTS failed after {retries} attempts: {last_exc}")


async def process_segment(seg, cfg, sem):
    async with sem:
        seg_id = str(seg["id"])
        text = str(seg["text"]).strip()
        start = float(seg["start"])
        end = float(seg["end"])
        window = max(0.1, end - start)
        voice = seg.get("voice", cfg["voice"])
        pitch = seg.get("pitch", cfg.get("pitch", "-2Hz"))
        base_rate = seg.get("rate", cfg.get("default_rate", "-4%"))
        retries = int(cfg.get("retries", 3))
        max_rate = int(cfg.get("max_rate_percent", 18))
        tolerance = float(cfg.get("duration_tolerance", 0.06))

        dest = OUT_DIR / f"{seg_id}.mp3"
        source = await synth_to(text, voice, base_rate, pitch, dest, retries=retries)
        duration = probe_duration(dest)
        final_rate = pct_to_int(base_rate)
        passes = 1

        ratio = duration / window
        if ratio > 1 + tolerance:
            # Approximate extra speech-rate required. Leave a little headroom so the
            # spoken phrase ends before the next source phrase starts.
            required_extra = math.ceil((ratio - 1) * 100) + 2
            candidate = min(max_rate, max(final_rate + 1, final_rate + required_extra))
            if candidate != final_rate:
                final_rate = candidate
                source = await synth_to(text, voice, fmt_rate(final_rate), pitch, dest, retries=retries)
                duration = probe_duration(dest)
                passes += 1

        ratio = duration / window
        if ratio <= 1 + tolerance:
            status = "ok"
        elif ratio <= 1.20:
            status = "tight"
        else:
            status = "adapt_text"

        return {
            "id": seg_id,
            "text": text,
            "start": start,
            "end": end,
            "window": round(window, 3),
            "duration": round(duration, 3),
            "ratio": round(ratio, 4),
            "voice": voice,
            "pitch": pitch,
            "rate": fmt_rate(final_rate),
            "source": source,
            "passes": passes,
            "status": status,
            "file": f"voice_v2/{seg_id}.mp3",
        }


async def main():
    cfg = json.loads(JOB_PATH.read_text(encoding="utf-8"))
    segments = cfg.get("segments", [])
    if not segments:
        raise SystemExit("job.json has no segments")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    max_parallel = max(1, int(cfg.get("max_parallel", 6)))
    sem = asyncio.Semaphore(max_parallel)

    results = await asyncio.gather(*(process_segment(seg, cfg, sem) for seg in segments))
    results.sort(key=lambda x: x["start"])

    summary = {
        "schema": 2,
        "voice": cfg.get("voice"),
        "segment_count": len(results),
        "ok": sum(x["status"] == "ok" for x in results),
        "tight": sum(x["status"] == "tight" for x in results),
        "adapt_text": sum(x["status"] == "adapt_text" for x in results),
        "segments": results,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({k: summary[k] for k in ("segment_count", "ok", "tight", "adapt_text")}, ensure_ascii=False))
    if summary["adapt_text"]:
        print("WARNING: some segments are too long and should be text-adapted before final mix")


if __name__ == "__main__":
    asyncio.run(main())
