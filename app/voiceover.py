import contextlib
import struct
import subprocess
import wave
from pathlib import Path

import requests

from app.config import settings
from app.models import Topic


VOICE_MAP = {
    Topic.FINANCE: "elevenlabs_voice_finance",
    Topic.RELATIONSHIPS: "elevenlabs_voice_relationships",
    Topic.HEALTH: "elevenlabs_voice_health",
    Topic.CULTURE: "elevenlabs_voice_culture",
}


def _build_tts_text(script_payload: dict) -> str:
    chunks = [script_payload.get("hook", "")]
    chunks.extend(script_payload.get("lines", []))
    chunks.append(script_payload.get("cta", ""))
    return " ".join([part.strip() for part in chunks if part.strip()])


def _voice_id_for_topic(topic: Topic) -> str:
    setting_name = VOICE_MAP.get(topic)
    if not setting_name:
        return ""
    return getattr(settings, setting_name, "")


def _write_silence_wav(path: Path, seconds: float, sample_rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = int(seconds * sample_rate)

    with contextlib.closing(wave.open(str(path), "wb")) as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        silence_frame = struct.pack("<h", 0)
        wav.writeframes(silence_frame * total_frames)


def synthesize_voiceover(script_payload: dict, topic: Topic, reel_id: str) -> tuple[str, str]:
    output_dir = Path(settings.local_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{reel_id}_voice.wav"

    script_text = _build_tts_text(script_payload)
    word_count = max(1, len(script_text.split()))
    target_seconds = max(15.0, min(60.0, (word_count / 2.6) + 2.0))

    voice_id = _voice_id_for_topic(topic)
    if settings.elevenlabs_api_key and voice_id:
        try:
            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": script_text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.45,
                        "similarity_boost": 0.75,
                        "style": 0.4,
                        "use_speaker_boost": True,
                    },
                },
                timeout=60,
            )
            response.raise_for_status()

            temp_mp3 = output_dir / f"{reel_id}_voice.mp3"
            temp_mp3.write_bytes(response.content)

            # Convert to WAV for easier FFmpeg mixing consistency.
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(temp_mp3),
                    "-ar",
                    "44100",
                    "-ac",
                    "1",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
            )
            if temp_mp3.exists():
                temp_mp3.unlink()

            if output_path.exists() and output_path.stat().st_size > 0:
                return str(output_path), voice_id
        except Exception:
            pass

    # Deterministic offline fallback so full pipeline is runnable without API keys.
    _write_silence_wav(output_path, target_seconds)
    return str(output_path), voice_id
