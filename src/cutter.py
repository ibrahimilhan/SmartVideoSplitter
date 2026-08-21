import subprocess
import os

# Windows'ta her kesimde konsol penceresi yanip sonmesin.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

def cut_video_segment(input_path: str, output_path: str, start_time: float, end_time: float, is_precise: bool = False, speed_preset: str = "Balanced (Medium)", is_gpu: bool = False, normalize_audio: bool = False) -> bool:
    """Videodan belirtilen araligi keser (varsayilan olarak stream copy hiziyla)."""
    duration = end_time - start_time
    if duration <= 0:
        return False
        
    audio_args = ["-c:a", "aac", "-b:a", "128k", "-af", "dynaudnorm"] if normalize_audio else ["-c:a", "copy"]

    try:
        if is_gpu:
            cmd = [
                "ffmpeg", "-y",
                "-hwaccel", "cuda",
                "-ss", str(start_time),
                "-i", input_path,
                "-t", str(duration),
                "-c:v", "h264_nvenc", "-preset", "p4",
                "-pix_fmt", "yuv420p"
            ] + audio_args + [output_path]
        else:
            preset_map = {
                "Fast (Lower Quality)": "fast",
                "Balanced (Medium)": "medium",
                "High Quality (Slow)": "slow"
            }
            preset = preset_map.get(speed_preset, "medium")

            if is_precise:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start_time),
                    "-i", input_path,
                    "-t", str(duration),
                    "-c:v", "libx264",
                    "-preset", preset,
                    "-pix_fmt", "yuv420p"
                ] + audio_args + [output_path]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start_time),
                    "-i", input_path,
                    "-t", str(duration),
                    "-c:v", "copy"
                ] + audio_args + [output_path]

        success = _run_quiet(cmd)
        return success and os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        print(f"Error cutting segment: {e}")
        return False

def _run_quiet(cmd) -> bool:
    """FFmpeg komutunu sessizce calistirir ve basariliysa True doner."""
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW, check=True)
        return True
    except subprocess.CalledProcessError:
        return False
