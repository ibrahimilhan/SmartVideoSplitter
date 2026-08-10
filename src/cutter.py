import subprocess
import os

# Windows'ta her kesimde konsol penceresi yanip sonmesin.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

def cut_video_segment(input_path: str, output_path: str, start_time: float, end_time: float, precise: bool = False, speed_lvl: str = "Balanced (Medium)", is_gpu: bool = False) -> bool:
    """
    Cuts a segment from the input video and saves it to output_path.
    If precise=True, re-encodes the segment for millimeter precision.
    If precise=False, uses -c copy for lossless, lightning-fast cutting.
    """
    duration = end_time - start_time
    
    # Eger cikti dosyasi zaten varsa, uzerine yazmayip atla
    if os.path.exists(output_path):
        return True
        
    if precise:
        if is_gpu:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_time),
                "-i", input_path,
                "-t", str(duration),
                "-c:v", "h264_nvenc", "-preset", "fast",
                "-c:a", "copy",
                output_path
            ]
        else:
            try:
                thread_count = str(int(speed_lvl.split(" ")[0]))
            except:
                thread_count = "4" # fallback
                
            # 0 means auto/max in FFmpeg, but we extracted exact counts now
            if "Max" in speed_lvl:
                thread_count = "0" 
                
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_time),
                "-i", input_path,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18"
            ]
            
            if thread_count != "0":
                cmd.extend(["-threads", thread_count])
                
            cmd.extend([
                "-c:a", "copy",
                output_path
            ])
    else:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", input_path,
            "-t", str(duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_non_negative",
            output_path
        ]
    
    print(f"[FFMPEG] Cutting: {os.path.basename(output_path)} ({duration:.2f} seconds)")
    
    # KURAL 3/14 — ham byte al, errors='ignore' ile coz (Turkce dosya adlari).
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=_NO_WINDOW)

    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="ignore").strip()
        last_line = err.splitlines()[-1] if err else "unknown error"
        print(f"  [ERROR] Could not cut {os.path.basename(output_path)}: {last_line}")
        return False

    return True
