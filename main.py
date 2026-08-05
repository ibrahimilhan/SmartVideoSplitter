import os
import sys
import glob

# src klasorundeki modulleri ice aktaralim
from src.scanner import scan_black_screens, generate_cut_points
from src.ocr_mapper import get_question_number
from src.cutter import cut_video_segment
from src.gallery_maker import create_gallery

def print_banner():
    print("="*50)
    print("       🚀 SMART VIDEO SPLITTER & CUTTER 🚀       ")
    print("="*50)
    print("Otomatik Sinav Videosu Kesici ve Galeri Olusturucu")
    print("="*50)

def process_single_video(video_path: str, output_folder: str):
    """Tek bir videoyu tarar, numaralandirir ve keser."""
    os.makedirs(output_folder, exist_ok=True)
    video_name = os.path.basename(video_path)
    
    print(f"\n[ISLEM] {video_name} isleniyor...")
    
    # 1. Siyah ekran (fade efekti) tespiti
    black_segments = scan_black_screens(video_path)
    cut_points = generate_cut_points(video_path, black_segments)
    
    if not cut_points:
        print("Kesilecek parca bulunamadi!")
        return
        
    print(f"[{video_name}] Toplam {len(cut_points)} soru tespit edildi.")
    
    # 2. Her bir parcayi kes ve OCR ile isimlendir
    for i, (start_time, end_time) in enumerate(cut_points):
        # OCR ile dogru numarayi okumak icin parcanin ortasina yakin bir saniyeyi hedef alalim
        target_time = start_time + min(5.0, (end_time - start_time) / 2)
        q_num_str = get_question_number(video_path, target_time)
        
        # Eger numara bulunamazsa veya 200'den buyukse, sirali bir isim ver
        if q_num_str == "XX":
            q_num_str = f"Soru_{i+1:02d}"
        else:
            q_num_str = f"{q_num_str}_soru"
            
        out_file = os.path.join(output_folder, f"{q_num_str}.mp4")
        
        # 3. Kesim islemi
        cut_video_segment(video_path, out_file, start_time, end_time)
        
    print(f"[BASARILI] {video_name} parcalandi!")

def main():
    print_banner()
    
    while True:
        print("\nNe yapmak istersiniz?")
        print("1. Videolari Parcala (Klasordeki tum MP4'leri keser)")
        print("2. Cevap Galerisi Olustur (Kesilmis videolardan PNG ceker)")
        print("3. Cikis")
        
        choice = input("Seciminiz (1/2/3): ").strip()
        
        if choice == '3':
            print("Cikis yapiliyor. Iyi calismalar!")
            sys.exit(0)
            
        elif choice == '1':
            input_dir = input("\nKesilecek videolarin oldugu klasor yolunu girin:\n> ").strip()
            # Tırnakları temizle
            input_dir = input_dir.strip('"').strip("'")
            
            if not os.path.exists(input_dir):
                print("HATA: Klasor bulunamadi!")
                continue
                
            output_dir = input("Kesilen parcalarin kaydedilecegi klasor yolunu girin:\n> ").strip()
            output_dir = output_dir.strip('"').strip("'")
            
            videos = glob.glob(os.path.join(input_dir, "*.mp4"))
            if not videos:
                print("Klasorde MP4 dosyasi bulunamadi!")
                continue
                
            for v in videos:
                # Video adina uygun alt klasor olustur (ornegin: TYT_Matematik_Cikmis_Sorular klasoru)
                v_name = os.path.splitext(os.path.basename(v))[0]
                out_sub = os.path.join(output_dir, v_name)
                process_single_video(v, out_sub)
                
            print("\nTUM VIDEOLAR KESILDI!")
            
        elif choice == '2':
            input_dir = input("\nKesilmis MP4 parcalarinin bulundugu klasoru girin:\n> ").strip()
            input_dir = input_dir.strip('"').strip("'")
            
            if not os.path.exists(input_dir):
                print("HATA: Klasor bulunamadi!")
                continue
                
            output_dir = input("PNG Galerisinin kaydedilecegi klasoru girin:\n> ").strip()
            output_dir = output_dir.strip('"').strip("'")
            
            create_gallery(input_dir, output_dir)
            
        else:
            print("Gecersiz secim!")

if __name__ == "__main__":
    main()
