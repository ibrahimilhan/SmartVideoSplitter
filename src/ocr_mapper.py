import cv2
import easyocr
import re
import numpy as np

# EasyOCR modelini global olarak bir kez yukle ki her cagridan tekrar yuklemesin
print("[OCR] Yapay Zeka modeli yukleniyor (Bu islem ilk calistirmada 10-15 saniye surebilir)...")
try:
    reader = easyocr.Reader(['tr', 'en'], gpu=False)
except Exception as e:
    print(f"[OCR] Model yuklenemedi: {e}")
    reader = None

def get_question_number(video_path: str, target_time: float) -> str:
    """
    Goes to `target_time` in the video, grabs a frame, and uses OCR
    to detect the question number in the top-left area.
    Returns the question number as a padded string (e.g., "05") or "XX" if not found.
    """
    if reader is None:
        return "XX"
        
    cap = cv2.VideoCapture(video_path)
    
    # Hedef saniyeye git (Milisaniye cinsinden)
    cap.set(cv2.CAP_PROP_POS_MSEC, target_time * 1000)
    ret, frame = cap.read()
    cap.release()
    
    if not ret or frame is None:
        return "XX"
        
    # Resmi gri tonlamaya cevir ve OCR islemine sok
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Sadece sol ust koseyi (soru numarasinin oldugu yer) tarayalim (Hizlandirmak icin)
    h, w = gray.shape
    roi = gray[0:int(h*0.3), 0:int(w*0.3)]
    
    results = reader.readtext(roi, detail=0, paragraph=False)
    
    question_number = "XX"
    for text in results:
        # Metni temizle: sadece rakamlari al (Bazen Soru 1, Soru-1 yazabilir)
        text_clean = re.sub(r'[^0-9]', '', text)
        if text_clean.isdigit():
            num = int(text_clean)
            if 1 <= num <= 200: # Gecerli bir soru numarasi mi?
                question_number = f"{num:02d}"
                break
                
    return question_number
