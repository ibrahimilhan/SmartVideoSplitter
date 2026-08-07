import os
import sys
import threading
import glob
import time
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, font as tkfont
from tkinterdnd2 import TkinterDnD, DND_FILES

# Modulleri ice aktaralim
from src.scanner import scan_and_build
from src.cutter import cut_video_segment


# ========== RENK PALETI ==========
COLORS = {
    "bg_dark":       "#0b0c13", # Çok koyu lacivert/siyah (uzay grisi)
    "bg_card":       "#131521", # Paneller için hafif lacivert
    "bg_card_alt":   "#1a1d2e", # Biraz daha açık vurgu paneli
    "accent":        "#b8257b", # Yumuşatılmış Magenta (Pembe/Mor)
    "accent_hover":  "#db3397", 
    "accent2":       "#18869c", # Yumuşatılmış Teal (Turkuaz/Mavi)
    "text_primary":  "#e6ecf0", # Beyaza yakın çok açık mavi
    "text_secondary":"#8b99a6", # Soluk metalik gri
    "text_muted":    "#556170", 
    "success":       "#27b376", # Yumuşatılmış teknolojik yeşil
    "warning":       "#e0aa0f", 
    "log_bg":        "#06070a", # Log için en koyu siyah
    "log_fg":        "#2bc4d1", # Log metinleri için turkuaz
    "overlay_bg":    "#0d101c",
    "border":        "#243b4d", # Çok hafif turkuaz yansımalı kenarlık
}

class RedirectText:
    """Konsol ciktilarini (print) Tkinter text widget'ina yonlendirmek icin sinif"""
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, string):
        self.text_widget.configure(state="normal")
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)
        self.text_widget.configure(state="disabled")

    def flush(self):
        pass


class SmartVideoSplitterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SmartVideoSplitter")
        self.root.geometry("1020x700")
        self.root.configure(bg=COLORS["bg_dark"])
        self.root.minsize(900, 600)
        
        # Icon olmasa bile taskbar'da guzel gorunsun
        self.root.option_add("*tearOff", False)
        
        self.is_processing = False
        self._overlay_visible = False
        self._hide_timer = None
        self.setup_fonts()
        self.setup_ui()
        self.setup_dnd()
        
        sys.stdout = RedirectText(self.log_area)
        
    def setup_fonts(self):
        self.font_title = ("Consolas", 26, "bold") # Ana baslik icin teknolojik font
        self.font_subtitle = ("Segoe UI", 11)
        self.font_body = ("Segoe UI", 10)
        self.font_body_bold = ("Segoe UI", 10, "bold")
        self.font_log = ("Consolas", 10)
        self.font_overlay = ("Consolas", 32, "bold")
        self.font_warning_title = ("Segoe UI", 11, "bold")
        self.font_small = ("Segoe UI", 9)
        self.font_stat = ("Courier New", 36, "bold") # Rakamlar icin teknolojik font
        self.font_stat_label = ("Segoe UI", 9)

    def create_rounded_frame(self, parent, bg_color, pad=15):
        """Kartin etrafinda ince bir border efekti olustur"""
        outer = tk.Frame(parent, bg=COLORS["border"], padx=1, pady=1)
        inner = tk.Frame(outer, bg=bg_color, padx=pad, pady=pad)
        inner.pack(fill=tk.BOTH, expand=True)
        return outer, inner

    def setup_ui(self):
        # SCROLLBAR STILI
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use('clam')
        style.configure("Cyber.Vertical.TScrollbar",
                        background=COLORS["border"],
                        troughcolor=COLORS["log_bg"],
                        bordercolor=COLORS["log_bg"],
                        arrowcolor=COLORS["accent2"],
                        relief="flat")
        style.map("Cyber.Vertical.TScrollbar",
                  background=[('active', COLORS["accent"])])
                  
        # BANNER (Gorsel Sölen) - Ekranin kenarlarina degmesi icin dogrudan root'a ekliyoruz
        banner_path = os.path.join("assets", "banner.jpg")
        if os.path.exists(banner_path):
            try:
                from PIL import Image, ImageTk
                img = Image.open(banner_path)
                
                # Cok genis bir ekran boyutunda bile kenarlarin bos kalmamasi icin genisligi 2500 yapiyoruz
                img_w, img_h = img.size
                target_w, target_h = 2500, 180
                
                crop_h = int(img_w * (target_h / target_w))
                top = (img_h - crop_h) // 2
                bottom = top + crop_h
                
                if top < 0: top = 0
                if bottom > img_h: bottom = img_h
                
                img_cropped = img.crop((0, top, img_w, bottom))
                img_resized = img_cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
                
                self.banner_img = ImageTk.PhotoImage(img_resized)
                
                banner_lbl = tk.Label(self.root, image=self.banner_img, bg=COLORS["bg_dark"], bd=0)
                banner_lbl.pack(fill=tk.X)
            except Exception as e:
                print(f"Banner yuklenirken hata: {e}")

        # Ana container (Tum bilesenler bunun icinde)
        main_container = tk.Frame(self.root, bg=COLORS["bg_dark"], padx=32, pady=24)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # ===== HEADER BOLUMU (Yazi Tabanli Sik Tasarim) =====
        header = tk.Frame(main_container, bg=COLORS["bg_dark"])
        header.pack(fill=tk.X, pady=(0, 24))
        
        title_frame = tk.Frame(header, bg=COLORS["bg_dark"])
        title_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Alt baslik
        tk.Label(title_frame, text="Automatically split educational videos with AI",
                 font=("Segoe UI", 12), fg=COLORS["accent2"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(4, 12))
                 
        # Estetik ayrac cizgisi (Neon vurgu)
        separator = tk.Frame(title_frame, bg=COLORS["accent"], height=2)
        separator.pack(fill=tk.X, anchor="w", pady=(0, 4))
        
        # Versiyon etiketi sag ust
        ver_frame = tk.Frame(header, bg=COLORS["bg_card"], padx=14, pady=6)
        ver_frame.pack(side=tk.RIGHT, anchor="ne")
        tk.Label(ver_frame, text="v2.0 Cyberpunk", font=("Consolas", 10, "bold"),
                 fg=COLORS["accent2"], bg=COLORS["bg_card"]).pack()

        # ===== UYARI KARTI =====
        warn_outer, warn_inner = self.create_rounded_frame(main_container, COLORS["bg_card"], pad=12)
        warn_outer.pack(fill=tk.X, pady=(0, 12))
        
        # Uyari basligi
        warn_header = tk.Frame(warn_inner, bg=COLORS["bg_card"])
        warn_header.pack(fill=tk.X, pady=(0, 6))
        
        tk.Label(warn_header, text="⚠",
                 font=("Segoe UI", 14), fg=COLORS["warning"],
                 bg=COLORS["bg_card"]).pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(warn_header, text="Before You Start",
                 font=self.font_warning_title, fg=COLORS["warning"],
                 bg=COLORS["bg_card"]).pack(side=tk.LEFT)
        
        warnings = [
            ("FFmpeg", "FFmpeg must be installed on your system.", True),
            ("Transition Effect", "A 'Fade to Black' transition between parts is mandatory.", False)
        ]
        for tag, desc, has_btn in warnings:
            row = tk.Frame(warn_inner, bg=COLORS["bg_card"])
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text="›", font=self.font_body_bold, fg=COLORS["accent"],
                     bg=COLORS["bg_card"]).pack(side=tk.LEFT, padx=(8, 6))
            tk.Label(row, text=tag, font=self.font_body_bold, fg=COLORS["text_primary"],
                     bg=COLORS["bg_card"]).pack(side=tk.LEFT)
            tk.Label(row, text=f" — {desc}", font=self.font_body, fg=COLORS["text_secondary"],
                     bg=COLORS["bg_card"]).pack(side=tk.LEFT)
            if has_btn:
                tk.Button(row, text="How to Install?", font=self.font_small, bg=COLORS["accent"],
                          fg="white", relief=tk.FLAT, cursor="hand2", padx=6, pady=0,
                          command=self._show_ffmpeg_install).pack(side=tk.LEFT, padx=(10, 0))

        # ===== VIDEO SECME BUTONLARI =====
        btn_frame = tk.Frame(main_container, bg=COLORS["bg_dark"])
        btn_frame.pack(fill=tk.X, pady=(0, 12))
        
        btn_file = tk.Button(btn_frame, text="🎬 Select Video File", bg=COLORS["accent2"], fg="white",
                  font=self.font_body_bold, padx=14, pady=6, relief=tk.FLAT, cursor="hand2",
                  activebackground=COLORS["accent"], activeforeground="white",
                  command=self.browse_files)
        btn_file.pack(side=tk.LEFT, padx=(0, 8))
        btn_file.bind("<Enter>", lambda e: btn_file.config(bg=COLORS["accent"]))
        btn_file.bind("<Leave>", lambda e: btn_file.config(bg=COLORS["accent2"]))
        
        btn_folder = tk.Button(btn_frame, text="📁 Select Folder", bg=COLORS["accent2"], fg="white",
                  font=self.font_body_bold, padx=14, pady=6, relief=tk.FLAT, cursor="hand2",
                  activebackground=COLORS["accent"], activeforeground="white",
                  command=self.browse_folder)
        btn_folder.pack(side=tk.LEFT, padx=(0, 16))
        btn_folder.bind("<Enter>", lambda e: btn_folder.config(bg=COLORS["accent"]))
        btn_folder.bind("<Leave>", lambda e: btn_folder.config(bg=COLORS["accent2"]))
        
        # Soru sayisi giris alani
        lbl_q = tk.Label(btn_frame, text="Expected Parts:", font=self.font_body_bold,
                         fg=COLORS["text_secondary"], bg=COLORS["bg_dark"])
        lbl_q.pack(side=tk.LEFT, padx=(0, 4))
        
        self.entry_q_count = tk.Entry(btn_frame, font=self.font_body, bg=COLORS["bg_card"],
                                      fg=COLORS["text_primary"], width=6, relief=tk.FLAT,
                                      insertbackground=COLORS["text_primary"])
        self.entry_q_count.pack(side=tk.LEFT, ipady=4, padx=(0, 8))
        
        tk.Label(btn_frame, text="(Optional)", font=self.font_small,
                 fg=COLORS["text_muted"], bg=COLORS["bg_dark"]).pack(side=tk.LEFT)

        # ===== ISTATISTIK KARTLARI =====
        stats_frame = tk.Frame(main_container, bg=COLORS["bg_dark"])
        stats_frame.pack(fill=tk.X, pady=(0, 12))
        
        self.stat_video_count = tk.StringVar(value="0")
        self.stat_question_count = tk.StringVar(value="0")
        self.stat_status = tk.StringVar(value="Waiting")
        
        stat_data = [
            (self.stat_video_count, "Video", COLORS["accent"]),
            (self.stat_question_count, "Part Detection", COLORS["success"]),
            (self.stat_status, "Status", COLORS["warning"]),
        ]
        
        for i, (var, label, color) in enumerate(stat_data):
            s_outer, s_inner = self.create_rounded_frame(stats_frame, COLORS["bg_card"], pad=10)
            s_outer.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0 if i == 0 else 4, 0 if i == len(stat_data)-1 else 4))
            
            tk.Label(s_inner, textvariable=var, font=self.font_stat, fg=color,
                     bg=COLORS["bg_card"]).pack()
            tk.Label(s_inner, text=label, font=self.font_stat_label, fg=COLORS["text_muted"],
                     bg=COLORS["bg_card"]).pack()

        # ===== ALT BOLUM: BILGI PANELI + LOG =====
        bottom_frame = tk.Frame(main_container, bg=COLORS["bg_dark"])
        bottom_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- SOL: BILGI PANELI ---
        info_outer, info_inner = self.create_rounded_frame(bottom_frame, COLORS["bg_card"], pad=12)
        info_outer.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        
        tk.Label(info_inner, text="📊 Video Information", font=self.font_body_bold,
                 fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(0, 10))
        
        # Info panel degiskenleri
        self.info_vars = {}
        info_fields = [
            ("video_adi",       "🎬 Video Name"),
            ("video_suresi",    "⏱️ Video Duration"),
            ("cozunurluk",      "📐 Resolution"),
            ("dosya_boyutu",    "💾 File Size"),
            ("parca_sayisi",    "✂️ Part Count"),
            ("gecen_sure",      "⏳ Elapsed Time"),
            ("tahmini_kalan",   "📈 Est. Remaining"),
            ("islem_hizi",      "⚡ Processing Speed"),
        ]
        
        for key, label in info_fields:
            row = tk.Frame(info_inner, bg=COLORS["bg_card"])
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=label, font=self.font_small, fg=COLORS["text_muted"],
                     bg=COLORS["bg_card"], width=14, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value="—")
            self.info_vars[key] = var
            tk.Label(row, textvariable=var, font=self.font_body_bold, fg=COLORS["text_primary"],
                     bg=COLORS["bg_card"], anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- SAG: LOG ALANI ---
        log_outer, log_inner = self.create_rounded_frame(bottom_frame, COLORS["log_bg"], pad=0)
        log_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.log_outer = log_outer
        
        log_header = tk.Frame(log_inner, bg=COLORS["bg_card_alt"], padx=12, pady=6)
        log_header.pack(fill=tk.X)
        
        left_header = tk.Frame(log_header, bg=COLORS["bg_card_alt"])
        left_header.pack(side=tk.LEFT)
        
        self.live_dot = tk.Label(left_header, text="●", font=("Segoe UI", 8),
                                 fg=COLORS["text_muted"], bg=COLORS["bg_card_alt"])
        self.live_dot.pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(left_header, text="Process Log", font=self.font_body_bold,
                 fg=COLORS["text_secondary"], bg=COLORS["bg_card_alt"]).pack(side=tk.LEFT)
        
        self.log_area = tk.Text(log_inner, bg=COLORS["log_bg"], fg=COLORS["log_fg"],
                                font=self.font_log, relief=tk.FLAT, borderwidth=0,
                                padx=12, pady=8, wrap=tk.WORD, state="disabled",
                                insertbackground=COLORS["log_fg"],
                                selectbackground=COLORS["accent2"])
        
        scrollbar = ttk.Scrollbar(log_inner, orient=tk.VERTICAL, command=self.log_area.yview, style="Cyber.Vertical.TScrollbar")
        self.log_area.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ===== SURUKLE BIRAK OVERLAY (sadece log alani uzerinde) =====
        self.overlay = tk.Frame(self.log_outer, bg=COLORS["overlay_bg"])
        
        overlay_content = tk.Frame(self.overlay, bg=COLORS["overlay_bg"])
        overlay_content.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        tk.Label(overlay_content, text="📥", font=("Segoe UI", 28),
                 bg=COLORS["overlay_bg"], fg="white").pack()
        tk.Label(overlay_content, text="DROP VIDEO HERE",
                 font=("Segoe UI", 18, "bold"), bg=COLORS["overlay_bg"], fg="white").pack(pady=(4, 0))
        tk.Label(overlay_content, text="Drag and drop MP4 files or a folder",
                 font=self.font_subtitle, bg=COLORS["overlay_bg"], fg="#aaaaaa").pack(pady=(4, 0))
        
        # Hosgeldin mesaji
        self.log_area.configure(state="normal")
        self.log_area.insert(tk.END, "SmartVideoSplitter is ready.\n")
        self.log_area.insert(tk.END, "Drag and drop a video or folder onto this window.\n\n")
        self.log_area.configure(state="disabled")

    def _ask_user_action_sync(self, title, message):
        """Arka plan is parcacigindan ozel 3 secenekli bir diyalog penceresi acar."""
        import threading
        answer = ["skip"]
        event = threading.Event()
        
        def _ask():
            top = tk.Toplevel(self.root)
            top.title(title)
            top.geometry("480x280")
            top.configure(bg=COLORS["bg_dark"])
            top.attributes('-topmost', True)
            top.grab_set()
            
            lbl = tk.Label(top, text=message, font=self.font_body, fg=COLORS["text_primary"], bg=COLORS["bg_dark"], justify=tk.LEFT, wraplength=450)
            lbl.pack(pady=20, padx=15)
            
            btn_frame = tk.Frame(top, bg=COLORS["bg_dark"])
            btn_frame.pack(pady=10)
            
            def set_ans(val):
                answer[0] = val
                top.destroy()
                event.set()
                
            tk.Button(btn_frame, text="Force Split by My Count", bg=COLORS["warning"], fg="white", 
                      font=self.font_body_bold, padx=8, pady=4, relief=tk.FLAT, cursor="hand2",
                      command=lambda: set_ans("force")).pack(side=tk.LEFT, padx=5)
                      
            tk.Button(btn_frame, text="Split by AI Count", bg=COLORS["success"], fg="white", 
                      font=self.font_body_bold, padx=8, pady=4, relief=tk.FLAT, cursor="hand2",
                      command=lambda: set_ans("ai")).pack(side=tk.LEFT, padx=5)
                      
            tk.Button(btn_frame, text="Skip Video", bg=COLORS["bg_card"], fg="white", 
                      font=self.font_body_bold, padx=8, pady=4, relief=tk.FLAT, cursor="hand2",
                      command=lambda: set_ans("skip")).pack(side=tk.LEFT, padx=5)
            
            top.protocol("WM_DELETE_WINDOW", lambda: set_ans("skip"))
            
        self.root.after(0, _ask)
        event.wait()
        return answer[0]

    def _reset_ui(self):
        """Arayuzdeki statulari ve loglari varsayilan hale getirir."""
        self.stat_video_count.set("0")
        self.stat_question_count.set("0")
        self.stat_status.set("Waiting")
        
        self._update_info("video_adi", "—")
        self._update_info("video_suresi", "—")
        self._update_info("cozunurluk", "—")
        self._update_info("dosya_boyutu", "—")
        self._update_info("parca_sayisi", "0")
        
        # self.entry_q_count.delete(0, tk.END) # Kullanici deger girdiyse korunsun
        
        self.log_area.configure(state="normal")
        self.log_area.delete(1.0, tk.END)
        self.log_area.configure(state="disabled")

    def _show_ffmpeg_install(self):
        """Kullaniciya FFmpeg kurulumu icin yardimci olacak CMD penceresini acar."""
        msg = (
            "echo =================================================== & "
            "echo FFMPEG INSTALLATION GUIDE & "
            "echo =================================================== & "
            "echo. & "
            "echo To install FFmpeg, copy the following command, paste it here, and press ENTER: & "
            "echo. & "
            "echo winget install Gyan.FFmpeg & "
            "echo. & "
            "echo You can close this CMD window after the installation is complete."
        )
        os.system(f'start cmd.exe /k "{msg}"')

    def setup_dnd(self):
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<DropEnter>>', self._on_drag_enter)
        self.root.dnd_bind('<<DropLeave>>', self._on_drag_leave)
        self.root.dnd_bind('<<Drop>>', self.handle_drop)
        
        self.overlay.drop_target_register(DND_FILES)
        self.overlay.dnd_bind('<<DropEnter>>', self._on_drag_enter)
        self.overlay.dnd_bind('<<DropLeave>>', self._on_drag_leave)
        self.overlay.dnd_bind('<<Drop>>', self.handle_drop)

    def _on_drag_enter(self, event):
        """Dosya pencerenin ustune geldiginde: zamanlayiciyi iptal et, overlay'i goster."""
        if self._hide_timer is not None:
            self.root.after_cancel(self._hide_timer)
            self._hide_timer = None
        if not self.is_processing and not self._overlay_visible:
            self._overlay_visible = True
            self.overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

    def _on_drag_leave(self, event):
        """Dosya pencereden ciktiginda: 100ms bekle, tekrar girmezse overlay'i kapat."""
        if self._hide_timer is not None:
            self.root.after_cancel(self._hide_timer)
        self._hide_timer = self.root.after(100, self._do_hide_overlay)

    def _do_hide_overlay(self):
        """Gercekten overlay'i gizle (debounce sonrasi)."""
        self._overlay_visible = False
        self._hide_timer = None
        self.overlay.place_forget()

    def handle_drop(self, event):
        if self._hide_timer is not None:
            self.root.after_cancel(self._hide_timer)
            self._hide_timer = None
        self._overlay_visible = False
        self.overlay.place_forget()
        
        if self.is_processing:
            messagebox.showwarning("Busy", "A process is already running. Please wait for it to finish.")
            return
        
        paths = self.root.tk.splitlist(event.data)
        
        videos_to_process = []
        for p in paths:
            if os.path.isdir(p):
                videos_to_process.extend(glob.glob(os.path.join(p, "*.mp4")))
            elif p.lower().endswith(".mp4"):
                videos_to_process.append(p)
                
        self._start_processing(videos_to_process)

    def browse_files(self):
        """Dosya secme penceresiyle MP4 dosyalari sec."""
        if self.is_processing:
            messagebox.showwarning("Busy", "Zaten bir işlem devam ediyor.")
            return
        files = filedialog.askopenfilenames(
            title="Select Video Files to Split",
            filetypes=[("MP4 Videos", "*.mp4"), ("All Files", "*.*")]
        )
        if files:
            self._start_processing(list(files))

    def browse_folder(self):
        """Klasor secme penceresiyle bir klasordeki tum MP4'leri sec."""
        if self.is_processing:
            messagebox.showwarning("Busy", "Zaten bir işlem devam ediyor.")
            return
        folder = filedialog.askdirectory(title="Select Folder Containing Videos")
        if folder:
            videos = glob.glob(os.path.join(folder, "*.mp4"))
            self._start_processing(videos)

    def _start_processing(self, videos_to_process):
        """Ortak islemi baslatan fonksiyon (surukle-birak ve butonlar icin)."""
        if not videos_to_process:
            messagebox.showwarning("Warning", "No valid MP4 file found!")
            return
            
        self._reset_ui()
            
        # Beklenen soru sayisini al
        expected_q = None
        q_text = self.entry_q_count.get().strip()
        if q_text.isdigit():
            expected_q = int(q_text)
            
        base_dir = os.path.dirname(videos_to_process[0])
        output_dir = os.path.join(base_dir, "Split_Videos")
        
        self.stat_video_count.set(str(len(videos_to_process)))
        
        if expected_q:
            self.stat_question_count.set(f"0 / {expected_q}")
            self._update_info("parca_sayisi", f"0 / {expected_q}")
        else:
            self.stat_question_count.set("0")
            self._update_info("parca_sayisi", "0")
            
        self.stat_status.set("Starting...")
        self.live_dot.configure(fg=COLORS["success"])
        self._blink_active = True
        self._blink_dot()
        
        threading.Thread(target=self.run_process, args=(videos_to_process, output_dir, expected_q), daemon=True).start()

    def open_folder(self, path):
        try:
            os.startfile(path)
        except Exception as e:
            print(f"Could not open folder: {e}")

    def _blink_dot(self):
        if not self._blink_active:
            return
        current = self.live_dot.cget("fg")
        next_color = COLORS["text_muted"] if current == COLORS["success"] else COLORS["success"]
        self.live_dot.configure(fg=next_color)
        self.root.after(500, self._blink_dot)

    def _format_time(self, seconds):
        """Saniyeyi okunaklı formata cevir."""
        if seconds < 60:
            return f"{int(seconds)} sec"
        elif seconds < 3600:
            m, s = divmod(int(seconds), 60)
            return f"{m} min {s} sec"
        else:
            h, rem = divmod(int(seconds), 3600)
            m, s = divmod(rem, 60)
            return f"{h} hr {m} dk"

    def _format_size(self, bytes_size):
        """Byte'i okunaklı formata cevir."""
        if bytes_size < 1024**2:
            return f"{bytes_size / 1024:.1f} KB"
        elif bytes_size < 1024**3:
            return f"{bytes_size / (1024**2):.1f} MB"
        else:
            return f"{bytes_size / (1024**3):.2f} GB"

    def _get_video_meta(self, video_path):
        """FFprobe ile video suresini ve cozunurlugunu ogren."""
        duration = 0.0
        width, height = 0, 0
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,duration",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1", video_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for line in result.stdout.strip().split("\n"):
                if line.startswith("width="):
                    width = int(line.split("=")[1])
                elif line.startswith("height="):
                    height = int(line.split("=")[1])
                elif line.startswith("duration="):
                    try:
                        duration = float(line.split("=")[1])
                    except ValueError:
                        pass
        except Exception:
            pass
        return duration, width, height

    def _update_info(self, key, value):
        """Bilgi panelindeki bir alani guncelle."""
        if key in self.info_vars:
            self.info_vars[key].set(value)

    def run_process(self, videos, output_dir, expected_q=None):
        self.is_processing = True
        try:
            self._run_process_inner(videos, output_dir, expected_q)
        except Exception as e:
            print(f"\n  [CRITICAL ERROR] An error occurred during processing: {e}")
            self.stat_status.set("❌ Error")
        finally:
            self.is_processing = False
            self.live_dot.configure(fg=COLORS["text_muted"])
            self._blink_active = False
            
    def _run_process_inner(self, videos, output_dir, expected_q=None):
        total_questions = 0
        process_start = time.time()
        
        # Toplam video suresini onceden hesapla (tahmini sure icin)
        total_duration = 0.0
        for v in videos:
            d, _, _ = self._get_video_meta(v)
            total_duration += d
        
        self._update_info("video_adi", f"{len(videos)} files")
        self._update_info("video_suresi", self._format_time(total_duration))
        
        # Toplam dosya boyutu
        total_size = sum(os.path.getsize(v) for v in videos)
        self._update_info("dosya_boyutu", self._format_size(total_size))
        
        print("\n")
        print("  ┌─────────────────────────────────────────┐")
        print(f"  │  🚀 PROCESS STARTED                    │")
        print(f"  │  {len(videos)} video ({self._format_time(total_duration)})          │")
        print("  └─────────────────────────────────────────┘")
        print()
        
        processed_duration = 0.0
        
        for idx, v in enumerate(videos, 1):
            v_name = os.path.splitext(os.path.basename(v))[0]
            out_sub = os.path.join(output_dir, v_name)
            os.makedirs(out_sub, exist_ok=True)
            
            # Video bilgilerini panele yaz
            vid_dur, vid_w, vid_h = self._get_video_meta(v)
            vid_size = os.path.getsize(v)
            
            self._update_info("video_adi", v_name[:25])
            self._update_info("video_suresi", self._format_time(vid_dur))
            self._update_info("cozunurluk", f"{vid_w}x{vid_h}" if vid_w else "—")
            self._update_info("dosya_boyutu", self._format_size(vid_size))
            
            self.stat_status.set(f"Scanning {idx}/{len(videos)}")
            
            print(f"\n▸ [{idx}/{len(videos)}] {v_name}")
            if expected_q:
                print(f"  ⏳ Step 1/2 — Scanning for transitions (Expected: {expected_q} parça)...")
            else:
                print(f"  ⏳ Step 1/2 — Scanning for transitions (Auto-detect)...")
            
            video_start = time.time()
            
            if expected_q:
                cut_points, realistic_q = scan_and_build(v, expected_q)
                
                # Uyumsuzluk kontrolu
                if realistic_q != expected_q:
                    print(f"  [WARNING] {expected_q} parts requested but {realistic_q} realistic transitions detected.")
                    msg = (
                        f"You expected {expected_q} parts for '{v_name}', but the AI detected {realistic_q} realistic transition effects (parts).\n\n"
                        f"How would you like to proceed?\n\n"
                        f"Note: If the difference is very small (e.g., 1-2), it's likely a minor skipped effect. "
                        f"You can choose 'Force Split by My Count' to proceed with your number."
                    )
                    ans = self._ask_user_action_sync("Part Count Mismatch", msg)
                    
                    if ans == "skip":
                        print(f"  [CANCELLED] Video skipped by user.")
                        continue
                    elif ans == "ai":
                        print(f"  [AI] Rescanning based on AI count: {realistic_q} parts...")
                        self.stat_status.set(f"Rescanning {idx}/{len(videos)}")
                        cut_points = scan_and_build(v)
                        expected_q = realistic_q  # UI'daki hedef sayiyi guncelle
                    elif ans == "force":
                        print(f"  [FORCE] Video forcibly split into {expected_q} parts.")
                        # mevcut cut_points oldugu gibi kalir
            else:
                cut_points = scan_and_build(v)
            
            if not cut_points or len(cut_points) <= 1:
                print("  No transitions found, skipping.")
                processed_duration += vid_dur
                continue
                
            q_count = len(cut_points)
            total_questions += q_count
            
            if expected_q:
                self.stat_question_count.set(f"{total_questions} / {expected_q}")
                self._update_info("parca_sayisi", f"{total_questions} / {expected_q}")
            else:
                self.stat_question_count.set(str(total_questions))
                self._update_info("parca_sayisi", str(total_questions))
                
            self.stat_status.set(f"Cutting {idx}/{len(videos)}")
            print(f"  ⏳ Step 2/2 — {q_count} parts detected, splitting...")
            
            for i, (start_time, end_time) in enumerate(cut_points):
                q_dur = end_time - start_time
                q_num_str = f"{i+1:02d}_parca"
                out_file = os.path.join(out_sub, f"{q_num_str}.mp4")
                cut_video_segment(v, out_file, start_time, end_time)
                
            print(f"  ✓ {v_name} completed.")
            

            
            # Sure hesaplamalari
            video_elapsed = time.time() - video_start
            processed_duration += vid_dur
            total_elapsed = time.time() - process_start
            
            self._update_info("gecen_sure", self._format_time(total_elapsed))
            
            # Islem hizi: 1 min video = kac saniye islem
            if processed_duration > 0:
                speed_ratio = total_elapsed / processed_duration
                self._update_info("islem_hizi", f"1 min video = {speed_ratio * 60:.0f} sec")
                
                remaining_dur = total_duration - processed_duration
                est_remaining = remaining_dur * speed_ratio
                self._update_info("tahmini_kalan", f"~{self._format_time(est_remaining)}")
                print(f"  ⏱️ This video: {self._format_time(video_elapsed)} | Estimated remaining: ~{self._format_time(est_remaining)}")
            print()
            
        self.stat_status.set("✅ Completed")
        
        total_elapsed = time.time() - process_start
        self._update_info("gecen_sure", self._format_time(total_elapsed))
        self._update_info("tahmini_kalan", "Done!")
        self._update_info("video_adi", "✅ Completed")
        
        print()
        print("  ┌─────────────────────────────────────────┐")
        print(f"  │  ✅ ALL PROCESSES COMPLETED!            │")
        print(f"  │  {len(videos)} videos → {total_questions} parts           │")
        print(f"  │  Total time: {self._format_time(total_elapsed)}               │")
        print("  └─────────────────────────────────────────┘")
        
        messagebox.showinfo("Completed", f"{len(videos)} videos successfully split!\nTotal {total_questions} parts cut.\nTime: {self._format_time(total_elapsed)}")
        self.open_folder(output_dir)

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = SmartVideoSplitterApp(root)
    root.mainloop()
