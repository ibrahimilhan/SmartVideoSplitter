import subprocess
import os
import glob
from tqdm import tqdm

def create_gallery(video_folder: str, output_folder: str):
    """
    Scans a folder for .mp4 files, extracts a frame near the end of each,
    and saves them as full-resolution PNG images in the output_folder.
    """
    os.makedirs(output_folder, exist_ok=True)
    
    videos = glob.glob(os.path.join(video_folder, "*.mp4"))
    videos.sort()
    
    if not videos:
        print(f"[{video_folder}] icinde hic MP4 dosyasi bulunamadi.")
        return
        
    print(f"\n[Galeri] {os.path.basename(video_folder)} klasoru icin {len(videos)} PNG cekiliyor...")
    
    for video_path in tqdm(videos, desc="PNG Cekimi", unit="video"):
        video_name = os.path.basename(video_path)
        img_name = video_name.replace(".mp4", ".png")
        img_path = os.path.join(output_folder, img_name)
        
        # Eger resim zaten varsa atla
        if os.path.exists(img_path):
            continue
            
        try:
            # 1. Videonun suresini al
            cmd_dur = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of",
                "default=noprint_wrappers=1:nokey=1", video_path
            ]
            result = subprocess.run(cmd_dur, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            duration = float(result.stdout.strip())
            
            # 2. Videonun bitmesine 1 saniye kala (veya en az 0.1 saniye kala) hedef zamani belirle
            # Boylece fade-out (kararma) efektinin icinde kalmayiz
            target_time = max(0.1, duration - 1.0)
            
            # 3. FFmpeg ile o saniyeden 1 kare al
            cmd_extract = [
                "ffmpeg", "-y", "-ss", str(target_time), "-i", video_path,
                "-frames:v", "1", "-q:v", "2", img_path
            ]
            subprocess.run(cmd_extract, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        except Exception as e:
            print(f"  [HATA] {video_name} icin galeri resmi alinamadi: {e}")
            
    print(f"[Galeri] Basariyla tamamlandi. Cikti: {output_folder}")
