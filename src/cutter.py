import subprocess
import os
from typing import Tuple

def cut_video_segment(input_path: str, output_path: str, start_time: float, end_time: float) -> bool:
    """
    Cuts a segment from the input video and saves it to output_path.
    Uses -c copy for lossless, lightning-fast cutting without re-encoding.
    """
    duration = end_time - start_time
    
    # Eger cikti dosyasi zaten varsa, uzerine yazmayip atla
    if os.path.exists(output_path):
        return True
        
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
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if result.returncode != 0:
        print(f"Error occurred: Could not cut {output_path}.")
        return False
        
    return True
