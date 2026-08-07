<div align="center">
  
# ✂️ SVS | Smart Video Splitter

**Put an End to the "Manual Splitting" Drudgery That Steals Editors' Hours!** 🚀

[![Version](https://img.shields.io/badge/Version-v2.0_Pro-ff0055.svg)](#)
[![FFmpeg](https://img.shields.io/badge/Powered_by-FFmpeg-00f0ff.svg)](#)
[![Algorithm](https://img.shields.io/badge/Algorithm-Smart_Detection-00ff99.svg)](#)

</div>

---

## 😲 The Technology That Saves Editors

How many hours a day do you spend in Premiere Pro or DaVinci Resolve, searching for black screens (Fade to Black) in videos and cutting them one by one with the `C` (Razor) tool?

Educational videos, interviews, podcasts, or feature-length shoots... We know all too well the cold sweat you feel when the director says *"Save all the black transitions in between as separate mp4s"*.

**Smart Video Splitter (SVS) is designed exactly for this.**

While you sip your coffee; SVS's intelligent algorithm scans your video down to its pixels, detects **real** scene transitions and fade effects, and splits your video into parts in seconds **"Without Quality Loss"**.

---

## 🔥 Why Should You Use It? (The Editor's Savior)

* ⏱️ **Up to 10x Time Savings:** Reduces hours of manual cutting (Razor Blade spam) to mere minutes.
* 🤖 **Algorithmic Precision:** It doesn't just look for "black" screens; it understands the dynamics of scene transitions (Threshold and Noise detection). It doesn't forgive even the slightest transitions that might escape your eye.
* 💎 **Zero Quality Loss (Lossless):** It never re-renders the videos! Using FFmpeg Stream Copy technology, it cuts razor-sharp at lightning speed without ever degrading the quality.
* 🔄 **Timestamp Protection:** The "video freezes at the beginning but audio plays" (negative timestamp) vulnerabilities, which are common in automatic cutting programs, are completely prevented by SVS's custom algorithm (`-avoid_negative_ts`).
* 📂 **Automatic Naming & Organization:** It organizes the parts it cuts into folders as `01_part.mp4`, `02_part.mp4`. All you have to do is take these files and drop them into your editing Timeline!
* 🎨 **Dark / Studio UI:** It provides a professional feel with its eye-friendly, drag-and-drop supported, modern studio-themed interface that adapts to your editing workflow.

---

## 🚀 How to Use It? (Extremely Simple!)

1. **Drag Your Video:** Drag and drop your video (or a bunch of videos) into the program.
2. **Enter the Part Count (Optional):** If you know how many parts will come out of the video (for example, how many question solutions there are), write it down; let the algorithm focus on the most precise points. If you don't know, leave the field blank and the algorithm will handle it.
3. **Press "Start Processing":** And sit back.

SVS will slice the videos like a razor in seconds and deliver them to you.

---

## 🛠️ Installation (For Developers & Editors)

There is a massive technology behind the program. If you want to run it on your own system:

```bash
# 1. Clone the repo to your computer
git clone https://github.com/ibrahimilhan/SmartVideoSplitter.git

# 2. Enter the folder
cd SmartVideoSplitter

# 3. Install the required libraries
pip install -r requirements.txt

# 4. Start the Application!
python gui_app.py
```
*(Note: To be able to cut at flying speeds in the background, [FFmpeg](https://ffmpeg.org/) must be installed on your computer and added to the System Path.)*

---

## 💡 Footnote
This legendary tool is dedicated to all creative editors who try to catch up with edits until morning, with bloodshot eyes, saying *"let this render finish so I can sleep"*. ❤️

Stay with the edit, use technology to your advantage!
