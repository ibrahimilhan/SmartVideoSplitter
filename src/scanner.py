import subprocess
import numpy as np
import os
import threading

SAFETY_MARGIN = 0.2

def get_video_duration(video_path: str) -> float:
    """FFprobe ile videonun toplam suresini saniye cinsinden ogrenilir."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", video_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0

def coarse_scan(video_path: str, expected_q_count: int = None) -> list:
    """
    Videoyu 1 FPS'e dusurur, gri tonlama raw veriye cevirir ve
    ardisik kareler arasindaki piksel farkini hesaplayarak
    gecis noktalarini (fade, sahne degisimi) tespit eder.
    Bu yontem ffmpeg blackdetect'ten cok daha guvenilirdir.
    """
    print(f"  [SCAN] {os.path.basename(video_path)} - Rough scan started...")
    
    tid = threading.get_ident()
    raw_file = f'frames_raw_{tid}.gray'
    
    subprocess.run([
        'ffmpeg', '-y', '-i', video_path,
        '-vf', 'fps=1,scale=320:180,format=gray',
        '-f', 'rawvideo', '-pix_fmt', 'gray', raw_file
    ], capture_output=True)
    
    frame_size = 320 * 180
    raw_data = np.fromfile(raw_file, dtype=np.uint8)
    num_frames = len(raw_data) // frame_size
    
    if num_frames < 2:
        if os.path.exists(raw_file):
            os.remove(raw_file)
        return []
    
    frames = raw_data[:num_frames * frame_size].reshape(num_frames, 180, 320)
    
    # Ardisik karelerin piksel farklarini hesapla
    diffs = []
    for i in range(1, num_frames):
        diff = np.mean(np.abs(frames[i].astype(float) - frames[i-1].astype(float)))
        diffs.append((i, diff))
    
    if os.path.exists(raw_file):
        os.remove(raw_file)
    
    if expected_q_count is not None and expected_q_count > 0:
        # Eger kullanici bilerek veya yanlislikla cok yuksek bir sayi girdiyse,
        # sadece "gurultu" olan kucuk hareketleri kesmesin diye mutlak bir alt sinir (0.5) koyuyoruz.
        # Bir fade efektinin skoru genelde 2.0 - 10.0 arasidir. 0.5'in alti kesinlikle sadece hareket/gurultudur.
        all_peaks = [(sec, score) for sec, score in diffs if score > 0.5]
    else:
        # Varsayilan guvenli esik degeri
        all_peaks = [(sec, score) for sec, score in diffs if score > 1.0]

    if not all_peaks:
        return []
    
    # Yakin noktalari kumelestir (3 saniye icindeki zirveler tek gecis sayilir)
    clusters = []
    current_cluster = [all_peaks[0]]
    for i in range(1, len(all_peaks)):
        if all_peaks[i][0] - current_cluster[-1][0] <= 3:
            current_cluster.append(all_peaks[i])
        else:
            clusters.append(max(current_cluster, key=lambda x: x[1]))
            current_cluster = [all_peaks[i]]
    clusters.append(max(current_cluster, key=lambda x: x[1]))
    
    # Videonun bas ve sonundaki buyuk degisimleri (intro/outro) filtrele
    inner = []
    for sec, score in clusters:
        if sec <= 2 and score > 5:
            continue
        if sec >= num_frames - 2 and score > 5:
            continue
        inner.append((sec, score))
        
    realistic_q_count = len(inner) + 1
        
    # Eger kullanici soru sayisi girdiyse, en yuksek skora sahip olanlari sec ve sirala
    if expected_q_count is not None and expected_q_count > 0:
        expected_cuts = expected_q_count - 1
        if expected_cuts > 0:
            # Skora gore buyukten kucuge sirala, ilk N tanesini al
            inner.sort(key=lambda x: x[1], reverse=True)
            
            if len(inner) < expected_cuts:
                print(f"  [WARNING] {expected_q_count} parts expected, but only {len(inner)+1} realistic transitions found!")
                print(f"  [WARNING] The rest were ignored to prevent unnecessary cuts.")
            
            inner = inner[:expected_cuts]
            # Tekrar zamana gore sirala
            inner.sort(key=lambda x: x[0])
            
        print(f"  [SCAN] {len(inner)} transition points found.")
        return inner, realistic_q_count
    
    print(f"  [SCAN] {len(inner)} transition points found.")
    return inner

def refine_transitions(video_path: str, coarse_transitions: list, duration: float) -> list:
    """
    Kaba taramada bulunan gecis noktalarini 10 FPS hassasiyetinde tekrar tarar
    ve her gecisin tam baslangiç/bitis zamanlarini belirler.
    """
    if not coarse_transitions:
        return []
        
    print(f"  [PRECISE] Transitions are being precisely scanned...")
    
    refined = []
    for idx, (coarse_sec, coarse_score) in enumerate(coarse_transitions):
        win_start = max(0, coarse_sec - 3)
        win_end = min(coarse_sec + SAFETY_MARGIN, duration)
        win_duration = win_end - win_start
        
        tid = threading.get_ident()
        raw_file = f'fine_{tid}_{idx}.gray'
        subprocess.run([
            'ffmpeg', '-y', '-ss', str(win_start), '-t', str(win_duration),
            '-i', video_path, '-vf', 'fps=10,scale=320:180,format=gray',
            '-f', 'rawvideo', '-pix_fmt', 'gray', raw_file
        ], capture_output=True)
        
        frame_size = 320 * 180
        raw_data = np.fromfile(raw_file, dtype=np.uint8)
        num_frames = len(raw_data) // frame_size
        if num_frames < 2:
            refined.append((coarse_sec - SAFETY_MARGIN, coarse_sec + SAFETY_MARGIN))
            if os.path.exists(raw_file):
                os.remove(raw_file)
            continue
            
        frames = raw_data[:num_frames * frame_size].reshape(num_frames, 180, 320)
        fine_diffs = []
        for i in range(1, num_frames):
            diff = np.mean(np.abs(frames[i].astype(float) - frames[i-1].astype(float)))
            time_sec = win_start + i / 10.0
            fine_diffs.append((time_sec, diff))
            
        exceeding = [(t, d) for t, d in fine_diffs if d > 1.0]
        if exceeding:
            fade_start = exceeding[0][0]
            fade_end = exceeding[-1][0]
            cut_before = fade_start - SAFETY_MARGIN
            cut_after = fade_end + SAFETY_MARGIN
        else:
            cut_before = coarse_sec - SAFETY_MARGIN
            cut_after = coarse_sec + SAFETY_MARGIN
            
        refined.append((cut_before, cut_after))
        if os.path.exists(raw_file):
            os.remove(raw_file)
    return refined

def trim_fadeins(video_path: str, questions: list) -> list:
    """
    Her sorunun basindaki kararma efektini (fade-in) kirpar.
    Boylece video parcasi direkt soruyla baslar, siyahlikla degil.
    """
    trimmed = []
    for i, (start, end) in enumerate(questions):
        tid = threading.get_ident()
        raw_file = f'fade_check_{tid}_{i}.gray'
        
        subprocess.run([
            'ffmpeg', '-y', '-ss', f'{start:.3f}', '-t', '10',
            '-i', video_path, '-vf', 'fps=30,scale=320:180,format=gray',
            '-f', 'rawvideo', '-pix_fmt', 'gray', raw_file
        ], capture_output=True)
        
        frame_size = 320 * 180
        raw_data = np.fromfile(raw_file, dtype=np.uint8)
        num_frames = len(raw_data) // frame_size
        
        new_start = start
        if num_frames >= 2:
            frames = raw_data[:num_frames * frame_size].reshape(num_frames, 180, 320)
            std_dev = np.std(frames[0])
            is_blank = std_dev < 5.0
            
            if is_blank:
                diffs = []
                for j in range(1, num_frames):
                    diff = np.mean(np.abs(frames[j].astype(float) - frames[j-1].astype(float)))
                    diffs.append((j/30.0, diff))
                
                fade_end_time = 0.0
                for t, d in diffs:
                    if d > 1.0:
                        fade_end_time = t
                        
                if fade_end_time > 0:
                    new_start = start + fade_end_time + 0.2
                else:
                    for j in range(1, num_frames):
                        if np.std(frames[j]) > 10.0:
                            new_start = start + (j/30.0) + 0.2
                            break
        
        if new_start == start and i > 0:
            new_start += 0.2
            
        trimmed.append([new_start, end])
        if os.path.exists(raw_file):
            os.remove(raw_file)
            
    return trimmed

def merge_overlaps(questions: list) -> list:
    """15 saniyeden kisa olan parcalari onceki soruyla birlestirir."""
    short_indices = [i for i, q in enumerate(questions) if (q[1] - q[0]) < 15.0]
    for i in short_indices:
        if i > 0:
            questions[i-1][1] = questions[i][1]
    return [q for i, q in enumerate(questions) if i not in short_indices]

def build_questions(refined: list, duration: float) -> list:
    """Gecis noktalarindan soru araliklerini olusturur."""
    if not refined:
        return [[0.0, duration]]
    questions = []
    for i in range(len(refined) + 1):
        if i == 0:
            start = 0.0
            end = refined[0][0]
        elif i == len(refined):
            start = refined[-1][1]
            end = duration
        else:
            start = refined[i-1][1]
            end = refined[i][0]
        questions.append([start, end])
    return questions

def scan_and_build(video_path: str, expected_q_count: int = None) -> list:
    """
    Ana fonksiyon: Videoyu tarar, gecisleri tespit eder,
    hassas tarama yapar, fade-in'leri kirpar ve
    nihai soru araliklerini doner.
    
    Returns: [[start1, end1], [start2, end2], ...] listesi
    """
    duration = get_video_duration(video_path)
    if duration == 0:
        print(f"  [ERROR] {video_path} duration could not be read!")
        return []
    
    # 1. Kaba tarama (1 FPS piksel fark analizi)
    if expected_q_count is not None:
        coarse, realistic_q_count = coarse_scan(video_path, expected_q_count)
    else:
        coarse = coarse_scan(video_path)
    
    # 2. Hassas tarama (10 FPS)
    refined = refine_transitions(video_path, coarse, duration)
    
    # 3. Soru araliklerini olustur
    questions = build_questions(refined, duration)
    
    # 4. Fade-in kirpma
    questions = trim_fadeins(video_path, questions)
    
    # 5. Kisa parcalari birlestir
    questions = merge_overlaps(questions)
    
    print(f"  [RESULT] {len(questions)} parts created.")
    
    if expected_q_count is not None:
        return questions, realistic_q_count
    return questions
