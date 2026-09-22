from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path


def synthesize_wav(text: str, voice: str, destination: Path, trailing_silence: float) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found; install it before adding announcements")

    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("edge-tts is not installed") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="owntone-announce-") as tmpdir:
        tmp = Path(tmpdir)
        mp3 = tmp / "speech.mp3"
        wav = tmp / "speech.wav"

        asyncio.run(edge_tts.Communicate(text=text, voice=voice).save(str(mp3)))
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(mp3),
                "-af",
                f"apad=pad_dur={float(trailing_silence):.3f}",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(wav),
            ],
            check=True,
        )
        shutil.copyfile(wav, destination)
        destination.chmod(0o644)
