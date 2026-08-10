import subprocess
import os
from typing import Tuple

def cut_video_segment(input_path: str, output_path: str, start_time: float, end_time: float, precise: bool = False, speed_lvl: str = "Balanced (Medium)") -> bool:
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
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if result.returncode != 0:
        print(f"Error occurred: Could not cut {output_path}.")
        return False
        
    return True
