import glob
import random
import shlex
import subprocess
from pathlib import Path

import requests

from app.config import settings

SUPPORTED_VIDEO_EXTENSIONS = ("*.mp4", "*.mov", "*.mkv", "*.webm")
SUPPORTED_AUDIO_EXTENSIONS = ("*.mp3", "*.wav", "*.m4a")
DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def discover_cod_clips() -> list[str]:
    clip_dir = Path(settings.local_clips_dir)
    if not clip_dir.exists():
        return []

    clips: list[str] = []
    for ext in SUPPORTED_VIDEO_EXTENSIONS:
        clips.extend(glob.glob(str(clip_dir / ext)))
    return sorted(set(clips))


def discover_music_tracks() -> list[str]:
    music_dir = Path(settings.local_music_dir)
    if not music_dir.exists():
        return []

    tracks: list[str] = []
    for ext in SUPPORTED_AUDIO_EXTENSIONS:
        tracks.extend(glob.glob(str(music_dir / ext)))
    return sorted(set(tracks))


def choose_random_cod_clip() -> str:
    clips = discover_cod_clips()
    if not clips:
        raise FileNotFoundError(
            f"No CoD clips found in {settings.local_clips_dir}. Add self-recorded clips first."
        )
    return random.choice(clips)


def choose_random_music() -> str | None:
    tracks = discover_music_tracks()
    if not tracks:
        return None
    return random.choice(tracks)


def download_pexels_fallback_clip(query: str = "cinematic city motion") -> str | None:
    if not settings.pexels_api_key:
        return None

    fallback_dir = Path(settings.local_clips_dir) / "fallback"
    fallback_dir.mkdir(parents=True, exist_ok=True)

    try:
        response = requests.get(
            "https://api.pexels.com/videos/search",
            params={"query": query, "per_page": 15, "orientation": "portrait"},
            headers={"Authorization": settings.pexels_api_key},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None

    videos = payload.get("videos", [])
    if not videos:
        return None

    for video in videos:
        for file_entry in video.get("video_files", []):
            if file_entry.get("file_type") == "video/mp4":
                url = file_entry.get("link")
                if not url:
                    continue
                out_path = fallback_dir / f"pexels_{video.get('id')}.mp4"
                if out_path.exists() and out_path.stat().st_size > 0:
                    return str(out_path)
                try:
                    clip_response = requests.get(url, timeout=90)
                    clip_response.raise_for_status()
                    out_path.write_bytes(clip_response.content)
                    return str(out_path)
                except Exception:
                    continue
    return None


def probe_duration_seconds(path: str) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    output = subprocess.check_output(command, text=True).strip()
    return float(output)


def choose_segment(total_duration: float, min_len: int = 15, max_len: int = 60) -> tuple[float, float]:
    clip_len = min(max_len, max(min_len, int(total_duration)))
    if total_duration <= clip_len:
        return 0.0, float(clip_len)

    start = random.uniform(0, max(0.0, total_duration - clip_len))
    return round(start, 2), float(clip_len)


def _escape_drawtext(text: str) -> str:
    escaped = text.replace("\\", "\\\\")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("'", "\\'")
    escaped = escaped.replace("%", "\\%")
    return escaped


def render_reel(
    clip_path: str,
    voice_path: str,
    script_payload: dict,
    output_path: str,
    start_seconds: float,
    duration_seconds: float,
    music_path: str | None = None,
    vtt_path: str | None = None,
) -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    # We will use the VTT file for subtitle rendering with subtitles filter
    if vtt_path and Path(vtt_path).exists():
        # Escape the colon and backslashes in path for the filter
        esc_vtt_path = vtt_path.replace("\\", "\\\\").replace(":", "\\\\:")
        subtitle_filter = f"subtitles='{esc_vtt_path}':force_style='Alignment=2,MarginV=100,Fontsize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=1,Outline=2'"
    else:
        subtitle_filter = ""

    video_chain = (
        "[0:v]"
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "fps=30,"
        "eq=contrast=1.06:saturation=1.08,"
        "unsharp=5:5:0.8:3:3:0.4"
    )
    if subtitle_filter:
        video_chain += "," + subtitle_filter
    video_chain += "[vout]"

    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start_seconds}",
        "-t",
        f"{duration_seconds}",
        "-i",
        clip_path,
        "-i",
        voice_path,
    ]

    if music_path:
        command.extend(["-stream_loop", "-1", "-i", music_path])

    if music_path:
        audio_chain = "[1:a]volume=1.0[voice];[2:a]volume=0.14[music];[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    else:
        audio_chain = "[1:a]volume=1.0[aout]"

    filter_complex = f"{video_chain};{audio_chain}"

    command.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            output_path,
        ]
    )

    run = subprocess.run(command, capture_output=True, text=True)
    if run.returncode != 0:
        cmd_repr = " ".join(shlex.quote(part) for part in command)
        raise RuntimeError(f"FFmpeg render failed:\n{cmd_repr}\n{run.stderr}")

    return output_path
