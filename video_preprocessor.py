"""Video preprocessing: extract frames + audio transcripts from MP4s.

Uses ffmpeg (must be installed) for frame/audio extraction and
faster-whisper (pip install faster-whisper) for transcription.
No Claude API dependency — runs entirely locally.
"""

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def extract_audio(video_path: Path, output_wav: Path) -> Path:
    """Extract audio from video as 16kHz mono WAV for Whisper."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            str(output_wav),
        ],
        capture_output=True, check=True,
    )
    logger.info(f"  Extracted audio -> {output_wav.name}")
    return output_wav


def transcribe_audio(wav_path: Path, model) -> str:
    """Transcribe a WAV file using a pre-loaded faster-whisper model.

    Args:
        wav_path: Path to 16kHz mono WAV.
        model: A faster_whisper.WhisperModel instance (loaded once, reused).

    Returns:
        Full transcript as a single string.
    """
    segments, _info = model.transcribe(str(wav_path), beam_size=5)
    texts = [segment.text.strip() for segment in segments]
    transcript = " ".join(texts)
    logger.info(f"  Transcribed {wav_path.name} ({len(transcript)} chars)")
    return transcript


def extract_frames(video_path: Path, output_dir: Path, duration: float, n_frames: int = 3) -> list[Path]:
    """Extract N evenly-spaced frames from a video as JPEGs.

    Default positions: 10%, 50%, 85% of duration.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    positions = [0.10, 0.50, 0.85][:n_frames]
    frame_paths = []

    for i, pct in enumerate(positions):
        timestamp = duration * pct
        out_path = output_dir / f"frame_{i}.jpg"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", f"{timestamp:.2f}",
                "-i", str(video_path),
                "-frames:v", "1",
                "-q:v", "2",
                str(out_path),
            ],
            capture_output=True, check=True,
        )
        frame_paths.append(out_path)

    logger.info(f"  Extracted {len(frame_paths)} frames from {video_path.name}")
    return frame_paths


def preprocess_video(video_path: Path, output_base: Path, model) -> dict:
    """Preprocess a single video: extract frames, audio, and transcribe.

    Args:
        video_path: Path to the MP4 file.
        output_base: Base directory for preprocessed output (e.g. output/video_preprocessed/).
        model: Pre-loaded faster-whisper model.

    Returns:
        Dict with video metadata, transcript, and frame paths.
    """
    stem = video_path.stem
    vid_dir = output_base / stem
    vid_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Preprocessing video: {video_path.name}")

    # Duration
    duration = get_video_duration(video_path)
    logger.info(f"  Duration: {duration:.1f}s")

    # Frames
    frame_paths = extract_frames(video_path, vid_dir, duration)

    # Audio + transcription
    wav_path = vid_dir / "audio.wav"
    extract_audio(video_path, wav_path)
    transcript = transcribe_audio(wav_path, model)

    return {
        "video_filename": video_path.name,
        "video_path": str(video_path),
        "media_type": "video",
        "duration_seconds": round(duration, 1),
        "transcript": transcript,
        "frame_paths": [str(p) for p in frame_paths],
    }


def preprocess_all_videos(video_paths: list[Path], output_base: Path) -> list[dict]:
    """Preprocess all videos sequentially, loading the whisper model once.

    Args:
        video_paths: List of MP4 file paths.
        output_base: Base directory for preprocessed output.

    Returns:
        List of video info dicts.
    """
    if not video_paths:
        return []

    logger.info(f"Loading faster-whisper model (base)...")
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    logger.info("Whisper model loaded")

    results = []
    for i, vp in enumerate(video_paths, 1):
        logger.info(f"Video {i}/{len(video_paths)}: {vp.name}")
        info = preprocess_video(vp, output_base, model)
        results.append(info)

    logger.info(f"Preprocessed {len(results)} video(s)")
    return results
