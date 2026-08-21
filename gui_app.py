import os
import sys
import threading
import glob
import time
import subprocess
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, font as tkfont
from tkinterdnd2 import TkinterDnD, DND_FILES

# Modulleri ice aktaralim
from src.scanner import scan_and_build
from src.cutter import cut_video_segment


# Windows'ta yardimci islemler konsol penceresi acmasin.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


def cpu_cores():
    """
    Gercekten kullanilabilir cekirdek sayisi.
    os.cpu_count() afinite maskesini ve konteyner sinirlarini gormez; daha
    dogru olan varsa onu tercih et. Thread ust siniri buradan turetiliyor.
    """
    try:
        if hasattr(os, "process_cpu_count"):          # Python 3.13+
            n = os.process_cpu_count()
            if n:
                return n
        if hasattr(os, "sched_getaffinity"):          # Linux
            n = len(os.sched_getaffinity(0))
            if n:
                return n
    except Exception:
        pass
    return cpu_cores()

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
    def __init__(self, text_widget, root):
        self.text_widget = text_widget
        self.root = root
        self.buffer = []
        self.update_pending = False

    def write(self, string):
        self.buffer.append(string)
        if not self.update_pending:
            self.update_pending = True
            self.root.after(50, self._flush_buffer)

    def _flush_buffer(self):
        if not self.buffer:
            self.update_pending = False
            return

        data = "".join(self.buffer)
        self.buffer.clear()

        try:
            self.text_widget.configure(state="normal")
            self.text_widget.insert(tk.END, data)
            self.text_widget.see(tk.END)
            self.text_widget.configure(state="disabled")
        except tk.TclError:
            # Pencere kapaniyorsa widget yok olmus olabilir; kapanista
            # Tcl hatasi basmak yerine sessizce vazgec.
            pass

        self.update_pending = False

    def flush(self):
        pass



def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb):
    return '#%02x%02x%02x' % rgb

def fade_color(c1_hex, c2_hex, ratio):
    c1 = hex_to_rgb(c1_hex)
    c2 = hex_to_rgb(c2_hex)
    r = int(c1[0] * (1 - ratio) + c2[0] * ratio)
    g = int(c1[1] * (1 - ratio) + c2[1] * ratio)
    b = int(c1[2] * (1 - ratio) + c2[2] * ratio)
    return rgb_to_hex((r, g, b))

class CyberButton(tk.Canvas):
    def __init__(self, master, text, command, bg_color, hover_color, font, width=180, height=36, **kwargs):
        super().__init__(master, width=width, height=height, bg=COLORS["bg_dark"], highlightthickness=0, **kwargs)
        self.command = command
        self.text = text
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.font = font
        
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
        self.bind("<ButtonRelease-1>", self.on_release)
        
        self.draw_button(self.bg_color)
        
    def draw_button(self, color, is_pressed=False):
        self.delete("all")
        # -1: kenarlik tam pikselde kalsin, aksi halde sag/alt kenar
        # tuvalin disina tasip kirpiliyor.
        w, h = int(self['width']) - 1, int(self['height']) - 1
        cut = 8
        # Chamfered polygon points (top-left chamfered, bottom-right chamfered)
        points = [
            cut, 0,
            w, 0,
            w, h - cut,
            w - cut, h,
            0, h,
            0, cut
        ]
        outline_color = COLORS["accent"] if color == self.hover_color else "#314559"
        fill_color = COLORS["bg_card_alt"] if is_pressed else color
        
        self.create_polygon(points, fill=fill_color, outline=outline_color, width=1)
        
        # Inner glow line simulation (top edge) removed based on user request
        pass
        
        y_offset = 1 if is_pressed else 0
        self.create_text(w/2, h/2 + y_offset, text=self.text, font=self.font, fill="white")
        
    def on_enter(self, e):
        self.config(cursor="hand2")
        self.draw_button(self.hover_color)
        
    def on_leave(self, e):
        self.draw_button(self.bg_color)
        
    def on_click(self, e):
        self.draw_button(self.bg_color, is_pressed=True)
        
    def on_release(self, e):
        self.draw_button(self.hover_color)
        if self.command:
            self.command()

class GradientDivider(tk.Canvas):
    """
    Soldan saga parlayip sonen ayrac.
    fill=X ile paketlendiginde pencere genisligine uyar — sabit genislikte
    cizilirse genis ekranda ortada kesik gorunur.
    """
    def __init__(self, master, width=600, height=2, color=COLORS["accent"], bg_color=COLORS["bg_dark"], **kwargs):
        super().__init__(master, width=width, height=height, bg=bg_color, highlightthickness=0, **kwargs)
        self._color = color
        self._bg = bg_color
        self._h = height
        self.draw_gradient(width, height, color, bg_color)
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        self.delete("all")
        self.draw_gradient(event.width, self._h, self._color, self._bg)

    def draw_gradient(self, width, height, color, bg_color):
        segments = 60
        seg_w = width / (segments * 2)
        for i in range(segments):
            ratio = i / segments
            c = fade_color(bg_color, color, ratio)
            self.create_rectangle(i * seg_w, 0, (i + 1) * seg_w, height, fill=c, outline="")
        for i in range(segments):
            ratio = 1.0 - (i / segments)
            c = fade_color(bg_color, color, ratio)
            x1 = (segments + i) * seg_w
            self.create_rectangle(x1, 0, x1 + seg_w, height, fill=c, outline="")


class CyberCheck(tk.Canvas):
    """
    Temaya uyan onay kutusu. Varsayilan tk.Checkbutton Windows'un kendi
    gri kutusunu ciziyor ve siber paletin yaninda yamali duruyordu.

    tk.Checkbutton ile ayni sozlesme: BooleanVar + command, ve
    set_enabled() ile aktif/pasif.
    """
    def __init__(self, master, text, variable, command=None, accent=None,
                 font=None, bg=None, disabled_command=None, **kwargs):
        self.accent = accent or COLORS["accent2"]
        self.bg_color = bg or COLORS["bg_dark"]
        self.font = font or ("Segoe UI", 10, "bold")
        self.var = variable
        self.command = command
        # Pasifken tiklanirsa sessiz kalmak yerine sebebini anlat.
        self.disabled_command = disabled_command
        self.text = text
        self.enabled = True
        self._hover = False

        super().__init__(master, width=self._needed_width(text), height=26,
                         bg=self.bg_color, highlightthickness=0, **kwargs)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self._draw()

    def _draw(self):
        self.delete("all")
        on = bool(self.var.get())
        if not self.enabled:
            box_line, txt = COLORS["text_muted"], COLORS["text_muted"]
        elif on:
            box_line, txt = self.accent, COLORS["text_primary"]
        else:
            box_line = self.accent if self._hover else "#314559"
            txt = COLORS["text_secondary"]

        # Pah kirilmis kutu — CyberButton ile ayni dil
        x0, y0, s, cut = 2, 6, 14, 4
        self.create_polygon(
            [x0 + cut, y0, x0 + s, y0, x0 + s, y0 + s - cut,
             x0 + s - cut, y0 + s, x0, y0 + s, x0, y0 + cut],
            fill=COLORS["bg_card"] if not on else self.accent,
            outline=box_line, width=1)

        if on:
            self.create_line(x0 + 3, y0 + 7, x0 + 6, y0 + 10, fill="white", width=2)
            self.create_line(x0 + 6, y0 + 10, x0 + 11, y0 + 4, fill="white", width=2)

        self.create_text(x0 + s + 8, 13, text=self.text, font=self.font,
                         fill=txt, anchor="w")

    def _on_enter(self, e):
        if self.enabled:
            self._hover = True
            self.config(cursor="hand2")
            self._draw()

    def _on_leave(self, e):
        self._hover = False
        self._draw()

    def _on_click(self, e):
        if not self.enabled:
            if self.disabled_command:
                self.disabled_command()
            return
        self.var.set(not self.var.get())
        self._draw()
        if self.command:
            self.command()

    def _needed_width(self, text):
        return 26 + tkfont.Font(font=self.font).measure(text)

    def set_enabled(self, flag):
        self.enabled = bool(flag)
        self.config(cursor="hand2" if flag else "")
        self._draw()

    def set_text(self, text):
        """Donanim tespiti sonucuna gore etiket degisebilir."""
        self.text = text
        self.config(width=self._needed_width(text))
        self._draw()

    def refresh(self):
        self._draw()


class CyberCard(tk.Canvas):
    def __init__(self, master, bg_color, glow_color, **kwargs):
        super().__init__(master, bg=COLORS["bg_dark"], highlightthickness=0, **kwargs)
        self.bg_color = bg_color
        self.glow_color = glow_color
        self.bind("<Configure>", self.on_resize)
        
    def on_resize(self, event):
        self.delete("all")
        w, h = event.width - 1, event.height - 1
        cut = 16
        # Outer glow layer
        points_glow = [
            cut, 0,
            w, 0,
            w, h - cut,
            w - cut, h,
            0, h,
            0, cut
        ]
        self.create_polygon(points_glow, fill=self.glow_color, outline="")
        
        # Inner card layer
        points = [
            cut, 2,
            w-2, 2,
            w-2, h - cut,
            w - cut, h-2,
            2, h-2,
            2, cut
        ]
        self.create_polygon(points, fill=self.bg_color, outline="#314559", width=1)
        
        # Top edge inner glow removed based on user request
        pass

class SmartVideoSplitterApp:
    
    def _check_dependencies(self):
        """Uygulama baslarken FFmpeg ve FFprobe'un yuklu olup olmadigini kontrol eder."""
        try:
            __import__('subprocess').run(["ffmpeg", "-version"], stdout=__import__('subprocess').DEVNULL, stderr=__import__('subprocess').DEVNULL, creationflags=__import__('subprocess').CREATE_NO_WINDOW)
            __import__('subprocess').run(["ffprobe", "-version"], stdout=__import__('subprocess').DEVNULL, stderr=__import__('subprocess').DEVNULL, creationflags=__import__('subprocess').CREATE_NO_WINDOW)
        except Exception:
            __import__('tkinter').messagebox.showerror(
                "CRITICAL ERROR - FFmpeg Missing", 
                "FFmpeg is not installed or not added to your Windows PATH!\n\n"
                "Smart Video Splitter CANNOT function without FFmpeg.\n"
                "Please install FFmpeg, add it to system PATH, and restart the application."
            )
            # We don't exit here so they can at least see the UI, but it warns them.

    def __init__(self, root):
        self._check_dependencies()
        self.root = root
        self.root.title("SmartVideoSplitter")
        self.root.configure(bg=COLORS["bg_dark"])
        # Olculer setup_ui'dan SONRA _fit_window() ile hesaplanir — sabit sayi
        # yazmak yerine gercek gereksinimi olcuyoruz ki icerik degisince
        # panel kirpilmasin.
        
        # Icon olmasa bile taskbar'da guzel gorunsun
        self.root.option_add("*tearOff", False)
        
        self.is_processing = False
        self._overlay_visible = False
        self._hide_timer = None
        self._blink_active = False
        # Donanim analizi sonucu (None = henuz taraniyor)
        self._nvenc_ok = False
        self._nvenc_reason = None
        self._gpu_name = "unknown"
        self.cancel_event = __import__('threading').Event()
        self.setup_fonts()
        self.setup_ui()
        # Precise Cut varsayilan acik geldigi icin bagli widget'lari
        # (NVENC kutusu / thread girisi) baslangicta senkronla.
        self._toggle_precise()
        self._fit_window()
        self.setup_dnd()
        
        # Konsol yonlendirmesi
        sys.stdout = RedirectText(self.log_area, self.root)
        sys.stderr = RedirectText(self.log_area, self.root)

        # Donanim analizi arka planda — WMI sorgusu + NVENC deneme kodlamasi
        # birkac saniye surebilir, acilis bunu beklemesin.
        threading.Thread(target=self._probe_hardware, daemon=True).start()
        
    def _fit_window(self):
        """
        Pencere olcusunu icerigin GERCEK gereksinimine gore kurar.

        Sabit minsize yazmak kirilgandi: bir alan eklenince bilgi paneli
        sessizce kirpilmaya basliyordu. Burada Tk'nin kendi hesapladigi
        gerekli olcuyu okuyup minsize'i ona esitliyoruz — boylece hicbir
        panel kirpilamaz. Ekran kucukse ekrana sigacak sekilde sinirlanir.
        """
        self.root.update_idletasks()
        need_w = self.main_container.winfo_reqwidth()
        need_h = self.root.winfo_reqheight()

        scr_w = self.root.winfo_screenwidth()
        scr_h = self.root.winfo_screenheight()
        max_w, max_h = scr_w - 80, scr_h - 100

        self.root.minsize(min(need_w, max_w), min(need_h, max_h))

        # Acilis boyutu: gerekenden biraz genis, ama ekrani asmadan.
        open_w = min(max(need_w + 60, 1120), 1460, max_w)
        open_h = min(need_h + 60, max_h)
        x = max(0, (scr_w - open_w) // 2)
        y = max(0, (scr_h - open_h) // 3)
        self.root.geometry(f"{open_w}x{open_h}+{x}+{y}")

    def _ui(self, fn, *args, **kwargs):
        """
        KURAL 1 — Tkinter thread-safety.
        Arka plan thread'inden gelen HER arayuz guncellemesi buradan gecmeli.
        Isi ana thread'in olay kuyruguna atar; dogrudan cagri Python'u
        hicbir hata vermeden cokertir.
        Ana thread'den cagrilirsa da guvenlidir (after(0) sadece siraya alir).
        """
        try:
            self.root.after(0, lambda: fn(*args, **kwargs))
        except (tk.TclError, RuntimeError):
            # Pencere kapatilmis ya da ana dongu bitmis olabilir. Tkinter bu
            # durumda TclError degil RuntimeError("main thread is not in main
            # loop") atar; ikisi de yakalanmazsa arka plan thread'i sessizce
            # coker. Is burada sessizce sonlanmali.
            pass

    def _set_status(self, text):
        self._ui(self.stat_status.set, text)

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
        self.font_stat_text = ("Courier New", 20, "bold") # Metin degerler (Status)
        self.font_stat_label = ("Segoe UI", 8, "bold")

    def create_rounded_frame(self, parent, bg_color, pad=15):
        """Sahte Glow/Drop Shadow Efektli Kart"""
        # Dis katman (en koyu)
        outer1 = tk.Frame(parent, bg="#0d121c", padx=1, pady=1)
        # Orta katman (gecis)
        outer2 = tk.Frame(outer1, bg="#131b29", padx=1, pady=1)
        # Ic katman (siberpunk ince cizgi)
        outer3 = tk.Frame(outer2, bg="#1d2e40", padx=1, pady=1)
        
        inner = tk.Frame(outer3, bg=bg_color, padx=pad, pady=pad)
        inner.pack(fill=tk.BOTH, expand=True)
        outer3.pack(fill=tk.BOTH, expand=True)
        outer2.pack(fill=tk.BOTH, expand=True)
        return outer1, inner

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
                target_w, target_h = 2500, 112
                
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
        main_container = tk.Frame(self.root, bg=COLORS["bg_dark"], padx=44, pady=22)
        main_container.pack(fill=tk.BOTH, expand=True)
        # _fit_window() genisligi buradan olcer: banner 2500px genisliginde
        # oldugu icin root'un reqwidth'i gercek icerigi yansitmiyor.
        self.main_container = main_container
        
        # ===== HEADER BOLUMU (Yazi Tabanli Sik Tasarim) =====
        header = tk.Frame(main_container, bg=COLORS["bg_dark"])
        header.pack(fill=tk.X, pady=(0, 16))
        
        # Ust satir: baslik solda, versiyon rozeti sagda
        title_row = tk.Frame(header, bg=COLORS["bg_dark"])
        title_row.pack(fill=tk.X)

        title_frame = tk.Frame(title_row, bg=COLORS["bg_dark"])
        title_frame.pack(side=tk.LEFT, anchor="w")

        # Urun adi — banner logoyu, bu satir kimligi tasiyor
        name_row = tk.Frame(title_frame, bg=COLORS["bg_dark"])
        name_row.pack(anchor="w")
        tk.Label(name_row, text="SMART VIDEO", font=("Consolas", 20, "bold"),
                 fg=COLORS["text_primary"], bg=COLORS["bg_dark"]).pack(side=tk.LEFT)
        tk.Label(name_row, text="SPLITTER", font=("Consolas", 20, "bold"),
                 fg=COLORS["accent"], bg=COLORS["bg_dark"]).pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(title_frame, text="Automated Scene Splitting Algorithm",
                 font=("Cascadia Code", 10), fg=COLORS["text_muted"],
                 bg=COLORS["bg_dark"]).pack(anchor="w", pady=(2, 0))

        # Sag ust: versiyon rozeti + rehber butonu.
        # Rehber butonu eskiden kontrol satirindaydi, dar pencerede tasiyordu.
        right_head = tk.Frame(title_row, bg=COLORS["bg_dark"])
        right_head.pack(side=tk.RIGHT, anchor="ne")

        ver_frame = tk.Frame(right_head, bg=COLORS["bg_card"], padx=14, pady=6)
        ver_frame.pack(side=tk.RIGHT, padx=(12, 0))
        tk.Label(ver_frame, text="v2.0 Cyberpunk", font=("Consolas", 10, "bold"),
                 fg=COLORS["accent2"], bg=COLORS["bg_card"]).pack()

        CyberButton(right_head, text="[?] GUIDE", command=self._show_tutorial,
                    bg_color=COLORS["bg_card"], hover_color=COLORS["accent2"],
                    font=self.font_small, width=100, height=30).pack(side=tk.RIGHT)

        # Gradient ayrac — tum genisligi kaplar (GradientDivider kendini yeniden cizer)
        separator = GradientDivider(header, width=800, height=2,
                                    color=COLORS["accent"], bg_color=COLORS["bg_dark"])
        separator.pack(fill=tk.X, pady=(14, 0))

        # ===== UYARI KARTI =====
        warn_outer, warn_inner = self.create_rounded_frame(main_container, COLORS["bg_card"], pad=10)
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
            ("Transition Effect", "A 'Fade to Black' transition between parts is mandatory.", False),
            ("Precise Cut", "Leave it ON — otherwise each part starts with ~6s of the previous one.", False)
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
                CyberButton(row, text="How to Install?", command=self._show_ffmpeg_install, 
                            bg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], 
                            font=self.font_small, width=120, height=24).pack(side=tk.LEFT, padx=(10, 0))

        # ===== VIDEO SECME BUTONLARI =====
        # Iki satir: hepsi tek satirdayken dar pencerede "CPU Threads"
        # sagdan kirpiliyordu.
        ctrl_area = tk.Frame(main_container, bg=COLORS["bg_dark"])
        ctrl_area.pack(fill=tk.X, pady=(0, 12))

        btn_frame = tk.Frame(ctrl_area, bg=COLORS["bg_dark"])
        btn_frame.pack(fill=tk.X)

        opt_frame = tk.Frame(ctrl_area, bg=COLORS["bg_dark"])
        opt_frame.pack(fill=tk.X, pady=(10, 0))

        self.btn_file = CyberButton(btn_frame, text="🎬 SELECT VIDEO FILE", command=self.browse_files, 
                               bg_color=COLORS["accent2"], hover_color=COLORS["accent"], 
                               font=self.font_body_bold, width=200, height=38)
        self.btn_file.pack(side=tk.LEFT, padx=(0, 16))
        
        self.btn_folder = CyberButton(btn_frame, text="📁 SELECT FOLDER", command=self.browse_folder, 
                               bg_color=COLORS["accent2"], hover_color=COLORS["accent"], 
                               font=self.font_body_bold, width=180, height=38)
        self.btn_folder.pack(side=tk.LEFT, padx=(0, 16))
        
        self.btn_cancel = CyberButton(btn_frame, text="🛑 CANCEL", command=self._on_cancel_click, 
                               bg_color="#8B0000", hover_color="#FF0000", 
                               font=self.font_body_bold, width=140, height=38)
        
        
        self.btn_pause = CyberButton(btn_frame, text="⏸ PAUSE", command=self._on_pause_click, 
                               bg_color="#B8860B", hover_color="#DAA520", 
                               font=self.font_body_bold, width=140, height=38)
        
        
        self.is_paused = False
        self.pause_start_time = 0
        
        # Soru sayisi giris alani
        lbl_q = tk.Label(opt_frame, text="Expected Parts:", font=self.font_body_bold,
                         fg=COLORS["text_secondary"], bg=COLORS["bg_dark"])
        lbl_q.pack(side=tk.LEFT, padx=(0, 4))
        
        self.entry_q_count = tk.Entry(opt_frame, font=self.font_body, bg=COLORS["bg_card"],
                                      fg=COLORS["text_primary"], width=6, relief=tk.FLAT,
                                      insertbackground=COLORS["text_primary"])
        self.entry_q_count.pack(side=tk.LEFT, ipady=4, padx=(0, 8))
        
        tk.Label(opt_frame, text="(Optional)", font=self.font_small,
                 fg=COLORS["text_muted"], bg=COLORS["bg_dark"]).pack(side=tk.LEFT, padx=(0, 16))
                 
        # Varsayilan ACIK. Kapaliyken ffmpeg -c copy kullanir ve kesim en yakin
        # keyframe'e yuvarlanir (bu videolarda ~6 sn): her parcanin basina bir
        # onceki sorunun son saniyeleri + gecis efekti sizar. Olculdu:
        # fast +4.7..+5.5 sn sapma, precise +0.02 sn. Bkz. CLAUDE.md kural 12.
        self.var_precise = tk.BooleanVar(value=True)
        self.chk_precise = CyberCheck(
            opt_frame, text="Precise Cut", variable=self.var_precise,
            command=self._toggle_precise, accent=COLORS["accent"],
            font=self.font_body_bold
        )
        self.chk_precise.pack(side=tk.LEFT, padx=(0, 10))

        self.var_normalize = tk.BooleanVar(value=True)
        self.chk_normalize = CyberCheck(
            opt_frame, text="Normalize Audio", variable=self.var_normalize,
            accent=COLORS["accent"], font=self.font_body_bold
        )
        self.chk_normalize.pack(side=tk.LEFT, padx=(0, 10))

        self.var_gpu = tk.BooleanVar(value=False)
        self.chk_gpu = CyberCheck(
            opt_frame, text="NVIDIA NVENC (checking…)", variable=self.var_gpu,
            command=self._toggle_gpu, accent=COLORS["success"],
            font=self.font_body_bold, disabled_command=self._gpu_disabled_click
        )
        self.chk_gpu.set_enabled(False)
        self.chk_gpu.pack(side=tk.LEFT, padx=(0, 14))
        
        max_threads = cpu_cores()
        default_val = max_threads // 2 if max_threads >= 2 else 1

        self.var_speed = tk.StringVar(value=str(default_val))
        
        # Cyber-styled CPU Frame
        cpu_frame = tk.Frame(opt_frame, bg=COLORS["bg_card"], padx=8, pady=3)
        cpu_frame.pack(side=tk.LEFT, padx=(0, 0))
        
        tk.Label(cpu_frame, text="CPU Threads:", font=self.font_small,
                 fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(side=tk.LEFT, padx=(0, 6))
                 
        # Giris aninda dogrulama: cekirdek sayisinin ustu yazilamaz.
        vcmd = (self.root.register(self._validate_threads), "%P")
        self.entry_speed = tk.Entry(
            cpu_frame, textvariable=self.var_speed,
            width=3, font=self.font_body_bold, bg=COLORS["bg_dark"], fg=COLORS["accent"],
            relief=tk.FLAT, justify="center", insertbackground=COLORS["accent"],
            state="disabled", validate="key", validatecommand=vcmd
        )
        self.entry_speed.pack(side=tk.LEFT, ipady=2)
        self.entry_speed.bind("<FocusOut>", self._fix_threads)

        tk.Label(cpu_frame, text=f"/ {max_threads} Max", font=self.font_small,
                 fg=COLORS["success"], bg=COLORS["bg_card"]).pack(side=tk.LEFT, padx=(6, 0))

        # Tespit edilen donanim — arka plandaki tarama bunu doldurur.
        self.lbl_hw = tk.Label(opt_frame, text="analyzing hardware…",
                               font=self.font_small, fg=COLORS["text_muted"],
                               bg=COLORS["bg_dark"])
        self.lbl_hw.pack(side=tk.LEFT, padx=(14, 0))
                 

        # ===== ISTATISTIK KARTLARI =====
        stats_frame = tk.Frame(main_container, bg=COLORS["bg_dark"])
        stats_frame.pack(fill=tk.X, pady=(0, 12))
        
        self.stat_video_count = tk.StringVar(value="0")
        self.stat_question_count = tk.StringVar(value="0")
        self.stat_status = tk.StringVar(value="Waiting")
        
        stat_data = [
            (self.stat_video_count, "Video", COLORS["accent"], self.font_stat),
            (self.stat_question_count, "Part Detection", COLORS["success"], self.font_stat),
            # Durum sayi degil metin — 36pt'de tasiyordu, kendi olcusu var.
            (self.stat_status, "Status", COLORS["warning"], self.font_stat_text),
        ]

        for i, (var, label, color, vfont) in enumerate(stat_data):
            card = CyberCard(stats_frame, bg_color=COLORS["bg_card"], glow_color="#131b29", height=88)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0 if i == 0 else 8, 0 if i == len(stat_data)-1 else 8))
            
            # Place an inner frame in the center of the Canvas for the labels
            s_inner = tk.Frame(card, bg=COLORS["bg_card"])
            s_inner.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            
            tk.Label(s_inner, textvariable=var, font=vfont, fg=color,
                     bg=COLORS["bg_card"]).pack()
            tk.Label(s_inner, text=label.upper(), font=self.font_stat_label,
                     fg=COLORS["text_muted"], bg=COLORS["bg_card"]).pack(pady=(2, 0))

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
        
        # 4 satir x 2 sutun, her hucrede etiket ustte / deger altta.
        # Tek sutun 8 satir halindeyken panel dikeyde tasiyor, etiket ile
        # deger yan yanayken de uzun etiketler kirpiliyordu.
        grid = tk.Frame(info_inner, bg=COLORS["bg_card"])
        grid.pack(fill=tk.BOTH, expand=True)
        grid.columnconfigure(0, weight=1, uniform="info")
        grid.columnconfigure(1, weight=1, uniform="info")

        for idx, (key, label) in enumerate(info_fields):
            r, c = idx % 4, idx // 4
            cell = tk.Frame(grid, bg=COLORS["bg_card"])
            cell.grid(row=r, column=c, sticky="ew",
                      padx=(0, 14) if c == 0 else (14, 0), pady=(0, 9))

            tk.Label(cell, text=label, font=self.font_small, fg=COLORS["text_muted"],
                     bg=COLORS["bg_card"], anchor="w").pack(anchor="w")

            var = tk.StringVar(value="—")
            self.info_vars[key] = var
            tk.Label(cell, textvariable=var, font=self.font_body_bold,
                     fg=COLORS["text_primary"], bg=COLORS["bg_card"],
                     anchor="w").pack(anchor="w")

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
        
        # height=8: tk.Text varsayilani 24 satirdir ve pencerenin "gerekli
        # yukseklik" hesabini sisirir. Zaten fill=BOTH ile buyuyor.
        self.log_area = tk.Text(log_inner, bg=COLORS["log_bg"], fg=COLORS["log_fg"],
                                font=self.font_log, relief=tk.FLAT, borderwidth=0,
                                height=8,
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
            top.geometry("560x280")
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
                
            CyberButton(btn_frame, text="Force Split (My Count)", command=lambda: set_ans("force"), 
                        bg_color=COLORS["warning"], hover_color="#f2c130", 
                        font=self.font_body_bold, width=190, height=36).pack(side=tk.LEFT, padx=5)
                      
            CyberButton(btn_frame, text="Split by Detected Count", command=lambda: set_ans("ai"), 
                        bg_color=COLORS["success"], hover_color="#36cf8a", 
                        font=self.font_body_bold, width=190, height=36).pack(side=tk.LEFT, padx=5)
                      
            CyberButton(btn_frame, text="Skip Video", command=lambda: set_ans("skip"), 
                        bg_color=COLORS["bg_card_alt"], hover_color=COLORS["accent"], 
                        font=self.font_body_bold, width=120, height=36).pack(side=tk.LEFT, padx=5)
            
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
        if sys.platform != "win32":
            messagebox.showinfo(
                "Install FFmpeg",
                "Install FFmpeg with your package manager:\n\n"
                "  macOS          brew install ffmpeg\n"
                "  Debian/Ubuntu  sudo apt install ffmpeg\n"
                "  Fedora         sudo dnf install ffmpeg\n"
                "  Arch           sudo pacman -S ffmpeg")
            return

        # README'deki adimlarla ayni kalmali.
        msg = (
            "echo =================================================== & "
            "echo FFMPEG INSTALLATION & "
            "echo =================================================== & "
            "echo. & "
            "echo 1^) Copy the line below, paste it here, press ENTER: & "
            "echo. & "
            "echo      winget install Gyan.FFmpeg & "
            "echo. & "
            "echo 2^) IMPORTANT - when it finishes, CLOSE this window and & "
            "echo    RESTART SmartVideoSplitter. FFmpeg is only added to & "
            "echo    your PATH for newly opened programs. & "
            "echo. & "
            "echo 3^) To verify, open a NEW cmd and run:  ffmpeg -version"
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
                
            
        # UI kilitlenmesini onlemek icin event handler'dan ciktiktan sonra baslat
        self.root.after(50, lambda v=videos_to_process: self._start_processing(v))

    def _on_pause_click(self):
        if not self.is_processing:
            return
            
        import ctypes, subprocess
        ntdll = ctypes.WinDLL('ntdll')
        kernel32 = ctypes.WinDLL('kernel32')
        PROCESS_ALL_ACCESS = 0x1F0FFF
        my_pid = os.getpid()
        
        # O anki FFmpeg'leri bul
        try:
            out = subprocess.check_output('wmic process get ProcessId,ParentProcessId,Name', shell=True).decode(errors='ignore')
            target_pids = []
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[0].lower()
                    try:
                        ppid = int(parts[-2])
                        pid = int(parts[-1])
                        if (name == 'ffmpeg.exe' or name == 'ffprobe.exe') and ppid == my_pid:
                            target_pids.append(pid)
                    except:
                        pass
                        
            if not self.is_paused:
                # Pause
                self.is_paused = True
                self.pause_start_time = __import__('time').time()
                for pid in target_pids:
                    handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
                    if handle:
                        ntdll.NtSuspendProcess(handle)
                        kernel32.CloseHandle(handle)
                self.btn_pause.delete("all")
                self.btn_pause.text = "▶ RESUME"
                self.btn_pause.draw_button(self.btn_pause.bg_color)
                self._update_log("[SYSTEM] Processing PAUSED.", tag="warn")
            else:
                # Resume
                self.is_paused = False
                pause_duration = __import__('time').time() - self.pause_start_time
                if hasattr(self, 'start_time'): self.start_time += pause_duration
                if hasattr(self, '_last_update_time'): self._last_update_time += pause_duration
                
                for pid in target_pids:
                    handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
                    if handle:
                        ntdll.NtResumeProcess(handle)
                        kernel32.CloseHandle(handle)
                self.btn_pause.delete("all")
                self.btn_pause.text = "⏸ PAUSE"
                self.btn_pause.draw_button(self.btn_pause.bg_color)
                self._update_log("[SYSTEM] Processing RESUMED.", tag="success")
        except Exception as e:
            print("Pause error:", e)

    def _on_cancel_click(self):
        if not self.is_processing:
            __import__('tkinter').messagebox.showinfo("Bilgi", "Şu an devam eden bir işlem yok.")
            return
        if __import__('tkinter').messagebox.askyesno("İptal", "Devam eden işlemi durdurmak istiyor musunuz? (Bu biraz zaman alabilir)"):
            self.cancel_event.set()
            # We don't have text config exposed easily on CyberButton, so we just disable it visually
            # Instead of changing text, we just print to log
            self._update_log("[SYSTEM] Cancellation requested. Gracefully stopping FFmpeg...", tag="warn")

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

    def _toggle_precise(self):
        if self.var_precise.get():
            # Donanim analizi NVENC'i onaylamadiysa kutu acilmaz.
            self.chk_gpu.set_enabled(self._nvenc_ok)
            self.entry_speed.config(state="disabled" if self.var_gpu.get() else "normal")
        else:
            self.chk_gpu.set_enabled(False)
            self.entry_speed.config(state="disabled")

    def _toggle_gpu(self):
        self.entry_speed.config(state="disabled" if self.var_gpu.get() else "normal")
            
    # ------------------------------------------------------------------
    # DONANIM ANALIZI
    # ------------------------------------------------------------------
    def _ffmpeg_has_nvenc(self):
        """FFmpeg derlemesinde h264_nvenc var mi? (Kart olsa da olmayabilir.)"""
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 creationflags=_NO_WINDOW).stdout
            return b"h264_nvenc" in out
        except Exception:
            return False

    def _nvenc_smoke_test(self):
        """
        Tek kare deneme kodlamasi. Kart + ffmpeg destegi olsa bile surucu
        eski/mesgulse NVENC calismaz; tek guvenilir kontrol denemektir.
        """
        try:
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-v", "error", "-f", "lavfi",
                 "-i", "color=c=black:s=256x144:d=0.1", "-frames:v", "1",
                 "-c:v", "h264_nvenc", "-f", "null", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=25, creationflags=_NO_WINDOW)
            return r.returncode == 0
        except Exception:
            return False

    def _detect_gpu_name(self):
        """
        Ekran karti adi — YALNIZCA gosterim icin.
        NVENC'in kullanilabilirligine bu karar VERMEZ; ona _nvenc_smoke_test()
        karar verir. Isim bulunamamasi NVENC'i devre disi birakmamali.
        """
        # 1) nvidia-smi: platformdan bagimsiz, surucu varsa kesin sonuc
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=10, creationflags=_NO_WINDOW)
            if r.returncode == 0:
                lines = [l.strip() for l in
                         r.stdout.decode("utf-8", errors="ignore").splitlines() if l.strip()]
                if lines:
                    return lines[0]
        except Exception:
            pass

        # 2) Windows WMI — NVIDIA disi kartlarin adini da verir.
        #    KURAL 3/14: shell=True yok, text=True yok, ham byte + ignore.
        if sys.platform == "win32":
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-CimInstance Win32_VideoController | "
                     "Select-Object -ExpandProperty Name"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=20, creationflags=_NO_WINDOW)
                names = [l.strip() for l in
                         r.stdout.decode("utf-8", errors="ignore").splitlines() if l.strip()]
                if names:
                    nv = [n for n in names if "NVIDIA" in n.upper()]
                    return nv[0] if nv else names[0]
            except Exception:
                pass

        return "GPU not identified"

    def _probe_hardware(self):
        """
        Arka planda calisir (acilisi bloklamasin). Sonucu _ui ile arayuze
        yansitir — KURAL 1.

        NVENC karari DENEME KODLAMASINA dayanir, donanim sorgusuna degil.
        Eski surum once WMI'ye bakiyordu; WMI sorgusu Linux'ta, Windows 7'de
        (PowerShell 2.0'da Get-CimInstance yok) veya WMI servisi kapaliyken
        basarisiz olunca NVIDIA karti olan kullaniciya bile "NVENC yok"
        deniyordu. Simdi ground truth ffmpeg'in kendisi.
        """
        cores = cpu_cores()
        gpu_name = self._detect_gpu_name()

        if not self._ffmpeg_has_nvenc():
            ok, reason = False, ("Your FFmpeg build does not include the "
                                 "h264_nvenc encoder.\n\nInstall a full FFmpeg "
                                 "build that ships NVIDIA support.")
        elif not self._nvenc_smoke_test():
            if "NVIDIA" in gpu_name.upper():
                ok, reason = False, (f"{gpu_name} was found, but a test encode "
                                     "failed.\n\nUpdating your NVIDIA driver "
                                     "usually fixes this.")
            else:
                ok, reason = False, ("No usable NVIDIA encoder on this system."
                                     f"\n\nDetected graphics: {gpu_name}")
        else:
            ok, reason = True, ""

        self._ui(self._apply_hw_result, cores, ok, gpu_name, reason)

    def _apply_hw_result(self, cores, nvenc_ok, gpu_name, reason):
        """Ana thread: donanim sonucunu arayuze isle."""
        self._nvenc_ok = nvenc_ok
        self._nvenc_reason = reason
        self._gpu_name = gpu_name

        short = gpu_name if len(gpu_name) <= 26 else gpu_name[:24] + "…"
        self.lbl_hw.config(text=f"{cores} cores  ·  {short}")

        if nvenc_ok:
            self.chk_gpu.set_text("NVIDIA NVENC")
            # Precise kapaliyken zaten pasif kalmali
            self.chk_gpu.set_enabled(self.var_precise.get())
            print(f"[HARDWARE] {cores} CPU cores | {gpu_name} | NVENC ready.")
        else:
            self.var_gpu.set(False)
            self.chk_gpu.set_text("NVIDIA NVENC (unavailable)")
            self.chk_gpu.set_enabled(False)
            print(f"[HARDWARE] {cores} CPU cores | {gpu_name} | NVENC unavailable.")

    def _gpu_disabled_click(self):
        """
        NVENC kutusu pasifken tiklandi. KURAL 3 messagebox'i DnD/tarama
        sirasinda yasaklar; burasi kullanicinin kendi tiklamasi, guvenli.
        """
        if not self.var_precise.get():
            messagebox.showinfo(
                "NVIDIA NVENC",
                "Turn on 'Precise Cut' first — hardware encoding only "
                "applies when parts are re-encoded.")
            return
        if self._nvenc_reason is None:
            messagebox.showinfo("NVIDIA NVENC",
                                "Still checking your hardware, one moment…")
            return
        messagebox.showwarning("NVIDIA NVENC unavailable",
                               self._nvenc_reason + "\n\nCPU encoding will be used.")

    def _validate_threads(self, proposed):
        """
        Giris aninda dogrula: sadece rakam ve 1..cekirdek sayisi araligi.
        8 cekirdekli makinede 12 yazilamaz. Bos birakmaya izin var ki
        kullanici silip yeniden yazabilsin (FocusOut'ta toparlanir).
        """
        if proposed == "":
            return True
        if not proposed.isdigit():
            return False
        return 1 <= int(proposed) <= (cpu_cores())

    def _fix_threads(self, event=None):
        """Alan bos veya gecersiz kaldiysa varsayilana don (KURAL 4)."""
        max_t = cpu_cores()
        try:
            v = int(self.var_speed.get())
            if not 1 <= v <= max_t:
                raise ValueError
        except ValueError:
            self.var_speed.set(str(max(1, max_t // 2)))

    def _start_processing(self, videos_to_process):
        """Ortak islemi baslatan fonksiyon (surukle-birak ve butonlar icin)."""
            
        if not videos_to_process:
            messagebox.showwarning("Warning", "No valid MP4 file found!")
            return
            
        if self.var_precise.get():
            # NEVER USE MESSAGEBOX HERE — DnD sirasinda cagrilir, kilitlenir.
            # Donanim analizi acilista yapildi; burasi yalnizca son emniyet.
            if self.var_gpu.get():
                if self._nvenc_ok:
                    print(f"[HARDWARE] NVENC engaged on {self._gpu_name}.")
                else:
                    self.var_gpu.set(False)
                    self.chk_gpu.refresh()
                    print("[WARNING] NVENC unavailable — falling back to CPU.")

            if not self.var_gpu.get():
                # KURAL 4 — durdurma, donanim sinirina cek ve devam et.
                max_t = cpu_cores()
                try:
                    t_count = int(self.var_speed.get())
                except ValueError:
                    t_count = None
                if t_count is None:
                    self.var_speed.set(str(max(1, max_t // 2)))
                    print(f"[WARNING] Invalid thread count fixed to {max_t // 2}.")
                elif t_count > max_t:
                    self.var_speed.set(str(max_t))
                    print(f"[WARNING] Threads reduced to {max_t} (system has {max_t} cores).")
                elif t_count < 1:
                    self.var_speed.set("1")
                    print("[WARNING] Threads raised to 1.")

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
        
        is_precise = self.var_precise.get()
        speed_lvl = self.var_speed.get()
        is_gpu = self.var_gpu.get()
        norm_audio = self.var_normalize.get()
        threading.Thread(target=self.run_process, args=(videos_to_process, output_dir, expected_q, is_precise, speed_lvl, is_gpu, norm_audio), daemon=True).start()

    def open_folder(self, path):
        """Cikti klasorunu isletim sisteminin dosya yoneticisinde ac."""
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
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
            # KURAL 3/14 — text=True YOK: Turkce dosya adi stderr'e dusunce
            # locale cozumu UnicodeDecodeError ile programi cokertir.
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    creationflags=_NO_WINDOW)
            for line in result.stdout.decode("utf-8", errors="ignore").strip().split("\n"):
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
        """Bilgi panelindeki bir alani guncelle (thread-safe — KURAL 1)."""
        if key in self.info_vars:
            self._ui(self.info_vars[key].set, value)

    def run_process(self, videos, output_dir, expected_q=None, is_precise=False, speed_lvl="Balanced (Medium)", is_gpu=False, normalize_audio=False):
        self._ui(self.btn_file.pack_forget)
        self._ui(self.btn_folder.pack_forget)
        self._ui(self.btn_cancel.pack, side=__import__('tkinter').LEFT, padx=(0, 16))
        self._ui(self.btn_pause.pack, side=__import__('tkinter').LEFT, padx=(0, 16))
        
        self.is_processing = True
        try:
            self._run_process_inner(videos, output_dir, expected_q, is_precise, speed_lvl, is_gpu, normalize_audio)
        except Exception as e:
            # KURAL 6/7 — stdout ezili oldugu icin tam izi hem log'a hem diske yaz.
            err = traceback.format_exc()
            print(f"\n  [CRITICAL ERROR] An error occurred during processing: {e}")
            print(err)
            self._dump_crash(err)
            self._set_status("❌ Error")
        finally:
            self.is_processing = False
            self._ui(self.btn_cancel.pack_forget)
            self._ui(self.btn_pause.pack_forget)
            self._ui(self.btn_file.pack, side=__import__('tkinter').LEFT, padx=(0, 16))
            self._ui(self.btn_folder.pack, side=__import__('tkinter').LEFT, padx=(0, 16))
            if self.is_paused:
                self.is_paused = False
                self._ui(self.btn_pause.delete, "all")
                self.btn_pause.text = "⏸ PAUSE"
                self._ui(self.btn_pause.draw_button, self.btn_pause.bg_color)
            self._blink_active = False
            self._ui(self.live_dot.configure, fg=COLORS["text_muted"])

    def _dump_crash(self, text):
        """sys.stdout GUI'ye yonlendirildigi icin (KURAL 6) hatayi ayrica diske yaz."""
        try:
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "svs_error.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{text}\n")
        except Exception:
            pass
            
    def _run_process_inner(self, videos, output_dir, expected_q=None, is_precise=False, speed_lvl="Balanced (Medium)", is_gpu=False, normalize_audio=False):
        try:
            self._run_process_inner_impl(videos, output_dir, expected_q, is_precise, speed_lvl, is_gpu, normalize_audio)
        except Exception as e:
            print(f"[CRASH ERROR] {e}")
            self._set_status("❌ Error")
            self._ui(lambda err=e: __import__('tkinter').messagebox.showerror("Fatal Error", f"An unexpected error occurred:\n{err}"))
        finally:
            
            # Bilgisayari normal uyku moduna geri dondur
            try:
                __import__("ctypes").windll.kernel32.SetThreadExecutionState(0x80000000)
            except:
                pass

            # Hide pause/cancel and show select buttons
            try:
                self._ui(self.btn_cancel.pack_forget)
                self._ui(self.btn_pause.pack_forget)
                self._ui(self.btn_file.pack, side=__import__('tkinter').LEFT, padx=(0, 16))
                self._ui(self.btn_folder.pack, side=__import__('tkinter').LEFT, padx=(0, 16))
                
                # Reset pause button state if it was paused
                if self.is_paused:
                    self.is_paused = False
                    self._ui(self.btn_pause.delete, "all")
                    self.btn_pause.text = "⏸ PAUSE"
                    self._ui(self.btn_pause.draw_button, self.btn_pause.bg_color)
            except Exception as e:
                print(e)
            self._blink_active = False
            self._ui(self.live_dot.configure, fg="#444444") # COLORS["status_inactive"]

    def _run_process_inner_impl(self, videos, output_dir, expected_q=None, is_precise=False, speed_lvl="Balanced (Medium)", is_gpu=False, normalize_audio=False):
        total_questions = 0     # tespit edilen parca
        total_written = 0       # diske gercekten yazilan
        total_failed = 0        # ffmpeg'in kesemedigi
        process_start = time.time()
        
        # Toplam video suresini onceden hesapla (tahmini sure icin)
        total_duration = 0.0
        video_durations = {}
        for v in videos:
            d, _, _ = self._get_video_meta(v)
            total_duration += d
            video_durations[v] = d
        
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
            if self.cancel_event.is_set():
                print("  [CANCELLED] Process stopped safely by user.")
                break
            v_name = os.path.splitext(os.path.basename(v))[0]
            # Klasor isminden uzantiyi kaldir
            v_name_clean = os.path.splitext(v_name)[0]
            base_out_sub = os.path.join(output_dir, v_name_clean)
            
            # Ayni isimli baska video varsa uzerine yazmamak icin unique yap
            out_sub = base_out_sub
            counter = 1
            while os.path.exists(out_sub):
                out_sub = f"{base_out_sub} ({counter})"
                counter += 1
                
            os.makedirs(out_sub, exist_ok=True)
            
            # Video bilgilerini panele yaz
            if not __import__('os').path.exists(v):
                print(f"  [ERROR] File not found (deleted?): {v}")
                total_failed += 1
                total_duration -= video_durations.get(v, 0.0) # ETA'yi duzelt
                continue
            vid_dur, vid_w, vid_h = self._get_video_meta(v)
            vid_size = __import__('os').path.getsize(v)
            
            self._update_info("video_adi", v_name[:25])
            self._update_info("video_suresi", self._format_time(vid_dur))
            self._update_info("cozunurluk", f"{vid_w}x{vid_h}" if vid_w else "—")
            self._update_info("dosya_boyutu", self._format_size(vid_size))
            
            self._set_status(f"Scanning {idx}/{len(videos)}")

            print(f"\n▸ [{idx}/{len(videos)}] {v_name}")
            # KURAL 10 — hedef parca sayisi PER-VIDEO. Bu videodaki karar
            # sonraki videolari etkilememeli, o yuzden yerel kopya kullaniyoruz.
            target_q = expected_q
            if target_q:
                print(f"  ⏳ Step 1/2 — Scanning for transitions (Expected: {target_q} parça)...")
            else:
                print(f"  ⏳ Step 1/2 — Scanning for transitions (Auto-detect)...")

            video_start = time.time()

            if target_q:
                cut_points, realistic_q = scan_and_build(v, target_q, is_gpu, self.cancel_event)

                if self.cancel_event.is_set():
                    print("  [CANCELLED] Process stopped safely by user.")
                    break
                
                # Uyumsuzluk kontrolu
                if realistic_q != target_q:
                    print(f"  [WARNING] {target_q} parts requested but {realistic_q} realistic transitions detected.")
                    msg = (
                        f"You expected {target_q} parts for '{v_name}', but the algorithm detected {realistic_q} realistic transition effects (parts).\n\n"
                        f"How would you like to proceed?\n\n"
                        f"Note: If the difference is very small (e.g., 1-2), it's likely a minor skipped effect. "
                        f"You can choose 'Force Split by My Count' to proceed with your number."
                    )
                    ans = self._ask_user_action_sync("Part Count Mismatch", msg)

                    if ans == "skip":
                        print(f"  [CANCELLED] Video skipped by user.")
                        processed_duration += vid_dur
                        continue
                    elif ans == "ai":
                        print(f"  [AUTO] Rescanning based on detected count: {realistic_q} parts...")
                        self._set_status(f"Rescanning {idx}/{len(videos)}")
                        cut_points, _ = scan_and_build(v, is_gpu=is_gpu, cancel_event=self.cancel_event)
                        target_q = realistic_q  # sadece bu videonun hedefi degisir
                    elif ans == "force":
                        actual_parts = len(cut_points) if cut_points else 0
                        if actual_parts == target_q:
                            print(f"  [FORCE] Video forcibly split into {target_q} parts.")
                        else:
                            print(f"  [FORCE] Could not find {target_q} parts. Forced to closest possible match: {actual_parts} parts.")
                        target_q = actual_parts  # Update UI target to reflect reality
                        # mevcut cut_points oldugu gibi kalir
            else:
                cut_points, _ = scan_and_build(v, is_gpu=is_gpu, cancel_event=self.cancel_event)
            
            if not cut_points or len(cut_points) <= 1:
                print("  No transitions found, skipping.")
                processed_duration += vid_dur
                continue
                
            q_count = len(cut_points)
            total_questions += q_count
            
            if target_q:
                self._ui(self.stat_question_count.set, f"{total_questions} / {target_q}")
                self._update_info("parca_sayisi", f"{total_questions} / {target_q}")
            else:
                self._ui(self.stat_question_count.set, str(total_questions))
                self._update_info("parca_sayisi", str(total_questions))

            self._set_status(f"Cutting {idx}/{len(videos)}")
            print(f"  ⏳ Step 2/2 — {q_count} parts detected, splitting...")
            
            # Kesim sonucu MUTLAKA okunmali: eskiden donus degeri yok
            # sayiliyordu, bu yuzden her kesim basarisiz olsa bile arayuz
            # "✅ Completed / N parca" gosterip bos klasor birakiyordu.
            written = failed = 0
            for i, (start_time, end_time) in enumerate(cut_points):
                if self.cancel_event.is_set():
                    print(f"  [CANCELLED] Stopping before starting part {i+1}...")
                    break
                q_num_str = f"{i+1:02d}_parca"
                out_file = os.path.join(out_sub, f"{q_num_str}.mp4")
                self._set_status(f"Cutting Part {i+1}/{q_count}")
                if cut_video_segment(v, out_file, start_time, end_time,
                                     is_precise, speed_lvl, is_gpu, normalize_audio):
                    written += 1
                else:
                    failed += 1

            total_written += written
            total_failed += failed

            if failed:
                print(f"  ⚠ {v_name}: {written} part(s) written, {failed} FAILED.")
            else:
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
            
        # Durum gercegi yansitsin — hicbir sey yazilamadiysa bu bir basari degil.
        if total_failed and total_written:
            self._set_status("⚠ Partial")
        elif total_failed:
            self._set_status("❌ Failed")
        else:
            self._set_status("✅ Completed")

        total_elapsed = time.time() - process_start
        self._update_info("gecen_sure", self._format_time(total_elapsed))
        self._update_info("tahmini_kalan", "Done!")
        self._update_info("video_adi", "✅ Completed")
        
        print()
        print("  " + "─" * 44)
        if total_failed:
            print(f"  {'⚠ FINISHED WITH ERRORS' if total_written else '❌ NOTHING WAS WRITTEN'}")
            print(f"  {len(videos)} video(s) → {total_written} part(s) written, {total_failed} failed")
            print("  See the messages above for the FFmpeg error.")
        else:
            print("  ✅ ALL PROCESSES COMPLETED!")
            print(f"  {len(videos)} video(s) → {total_written} part(s)")
        print(f"  Total time: {self._format_time(total_elapsed)}")
        print("  " + "─" * 44)

        # KURAL 1 — messagebox ve os.startfile ana thread'den cagrilmali.
        if total_failed:
            title = "Finished with errors" if total_written else "Splitting failed"
            summary = (f"{total_written} part(s) written, {total_failed} could not be cut.\n\n"
                       f"FFmpeg rejected those segments — check the Process Log "
                       f"for the exact error.\n\nTime: {self._format_time(total_elapsed)}")
        else:
            title = "Completed"
            summary = (f"{len(videos)} video(s) successfully split!\n"
                       f"Total {total_written} parts cut.\n"
                       f"Time: {self._format_time(total_elapsed)}")
        self._ui(self._finish_dialog, title, summary, output_dir, total_written > 0)

    def _finish_dialog(self, title, summary, output_dir, ok):
        """Ana thread'de calisir (bkz. _run_process_inner sonu)."""
        if ok:
            messagebox.showinfo(title, summary)
            self.open_folder(output_dir)
        else:
            # Hicbir dosya yoksa bos klasoru acmanin anlami yok.
            messagebox.showerror(title, summary)


    def _show_tutorial(self):
        top = tk.Toplevel(self.root)
        top.title("SVS Architecture & Guide")
        # Icerik 6 bolum — 700x550'de metin sikisiyordu.
        top.geometry("820x680")
        top.minsize(680, 480)
        top.configure(bg=COLORS["bg_dark"])
        top.transient(self.root)

        header_frame = tk.Frame(top, bg=COLORS["bg_dark"])
        header_frame.pack(fill=tk.X, pady=(18, 8), padx=20)

        # font_title (26pt) bu genislikte tasiyordu.
        lbl_title = tk.Label(header_frame, text="ARCHITECTURE & GUIDE",
                             font=("Consolas", 15, "bold"),
                             fg=COLORS["accent"], bg=COLORS["bg_dark"])
        lbl_title.pack(side=tk.LEFT)
        
        frame = tk.Frame(top, bg=COLORS["bg_dark"])
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        text_area = tk.Text(frame, wrap=tk.WORD, font=self.font_body, bg=COLORS["bg_dark"], fg=COLORS["text_primary"],
                            relief=tk.FLAT, padx=15, pady=15, insertbackground=COLORS["text_primary"])
        text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text_area.yview, style="Cyber.Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_area.config(yscrollcommand=scrollbar.set)
        
        # NOT: Buradaki sayilar gercek bir olcumden gelir —
        # 73,6 dk / 1280x720 / 46 parca. Uydurma rakam yazma; degistirmen
        # gerekiyorsa once olc (bkz. CLAUDE.md kural 12).
        text_tr = """
[1] 🔍 NASIL ÇALIŞIR?
--------------------------------------------------
SVS videoyu 4 FPS'e düşürüp gri tonlamaya çevirir ve ardışık kareler arasındaki piksel farkını ölçer. Fade efektleri bu farkta belirgin bir zirve oluşturur. Bulunan noktalar 10 FPS ile yeniden taranarak tam sınır belirlenir.

Parça sınırları şöyle kurulur:
    parça başı = fade bitişi + 0,2 sn
    parça sonu = fade başlangıcı − 0,2 sn

Böylece çıktı dosyasında ne fade efekti ne de önceki parçadan artık kalır. Videonun kendi kapanış kararması da son parçadan kırpılır.

Tarama sırasında diske geçici dosya yazılmaz; FFmpeg çıktısı akış halinde okunur.

[2] 🎯 HASSAS KESİM (varsayılan AÇIK) vs ⚡ HIZLI MOD
--------------------------------------------------
Bir MP4 her kareyi tam olarak saklamaz. Yaklaşık 6 saniyede bir "tam kare" (keyframe) koyar, aradaki kareler için yalnızca değişim bilgisini tutar.

• HIZLI MOD (Precise Cut KAPALI)
  Yeniden kodlama yapmaz, veriyi kopyalar. Bu yüzden ancak bir tam kareden başlayabilir ve istenen noktadan geriye kayar.
  Ölçüm: her parçanın başına önceki parçadan 4,7–5,5 saniye sızdı. 46 parçanın kesimi 9 saniye sürdü.

• HASSAS KESİM (Precise Cut AÇIK) — VARSAYILAN
  Yeniden kodlar, bu yüzden tam istenen karede başlayabilir.
  Ölçüm: sapma 0,02 saniye. 46 parçanın kesimi 166 saniye sürdü.

Aynı videoda toplam süre: Hızlı 86 sn (kirli çıktı), Hassas 243 sn (temiz çıktı). Programın amacı elle kırpmayı ortadan kaldırmak olduğu için varsayılan Hassas Kesim'dir.

[3] 🖥️ NVIDIA NVENC (donanım kodlama)
--------------------------------------------------
Program açılışta donanımı arka planda analiz eder (~2 sn):
    1. FFmpeg derlemesinde h264_nvenc var mı?
    2. Tek kare deneme kodlaması gerçekten başarılı mı?

Karar bu denemeye göre verilir, kartın adına göre değil. Kutu kilitliyse üzerine tıklayın — sebebi size özel yazılır (kart yok / FFmpeg desteksiz / sürücü eski).

Dürüst not: Bu makinedeki ölçümde NVENC ile CPU başa baş çıktı (17,3 sn / 18,2 sn). Kısa kliplerde GPU'yu her seferinde başlatma maliyeti kazancı yiyor. NVENC bir seçenektir, sihirli bir hız düğmesi değil.

[4] ⚙️ İŞLEMCİ ÇEKİRDEKLERİ
--------------------------------------------------
Program çekirdek sayınızı tespit eder ve giriş alanı bu sınırı aşmanıza izin vermez — 8 çekirdekli bir makinede 12 yazılamaz.

Varsayılan, çekirdek sayısının yarısıdır. Tümünü vermek her zaman daha hızlı değildir: dizüstülerde ısınma nedeniyle frekans düşer ve kazanç geri alınabilir. Emin değilseniz varsayılanı bırakın.

[5] ✅ SONUÇ DURUMLARI
--------------------------------------------------
İşlem bitince Status kartı gerçeği gösterir:
    ✅ Completed — bütün parçalar diske yazıldı
    ⚠ Partial   — bir kısmı yazıldı, bir kısmını FFmpeg reddetti
    ❌ Failed    — hiçbir dosya yazılamadı (klasör açılmaz)

Hata durumunda FFmpeg'in gerçek mesajı Process Log'da görünür.

[6] 📋 GEREKSİNİMLER
--------------------------------------------------
• FFmpeg kurulu ve sistem PATH'inde olmalı
• Parçalar arasında 'Fade to Black' benzeri bir geçiş bulunmalı
"""
        text_en = """
[1] 🔍 HOW IT WORKS
--------------------------------------------------
SVS downscales the video to 4 FPS grayscale and measures the pixel difference between consecutive frames. Fade effects produce a clear spike. Each candidate point is then re-scanned at 10 FPS to pin down its exact boundary.

Part boundaries are built like this:
    part start = end of fade   + 0.2 s
    part end   = start of fade - 0.2 s

That is why the output file contains neither the fade nor any leftover from the previous part. The video's own closing fade is trimmed from the last part as well.

No temporary files are written to disk during scanning — FFmpeg output is read as a stream.

[2] 🎯 PRECISE CUT (ON by default) vs ⚡ FAST MODE
--------------------------------------------------
An MP4 does not store every frame in full. Roughly every 6 seconds it stores a complete picture (a keyframe); frames in between only record what changed.

• FAST MODE (Precise Cut OFF)
  No re-encoding — it copies the data. Therefore it can only start at a keyframe, landing earlier than requested.
  Measured: 4.7–5.5 s of the previous part leaked into the start of every part. Cutting 46 parts took 9 seconds.

• PRECISE CUT (Precise Cut ON) — DEFAULT
  Re-encodes, so it can start exactly on the requested frame.
  Measured: 0.02 s drift. Cutting 46 parts took 166 seconds.

Totals on the same video: Fast 86 s (dirty output), Precise 243 s (clean output). Since the whole point of the tool is to remove manual trimming, Precise Cut is the default.

[3] 🖥️ NVIDIA NVENC (hardware encoding)
--------------------------------------------------
On startup the app analyses your hardware in the background (~2 s):
    1. Does your FFmpeg build ship h264_nvenc?
    2. Does a single-frame test encode actually succeed?

The decision comes from that test encode, not from the GPU's name. If the checkbox is locked, click it — you will get the specific reason (no NVIDIA GPU / FFmpeg without support / outdated driver).

An honest note: on this machine NVENC and CPU came out even (17.3 s vs 18.2 s). For short clips the per-invocation GPU startup cost cancels the gain. NVENC is an option, not a magic speed button.

[4] ⚙️ CPU THREADS
--------------------------------------------------
The app detects your core count and the input field will not let you exceed it — you cannot type 12 on an 8-core machine.

The default is half your cores. Using all of them is not always faster: on laptops, thermal throttling can claw the gain back. When in doubt, leave the default.

[5] ✅ RESULT STATES
--------------------------------------------------
When processing ends, the Status card tells you the truth:
    ✅ Completed — every part was written to disk
    ⚠ Partial   — some were written, some were rejected by FFmpeg
    ❌ Failed    — nothing was written (the folder is not opened)

On failure, FFmpeg's actual error message appears in the Process Log.

[6] 📋 REQUIREMENTS
--------------------------------------------------
• FFmpeg installed and available on your system PATH
• A 'Fade to Black' style transition between parts
"""
        
        current_state = {"lang": "TR"}
        
        def update_text(content):
            text_area.config(state=tk.NORMAL)
            text_area.delete(1.0, tk.END)
            text_area.insert(tk.END, content.strip())
            text_area.config(state=tk.DISABLED)
            
        def toggle_lang():
            if current_state["lang"] == "TR":
                current_state["lang"] = "EN"
                btn_lang.config(text="TÜRKÇE")
                update_text(text_en)
            else:
                current_state["lang"] = "TR"
                btn_lang.config(text="ENGLISH")
                update_text(text_tr)
                
        btn_lang = tk.Button(header_frame, text="ENGLISH", font=self.font_body_bold, bg=COLORS["bg_card"], fg=COLORS["text_primary"], 
                             relief=tk.FLAT, command=toggle_lang, cursor="hand2")
        btn_lang.pack(side=tk.RIGHT)
        
        update_text(text_tr)
        
        CyberButton(top, text="CLOSE", command=top.destroy, 
                    bg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], 
                    font=self.font_body_bold, width=120, height=35).pack(pady=(10, 20))

if __name__ == "__main__":

    root = TkinterDnD.Tk()
    app = SmartVideoSplitterApp(root)
    root.mainloop()
