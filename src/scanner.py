import subprocess
import numpy as np
import os

# ---------------------------------------------------------------------------
# ALGORITMA SABITLERI  (KURAL 15 — bu degerler gercek videolarla deneyerek
# bulundu. Degistirirsen gercek videoyla test et, kor "iyilestirme" yapma.)
# ---------------------------------------------------------------------------
SAFETY_MARGIN = 0.2      # kesim noktasina birakilan pay (sn)
FRAME_W = 320            # analiz cozunurlugu
FRAME_H = 180
FRAME_SIZE = FRAME_W * FRAME_H

COARSE_FPS = 4           # kaba tarama
FINE_FPS = 10            # hassas tarama
FADE_FPS = 30            # fade-in kirpma

DIFF_THRESHOLD = 1.0     # varsayilan gecis esigi (ort. mutlak piksel farki)
DIFF_THRESHOLD_HINTED = 0.5  # kullanici parca sayisi verdiyse daha hassas esik
CLUSTER_GAP = 3.0        # bu araliktaki zirveler tek gecis sayilir (sn)
EDGE_GUARD = 2.0         # video basi/sonundaki intro-outro koruma penceresi (sn)
EDGE_SCORE = 5.0         # intro/outro sayilmasi icin gereken skor
BLANK_STD = 5.0          # kare "bos/siyah" mi (standart sapma)
BRIGHT_STD = 10.0        # kare "dolu" mu
MIN_PART_SEC = 15.0      # bundan kisa parcalar komsusuyla birlestirilir
FADE_PROBE_SEC = 10      # parca basinda fade aranan pencere (sn)
FADEOUT_PROBE_SEC = 15   # son parcanin sonunda kararma aranan pencere (sn)

# Windows'ta her ffmpeg cagrisinda konsol penceresi yanip sonmesin.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


def _run_quiet(args):
    """
    KURAL 3/14 — text=True YOK. Turkce Windows'ta ve Turkce dosya adlarinda
    stderr'in locale ile cozulmesi UnicodeDecodeError ile programi cokertir.
    Ham byte alip errors='ignore' ile coz.
    """
    result = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_NO_WINDOW,
    )
    return result.stdout.decode("utf-8", errors="ignore")


def _gray_frames(args, cancel_event=None):
    """
    ffmpeg'i PIPE ile calistirip gri kareleri tek tek uretir.

    KURAL 8 — ham gri veriyi ASLA diske yazma. Uzun bir video 1 GB+ eder,
    islem yarida kalirsa dosya ortalikta kalir (repoda 7.6 GB birikmisti) ve
    numpy'a komple yuklemek RAM'i patlatir. Burada ayni anda bellekte
    yalnizca tek bir kare (~57 KB) durur.

    Tuketici erken cikarsa (break) pipe kapanir, ffmpeg kendiliginden durur —
    bu kasitli bir hizlandirmadir, bozma.
    """
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=_NO_WINDOW,
    )
    try:
        while True:
            if cancel_event and cancel_event.is_set():
                break
            buf = proc.stdout.read(FRAME_SIZE)
            if buf is None or len(buf) < FRAME_SIZE:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(FRAME_H, FRAME_W)
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
            
        is_cancelled = cancel_event and cancel_event.is_set()
        killed_by_us = False
        
        if proc.poll() is None:
            proc.kill()
            killed_by_us = True
            
        retcode = proc.wait()
        
        # Eger normal isleyis disinda coktuyse, iptal edilmediyse ve biz erken kapatmadiysak
        if retcode != 0 and not is_cancelled and not killed_by_us:
            raise RuntimeError(f"FFmpeg tarama motoru çöktü (Kod: {retcode}).\nEğer 'Use NVENC (GPU)' işaretliyse, ekran kartınız bunu desteklemiyor olabilir. Lütfen tiki kaldırıp CPU ile tekrar deneyin.")


def _ffmpeg_gray_args(video_path, fps, ss=None, t=None, is_gpu=False, cancel_event=None):
    """Gri ham kare uretimi icin ffmpeg argumanlari (stdout'a yazar)."""
    args = ["ffmpeg", "-nostdin", "-v", "error"]
    if is_gpu:
        args += ["-hwaccel", "cuda"]
    if ss is not None:
        args += ["-ss", f"{ss:.3f}"]
    if t is not None:
        args += ["-t", f"{t:.3f}"]
    args += [
        "-i", video_path,
        "-vf", f"fps={fps},scale={FRAME_W}:{FRAME_H},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    return args


def _diff_stream(video_path, fps, ss=None, t=None, t0=0.0, is_gpu=False, cancel_event=None):
    """(zaman, ardisik kare farki) ciftlerini akis halinde uretir."""
    prev = None
    for i, frame in enumerate(_gray_frames(_ffmpeg_gray_args(video_path, fps, ss, t, is_gpu=is_gpu, cancel_event=cancel_event), cancel_event=cancel_event)):
        cur = frame.astype(np.float32)
        if prev is not None:
            yield (t0 + i / fps, float(np.mean(np.abs(cur - prev))))
        prev = cur


def get_video_duration(video_path: str) -> float:
    """FFprobe ile videonun toplam suresini saniye cinsinden ogrenir."""
    out = _run_quiet([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1", video_path
    ])
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def coarse_scan(video_path: str, expected_q_count: int = None, is_gpu: bool = False, cancel_event=None):
    """
    Videoyu COARSE_FPS'e dusurup gri tonlamaya cevirir ve ardisik kareler
    arasindaki piksel farkindan gecis noktalarini (fade, sahne degisimi)
    tespit eder. Bu yontem ffmpeg blackdetect'ten cok daha guvenilirdir.

    KURAL 9 — donus tipi HER ZAMAN (transitions, realistic_q_count).
    """
    print(f"  [SCAN] {os.path.basename(video_path)} - Rough scan started...")

    diffs = list(_diff_stream(video_path, COARSE_FPS, is_gpu=is_gpu, cancel_event=cancel_event))
    if not diffs:
        return [], 1

    total_sec = (len(diffs) + 1) / COARSE_FPS

    # Kullanici parca sayisi verdiyse daha hassas esik kullan; yine de mutlak
    # bir alt sinir birak ki salt hareket/gurultu gecis sayilmasin.
    threshold = DIFF_THRESHOLD_HINTED if (expected_q_count or 0) > 0 else DIFF_THRESHOLD
    all_peaks = [(sec, score) for sec, score in diffs if score > threshold]
    if not all_peaks:
        return [], 1

    # Yakin zirveleri kumelestir — bir fade birden cok kare surer.
    clusters = []
    current = [all_peaks[0]]
    for peak in all_peaks[1:]:
        if peak[0] - current[-1][0] <= CLUSTER_GAP:
            current.append(peak)
        else:
            clusters.append(max(current, key=lambda x: x[1]))
            current = [peak]
    clusters.append(max(current, key=lambda x: x[1]))

    # Videonun bas ve sonundaki buyuk degisimleri (intro/outro) ele
    inner = [
        (sec, score) for sec, score in clusters
        if not (sec <= EDGE_GUARD and score > EDGE_SCORE)
        and not (sec >= total_sec - EDGE_GUARD and score > EDGE_SCORE)
    ]

    realistic_q_count = len(inner) + 1

    # Kullanici parca sayisi verdiyse en guclu N gecisi sec
    if (expected_q_count or 0) > 0:
        expected_cuts = expected_q_count - 1
        if expected_cuts > 0:
            if len(inner) < expected_cuts:
                print(f"  [WARNING] {expected_q_count} parts expected, but only {len(inner)+1} realistic transitions found!")
                print(f"  [WARNING] The rest were ignored to prevent unnecessary cuts.")
            inner.sort(key=lambda x: x[1], reverse=True)
            inner = inner[:expected_cuts]
            inner.sort(key=lambda x: x[0])
        else:
            inner = []

    print(f"  [SCAN] {len(inner)} transition points found.")
    return inner, realistic_q_count


def refine_transitions(video_path: str, coarse_transitions: list, duration: float, is_gpu: bool = False, cancel_event=None) -> list:
    """
    Kaba taramada bulunan gecisleri FINE_FPS hassasiyetinde tekrar tarar ve
    her gecisin tam baslangic/bitis zamanini belirler.
    """
    if not coarse_transitions:
        return []

    print(f"  [PRECISE] Transitions are being precisely scanned...")

    refined = []
    for coarse_sec, _score in coarse_transitions:
        win_start = max(0.0, coarse_sec - 3.0)
        win_end = min(coarse_sec + SAFETY_MARGIN, duration)
        win_duration = win_end - win_start

        exceeding = []
        if win_duration > 0:
            exceeding = [
                (t, d) for t, d in _diff_stream(
                    video_path, FINE_FPS, ss=win_start, t=win_duration, t0=win_start, is_gpu=is_gpu, cancel_event=cancel_event
                ) if d > DIFF_THRESHOLD
            ]

        if exceeding:
            cut_before = exceeding[0][0] - SAFETY_MARGIN
            cut_after = exceeding[-1][0] + SAFETY_MARGIN
        else:
            cut_before = coarse_sec - SAFETY_MARGIN
            cut_after = coarse_sec + SAFETY_MARGIN

        refined.append((cut_before, cut_after))
    return refined


def trim_fadeins(video_path: str, questions: list, is_gpu: bool = False, cancel_event=None) -> list:
    """
    Her parcanin basindaki kararma efektini (fade-in) kirpar; boylece parca
    siyahlikla degil dogrudan icerikle baslar.

    Parca zaten siyah baslamiyorsa ilk karede cikilir — pipe kapanir, ffmpeg
    durur. Yaygin durum bu oldugu icin buyuk hiz kazanci saglar.
    """
    trimmed = []
    for i, (start, end) in enumerate(questions):
        new_start = start
        prev = None
        last_fade_time = 0.0
        first_bright_time = None

        # BUG FIX: Clamp probe time so it doesn't overshoot into the next segment
        probe_window = min(FADE_PROBE_SEC, max(0.1, end - start))
        args = _ffmpeg_gray_args(video_path, FADE_FPS, ss=start, t=probe_window, is_gpu=is_gpu, cancel_event=cancel_event)
        for j, frame in enumerate(_gray_frames(args, cancel_event=cancel_event)):
            cur = frame.astype(np.float32)

            if j == 0:
                if float(np.std(cur)) >= BLANK_STD:
                    break  # siyahla baslamiyor -> kirpacak bir sey yok
                prev = cur
                continue

            if float(np.mean(np.abs(cur - prev))) > DIFF_THRESHOLD:
                last_fade_time = j / FADE_FPS
            if first_bright_time is None and float(np.std(cur)) > BRIGHT_STD:
                first_bright_time = j / FADE_FPS
            prev = cur

        if last_fade_time > 0:
            new_start = start + last_fade_time + SAFETY_MARGIN
        elif first_bright_time is not None:
            new_start = start + first_bright_time + SAFETY_MARGIN

        if new_start == start and i > 0:
            new_start += SAFETY_MARGIN

        trimmed.append([new_start, end])

    return trimmed


def trim_final_fadeout(video_path: str, questions: list, is_gpu: bool = False, cancel_event=None) -> list:
    """
    Son parcanin sonundaki kararmayi kirpar.

    1..N-1 numarali parcalarin bitisi tespit edilen gecisten turetilir
    (fade_start - SAFETY_MARGIN), yani zaten temizdir. Son parcanin bitisi
    ise videonun kendi sonudur ve kapanis fade'ini icerebilir — hedef
    "parcada fade gorunmesin" oldugu icin burasi ayrica kirpilir.
    """
    if not questions:
        return questions

    start, end = questions[-1]
    window = min(FADEOUT_PROBE_SEC, max(0.0, end - start))
    if window <= 0:
        return questions

    probe_start = end - window
    last_content = None
    for j, frame in enumerate(_gray_frames(
            _ffmpeg_gray_args(video_path, FADE_FPS, ss=probe_start, t=window, is_gpu=is_gpu, cancel_event=cancel_event))):
        if float(np.std(frame)) >= BLANK_STD:
            last_content = probe_start + j / FADE_FPS

    if last_content is None:
        # Pencerenin tamami siyah — en azindan bildigimiz kadarini at.
        questions[-1][1] = probe_start
    elif last_content < end:
        questions[-1][1] = min(end, last_content + 1.0 / FADE_FPS)

    return questions


def merge_overlaps(questions: list, min_len: float = MIN_PART_SEC) -> list:
    """
    MIN_PART_SEC'ten kisa parcalari komsusuyla birlestirir.

    KURAL 16 — kisa parca SILINMEZ, birlestirilir. Onceki eski surum ilk parca
    kisaysa onu sessizce dusuruyordu (videonun basi kayboluyordu) ve ardisik
    kisa parcalarda birlestirmeyi zaten silinmis bir ogeye yaziyordu.
    Burada her zaman "onceki KALAN parca"ya eklenir; henuz kalan parca yoksa
    parca bir sonrakinin basina tasinir.
    """
    if not questions:
        return []

    merged = []
    carry_start = None
    for start, end in questions:
        if carry_start is not None:
            start = carry_start
            carry_start = None

        if (end - start) >= min_len:
            merged.append([start, end])
        elif merged:
            merged[-1][1] = end          # onceki kalan parcayi uzat
        else:
            carry_start = start          # basta birikiyor -> sonrakine tasi

    if carry_start is not None:
        # Hicbir parca esigi gecemedi; tumunu tek parca yap (icerik kaybetme).
        merged.append([carry_start, questions[-1][1]])

    return merged


def build_questions(refined: list, duration: float) -> list:
    """Gecis noktalarindan parca araliklarini olusturur."""
    if not refined:
        return [[0.0, duration]]
    questions = []
    for i in range(len(refined) + 1):
        if i == 0:
            start, end = 0.0, refined[0][0]
        elif i == len(refined):
            start, end = refined[-1][1], duration
        else:
            start, end = refined[i-1][1], refined[i][0]
        questions.append([start, end])
    return questions


def scan_and_build(video_path: str, expected_q_count: int = None, is_gpu: bool = False, cancel_event=None):
    """
    Ana fonksiyon: videoyu tarar, gecisleri bulur, hassas tarama yapar,
    fade-in'leri kirpar ve nihai parca araliklarini doner.

    KURAL 9 — donus tipi HER ZAMAN (questions, realistic_q_count).
      questions: [[start1, end1], [start2, end2], ...]
    """
    duration = get_video_duration(video_path)
    if duration == 0:
        print(f"  [ERROR] {video_path} duration could not be read!")
        return [], 1

    coarse, realistic_q_count = coarse_scan(video_path, expected_q_count, is_gpu, cancel_event)
    if cancel_event and cancel_event.is_set(): return [], 0
    
    refined = refine_transitions(video_path, coarse, duration, is_gpu, cancel_event)
    if cancel_event and cancel_event.is_set(): return [], 0
    
    questions = build_questions(refined, duration)
    questions = trim_fadeins(video_path, questions, is_gpu, cancel_event)
    if cancel_event and cancel_event.is_set(): return [], 0
    
    questions = merge_overlaps(questions)
    questions = trim_final_fadeout(video_path, questions, is_gpu, cancel_event)

    print(f"  [RESULT] {len(questions)} parts created.")
    return questions, realistic_q_count
