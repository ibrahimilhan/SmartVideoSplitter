<div align="center">
  
# ✂️ SVS | Smart Video Splitter (AI-Powered)

**Kurgucuların (Editörlerin) Saatlerini Çalan "Manuel Kesim" Angaryasına Son!** 🚀

[![Version](https://img.shields.io/badge/Versiyon-v2.0_Pro-ff0055.svg)](#)
[![FFmpeg](https://img.shields.io/badge/Powered_by-FFmpeg-00f0ff.svg)](#)
[![AI](https://img.shields.io/badge/AI-Smart_Detection-00ff99.svg)](#)

</div>

---

## 😲 Kurgucuları Kurtaran O Teknoloji

Günde kaç saatinizi Premiere Pro veya DaVinci Resolve başında, videolardaki siyah ekranları (Fade to Black) arayıp `C` (Razor) tuşuyla tek tek kesmekle harcıyorsunuz? 

Eğitim videoları, röportajlar, podcastler veya uzun metrajlı çekimler... Yönetmen size *"Aralardaki siyah geçişlerden hepsini ayrı mp4 olarak kaydet"* dediğinde hissettiğiniz o soğuk teri çok iyi biliyoruz. 

**İşte Smart Video Splitter (SVS) tam olarak bunun için tasarlandı.**

Siz kahvenizi yudumlarken; SVS'nin yapay zekası videonuzu piksellerine kadar tarar, **gerçek** sahne geçişlerini ve kararma efektlerini tespit eder ve videonuzu saniyeler içinde **"Kalite Kaybı Yaşamadan (Lossless)"** parçalara ayırır.

---

## 🔥 Neden Kullanmalısın? (Editörün Kurtarıcısı)

* ⏱️ **10 Kata Kadar Zaman Tasarrufu:** Saatler süren manuel kesim (Razor Blade spam) işlemini dakikalara indirir.
* 🤖 **Yapay Zeka Destekli Hassasiyet:** Sadece "siyah" ekranları değil, sahne geçişlerinin dinamiğini anlar (Threshold ve Noise tespiti). Gözünüzden kaçan ufak geçişleri bile affetmez.
* 💎 **Sıfır Kalite Kaybı (Lossless):** Videoları bir daha renderlamaz! FFmpeg Stream Copy teknolojisiyle kaliteyi asla bozmadan, mili-saniyeler içinde şimşek hızında jilet gibi keser.
* 🔄 **Zaman Çizelgesi (Timestamp) Koruması:** Otomatik kesim programlarında hep yaşanan "videonun başı dondu ama ses geliyor" (negative timestamp) zafiyetleri SVS'nin özel algoritmasıyla (`-avoid_negative_ts`) tamamen engellenmiştir.
* 📂 **Otomatik İsimlendirme & Düzenleme:** Kestiği onca parçayı klasörleyip `01_parca.mp4`, `02_parca.mp4` şeklinde düzenler. Size sadece bu dosyaları alıp kurguya (Timeline'a) atmak kalır!
* 🎨 **Karanlık / Stüdyo Arayüzü:** Göz yormayan, sürükle-bırak destekli, modern ve profesyonel stüdyo temalı arayüzü ile kurgu sürecinize uyum sağlar.

---

## 🚀 Nasıl Kullanılır? (Çok Basit!)

1. **Videonu Sürükle:** Videonu (veya bir sürü videoyu) programın içine sürükleyip bırak.
2. **Parça Sayısını Gir (Opsiyonel):** Eğer videonun içinden kaç parça çıkacağını (örneğin kaç soru çözümü olduğunu) biliyorsan yaz; yapay zeka en kesin noktalara odaklansın. Eğer bilmiyorsan, alanı boş bırak yapay zeka halletsin.
3. **"İşlemi Başlat"a Bas:** Ve arkana yaslan. 

SVS, videoları saniyeler içinde jilet gibi doğrayıp sana teslim edecek.

---

## 🛠️ Kurulum (Geliştiriciler & Kurgucular İçin)

Programın arkasında devasa bir teknoloji yatıyor. Kendi sisteminizde çalıştırmak isterseniz:

```bash
# 1. Repoyu bilgisayarınıza klonlayın
git clone https://github.com/KULLANICI_ADINIZ/SmartVideoSplitter.git

# 2. Klasöre girin
cd SmartVideoSplitter

# 3. Gerekli kütüphaneleri yükleyin
pip install -r requirements.txt

# 4. Uygulamayı Başlatın!
python gui_app.py
```
*(Not: Arka planda uçan hızda kesim yapabilmesi için bilgisayarınızda [FFmpeg](https://ffmpeg.org/) kurulu ve Sistem Yolu'na (PATH) eklenmiş olmalıdır.)*

---

## 💡 Dipnot
Bu efsane araç; sabahlara kadar kurgu yetiştirmeye çalışan, gözleri kanlanmış, *"şu render bitsin de uyuyayım"* diyen tüm yaratıcı kurguculara armağan edilmiştir. ❤️ 

Kurguyla kalın, teknolojiyi kendi lehinize kullanın!
