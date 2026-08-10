# SmartVideoSplitter — Proje Kuralları

## 🎯 Asıl Amaç

Videoyu **fade-to-black geçişlerinden** güvenilir ve hızlı bölmek. Her karar bu amaca
hizmet etmeli. Arayüz, algoritmanın hizmetindedir — tersi değil.

**Tek giriş noktası: `gui_app.py`.** Başka bir şey çalıştırılmıyor.

## 🏗️ Mimari

```
gui_app.py  → Tkinter UI + iş akışı orkestrasyonu (worker thread)
src/scanner.py → geçiş tespiti (algoritmanın kalbi)
src/cutter.py  → ffmpeg ile kesim
```

Akış: kaba tarama (4 FPS gri, piksel farkı) → kümeleme → hassas tarama (10 FPS)
→ fade-in kırpma (30 FPS) → kısa parça birleştirme → kesim.

---

## 🚨 Saatli Bombalar — Bunlara Tekrar Basma

### 1. Tkinter Thread-Safety
Ağır işlemler (`run_process`) ayrı bir **Thread**'de çalışır. Arka plandaki bir
fonksiyondan **asla** doğrudan Tkinter elemanı güncellenemez (`Label`,
`StringVar.set()`, `.configure()`, `messagebox`). Güncellenirse Python **hiçbir hata
vermeden anında çöker.**

Tüm arayüz güncellemeleri `self._ui(...)` helper'ı üzerinden gitmeli
(bu `self.root.after(0, ...)`'a sarar).

> `print()` güvenlidir — `RedirectText` sınıfı zaten `after` ile koruma altına alır.

### 2. TkinterDnD Drag & Drop Kilitlenmesi
`<<Drop>>` event'i bitmeden ekrana `messagebox` açılırsa Windows'ta arayüz kilitlenir.
Bu yüzden `handle_drop` işi `self.root.after(50, ...)` ile geciktirir.
**Bu yapıyı asla bozma.**

### 3. NVIDIA / PowerShell Donanım Taraması
`subprocess.check_output` içinde **asla `text=True` kullanma.** Türkçe Windows'ta
`UnicodeDecodeError` ile program çöker. Daima ham byte al,
`.decode('utf-8', errors='ignore')` ile çöz.
Tarama başarısız olursa `messagebox` gösterme — sessizce **CPU moduna fallback** yap.

### 3b. Donanım Analizi Açılışta, Arka Planda
`_probe_hardware()` açılışta bir daemon thread'de çalışır (WMI sorgusu + NVENC
deneme kodlaması ~2,5 sn sürer, açılış bunu beklememeli). Sonucu `_ui()` ile
arayüze yansıtır.

**Karar deneme kodlamasına dayanır, donanım sorgusuna değil:**
1. `_ffmpeg_has_nvenc()` — ffmpeg derlemesinde `h264_nvenc` var mı
2. `_nvenc_smoke_test()` — tek kare NVENC kodlaması gerçekten başarılı mı

`_detect_gpu_name()` **yalnızca gösterim** içindir; NVENC kararına karışmaz.
Bu sıralamayı ters çevirme. Eski sürüm önce WMI'ye bakıyordu ve sorgu
Linux'ta, Windows 7'de (PowerShell 2.0'da `Get-CimInstance` yok) veya WMI
servisi kapalıyken başarısız olunca **NVIDIA kartı olan kullanıcıya bile
"NVENC yok"** diyordu. Ground truth ffmpeg'in kendisidir.

`_detect_gpu_name()` sırası: `nvidia-smi` (platformdan bağımsız) → Windows WMI
→ `"GPU not identified"`. İsim bulunamaması NVENC'i devre dışı bırakmamalı.

Kontroller düşerse kutu pasif kalır, etiketi `(unavailable)` olur, `var_gpu`
zorla `False` yapılır. Kullanıcı pasif kutuya tıklarsa `_gpu_disabled_click()`
**sebebe özel** mesaj gösterir. Bu bir KURAL 3 ihlali değildir: yasak olan
DnD/tarama sırasında messagebox açmaktır; burası kullanıcının kendi tıklaması.

`_start_processing` içindeki kontrol artık önbelleğe alınmış `_nvenc_ok`'u okur —
her çalıştırmada PowerShell sorgusu tekrarlanmaz. Orası yalnızca son emniyet,
**oraya messagebox koyma.**

### 4. Auto-Correct Yaklaşımı
Kullanıcı geçersiz thread sayısı girerse hata fırlatıp durma. Değeri donanım limitine
(`os.cpu_count()`) otomatik çek, uyarıyı log'a yaz, **işleme devam et.**

Buna ek olarak thread girişi artık **yazma anında** doğrulanır
(`_validate_threads`, Tk `validate="key"`): 8 çekirdekli makinede 12 yazılamaz.
Boş bırakmaya izin verilir (kullanıcı silip yeniden yazabilsin), `<FocusOut>`
ile `_fix_threads()` toparlar. `_start_processing`'deki clamp yine de durur —
iki katman birden, çünkü giriş doğrulaması programatik atamaları yakalamaz.

### 5. İki Dil Desteği (EN/TR)
Yeni arayüz metni eklerken TR ve EN karşılıklarını ilgili sözlüğe **mutlaka** ekle.

---

### 6. `sys.stdout` Ezilmiştir
`gui_app.py` başlangıçta `sys.stdout`/`sys.stderr`'i `RedirectText`'e yönlendirir.
GUI kurulmadan veya çöktükten sonra oluşan hata **hiçbir yere yazılmaz.**
Kritik hataları ayrıca dosyaya yaz; debug ederken sadece `print`'e güvenme.

### 7. Exception Handler Kendisi Patlamamalı
`except` bloğunda kullanılan her modülün import edildiğini doğrula.
(Geçmişte `traceback.format_exc()` çağrılıyordu ama `import traceback` yoktu →
her gerçek hata `NameError` ile maskeleniyordu.)

### 8. Geçici `.gray` Dosyaları
Tarama, ffmpeg çıktısını **pipe** ile akış halinde okur — diske yazmaz.
Diske yazan bir yol eklersen:
- **mutlaka `try/finally`** ile sil (happy-path `os.remove` yetmez),
- dosya adında `threading.get_ident()` kullanma — thread ID'leri yeniden kullanılır,
- tek bir uzun videonun ham gri hali **1 GB+** olabilir; RAM'e komple yükleme.

### 9. `scan_and_build` Her Zaman Tuple Döner
Sözleşme: `scan_and_build(...)` → **`(questions, realistic_q_count)`**, her koşulda.
`coarse_scan` da öyle. `expected_q_count` verilse de verilmese de değişmez.

Eskiden `expected_q_count` verilince tuple, verilmeyince düz `list` dönüyordu —
çağıran yer yanlış açarsa `cut_points` tuple olur ve döngü saçmalardı.
**Bu sözleşmeyi koşula bağlı hale getirme.** Kullanım: `cut_points, _ = scan_and_build(v)`

### 10. Döngü Değişkenlerini Ezme
Çoklu video işlerken `expected_q` gibi değerler döngü içinde **ezilmemeli** —
bir videodaki karar sonraki videoları etkilememeli. Per-video yerel değişken kullan.

### 11. Ölü Kodu "Tamir Etmeye" Çalışma
`main.py` ve `gui_app_backup.py` çalışmıyor ve **çalışması gerekmiyor.**
`main.py`, var olmayan `src.gallery_maker`, `scan_black_screens`,
`generate_cut_points`'i import eder. Bunları görüp eksik fonksiyon yazma.

### 12. Precise Cut VARSAYILAN AÇIK — Kapatma
Hedef: **çıktı mp4'ünde sadece istenen soru olacak** — ne fade efekti, ne önceki
parçadan artık.

`-c copy` (Fast mode) kesimi en yakın keyframe'e yuvarlamak *zorundadır*; ara
kareler tek başına çözülemez. Gerçek videoda ölçüldü (keyframe aralığı ~6 sn):

| | süre sapması | sonuç |
|---|---|---|
| Fast (`-c copy`) | **+4,7 … +5,5 sn** | her parça önceki sorunun son ~5 sn'siyle başlıyor |
| Precise (re-encode) | **+0,02 sn** | tam istenen yerden başlıyor |

Precise maliyeti: 73 dk'lık video / 46 parça için ~166 sn. Kabul edilebilir.
`var_precise` varsayılanı `True`; değiştirme.

NVENC ölçüldü ve CPU ile **başa baş** (17,3 vs 18,2 sn) — kısa kliplerde GPU
başlatma maliyeti kazancı yiyor. Opsiyonel kalsın, otomatik açma.

### 12b. Parça Sınırlarının Mantığı
```
parça başı = fade bitişi + SAFETY_MARGIN      (refine_transitions'tan)
parça sonu = fade başlangıcı − SAFETY_MARGIN
```
Bu yüzden 1..N-1 parçaları doğası gereği temizdir. **Son parçanın sonu** ise
videonun kendi sonudur ve kapanış fade'ini içerebilir — `trim_final_fadeout()`
tam olarak bu boşluğu kapatır. Silme.

### 12c. `cut_video_segment()` Dönüş Değeri MUTLAKA Okunur
Fonksiyon başarısızlıkta `False` döner. Bu değer bir dönem yok sayılıyordu ve
sonuç şuydu: **her kesim başarısız olsa bile** arayüz "✅ Completed / N parça"
gösterip boş klasör açıyordu (ölçüldü: 2 parça bildirildi, 0 dosya yazıldı).

`_run_process_inner` artık `total_written` / `total_failed` sayar ve durumu
buna göre verir:

| Sonuç | Status | Diyalog | Klasör açılır mı |
|---|---|---|---|
| Hepsi yazıldı | `✅ Completed` | info | evet |
| Bir kısmı düştü | `⚠ Partial` | info "Finished with errors" | evet |
| Hiçbiri yazılmadı | `❌ Failed` | **error** "Splitting failed" | hayır |

Yeni bir kesim yolu eklersen aynı sayımı yap. Sessiz başarı, sessiz çökmeden
beterdir — kullanıcı hatayı aylar sonra fark eder.

### 13. Çıktı Dosyası Varsa Atlanır
`cutter.py` çıktı zaten varsa sessizce `True` döner. Ayar değiştirilip tekrar
çalıştırılırsa eski dosya kalır. Bilinçli bir tercih — değiştirmeden önce sor.

### 14. Türkçe Karakterli Yollar Her Yerde
Kullanıcının dosyaları `C:/Users/İlhan/Desktop/AYT 2018 ... Çıkmış Sorular.mp4` gibi.
Kural 3 sadece PowerShell için değil, **her `subprocess` çağrısı** için geçerli:
- `shell=True` kullanma (yollarda boşluk/özel karakter var)
- argümanları liste olarak ver
- ffmpeg çağrılarında byte olarak oku, decode ederken `errors='ignore'`

### 15. Algoritma Eşikleri Deneyle Bulundu — Rastgele Oynama
`0.5` / `1.0` (piksel fark eşiği), `3s` (kümeleme), `15s` (kısa parça),
`0.2` (`SAFETY_MARGIN`), `4`/`10`/`30` FPS.
Bunlar gerçek videolarla ayarlanmış değerlerdir. Değiştirirsen **gerçek videoyla
test edilmeli** — "iyileştirme" görüntüsü veren kör değişiklik yapma.

---

### 16. Platforma Bağımlı Çağrılar `sys.platform` ile Ayrılır
Proje GitHub'da açık kaynak — Windows dışında da çalıştırılabilir. Yeni bir
sistem çağrısı eklerken:

| İş | Doğru yol |
|---|---|
| Klasör açma | `os.startfile` (win) / `open` (mac) / `xdg-open` (linux) |
| Çekirdek sayısı | `cpu_cores()` — `os.cpu_count()` afinite/konteyner sınırını görmez |
| GPU adı | `nvidia-smi` önce, WMI yalnızca `sys.platform == "win32"` içinde |
| FFmpeg kurulumu | winget yalnızca Windows'ta; diğerlerinde paket yöneticisi metni |

`subprocess` çağrılarında `creationflags=_NO_WINDOW` unutma (Windows'ta konsol
çakması), ve **asla `shell=True`** (KURAL 14 — yollarda boşluk/Türkçe karakter).

> Not: Bu çapraz platform yolları **yalnızca simülasyonla** doğrulandı; gerçek
> Linux/macOS üzerinde test edilmedi.

## 🧹 Repo Hijyeni

- `__pycache__` ve `*.gray` **asla** commit edilmez
- `requirements.txt` gerçekten import edilenle eşleşmeli
- Test/çöp dosyaları (`dummy.mp4`, `debug_svs.txt`) repoda bırakılmaz
