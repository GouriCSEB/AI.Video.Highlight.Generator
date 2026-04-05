<<<<<<< HEAD
# 🎬 HILIGHT — AI Video Highlight Generator

> Automatically generate short highlight videos from long lectures, tutorials,
> and webinars using Machine Learning and Computer Vision.

---

## 🏗️ Architecture

```
Browser (HTML/CSS/JS)
        ↕  REST API (JSON + multipart)
Flask Backend  (app.py)
        ↕
┌───────────────────────────────────────┐
│  Feature Extraction  (OpenCV)         │
│    → 12 visual features per frame     │
├───────────────────────────────────────┤
│  ML Scoring  (Random Forest)          │
│    → importance probability per frame │
├───────────────────────────────────────┤
│  Highlight Generation  (OpenCV)       │
│    → top-30 % frames stitched to MP4  │
└───────────────────────────────────────┘
```

---

## 📁 Project Structure

```
ai-video-highlight/
├── app.py                          # Flask REST API
├── requirements.txt
├── model/
│   ├── train_model.py              # ML training + evaluation
│   ├── model.pkl                   # saved Random Forest (auto-generated)
│   ├── scaler.pkl                  # feature scaler   (auto-generated)
│   └── metrics.json                # evaluation results (auto-generated)
├── video_processing/
│   ├── extract_frames.py           # feature extraction (12 features / frame)
│   └── highlight_generator.py      # segment selection + video stitching
├── templates/
│   └── index.html                  # single-page frontend
├── static/
│   ├── style.css                   # dark editorial design
│   └── script.js                   # Fetch API client
├── uploads/                        # uploaded videos (auto-created)
└── outputs/                        # generated highlights (auto-created)
=======
Got it — you want a clean **README.md style document** (like GitHub). Here’s a professional one you can directly copy 👇

---

# 🎬 AI Video Highlight Generator

## 📌 Overview

The **AI Video Highlight Generator** is an intelligent system that automatically extracts key moments from long videos and generates short, meaningful highlight clips. It leverages Artificial Intelligence techniques such as computer vision and audio analysis to identify important segments without manual effort.

---

## 🚀 Features

* 🎥 Automatic highlight detection
* 🧠 AI-based scene understanding
* 🔊 Audio intensity analysis
* ✂️ Video clipping & merging
* ⚡ Fast processing
* 📱 Simple user interface

---

## 🧠 How It Works

1. **Upload Video**

   * User provides a video file

2. **Preprocessing**

   * Extract frames using video processing
   * Extract audio track

3. **Analysis**

   * Detect scene changes (frame differences)
   * Identify high-motion segments
   * Analyze audio spikes (crowd noise, emphasis)

4. **Scoring System**

   * Assign importance score to each segment

5. **Highlight Extraction**

   * Select top-scoring segments

6. **Output**

   * Generate final highlight video

---

## 🛠️ Tech Stack

### 💻 Backend

* Python / Node.js
* OpenCV (frame processing)
* FFmpeg (video editing)

### 🧠 AI/ML

* TensorFlow / PyTorch
* Speech-to-Text APIs

### 🌐 Frontend

* HTML
* CSS
* JavaScript

---

## 📂 Project Structure

```
AI-Video-Highlight-Generator/
│
├── input_videos/
├── output_highlights/
├── models/
├── src/
│   ├── video_processing.py
│   ├── audio_analysis.py
│   ├── highlight_generator.py
│
├── app.js / app.py
├── requirements.txt
└── README.md
>>>>>>> ce9b07487297f9584f911943bfcc92ee72531f02
```

---

<<<<<<< HEAD
## ⚙️ Setup & Run

### 1 — Prerequisites

- Python 3.9 or newer
- pip
- (Optional) A virtual environment

### 2 — Install dependencies

```bash
# Create and activate a virtual environment (recommended)
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

> **Note:** OpenCV headless is used so no GUI libraries are needed.

### 3 — Train the model (first run only)

The ML model trains itself automatically on the first request, but you
can also train it manually:

```bash
cd model
python train_model.py
cd ..
```

This creates `model/model.pkl`, `model/scaler.pkl`, and `model/metrics.json`.

### 4 — Start the server

```bash
python app.py
```

Open your browser at **http://localhost:5000**

---

## 🔌 API Endpoints

| Method | Endpoint              | Description                            |
|--------|-----------------------|----------------------------------------|
| GET    | `/`                   | Serve the web UI                       |
| POST   | `/upload`             | Upload a video → returns `video_id`    |
| POST   | `/process/<video_id>` | Start ML processing pipeline           |
| GET    | `/status/<video_id>`  | Poll processing status + results       |
| GET    | `/highlight/<video_id>`| Stream highlight video                |
| GET    | `/download/<video_id>`| Download highlight video               |
| GET    | `/metrics`            | Model evaluation metrics               |

### Example: upload + process

```javascript
// 1. Upload
const form = new FormData();
form.append('video', file);
const { video_id } = await fetch('/upload', { method: 'POST', body: form }).then(r => r.json());

// 2. Start processing
await fetch(`/process/${video_id}`, { method: 'POST' });

// 3. Poll until done
const poll = setInterval(async () => {
  const status = await fetch(`/status/${video_id}`).then(r => r.json());
  if (status.status === 'done') {
    clearInterval(poll);
    // use status.timeline, status.segments, status.highlight_meta
  }
}, 1500);
```

---

## 🧠 Machine Learning Pipeline

### Feature Vector (12 features per frame)

| # | Feature              | Description                                  |
|---|----------------------|----------------------------------------------|
| 1 | `brightness`         | Mean pixel intensity of the frame            |
| 2 | `contrast`           | Std deviation of pixel intensity             |
| 3 | `edge_density`       | Fraction of edge pixels (Canny detector)     |
| 4 | `motion_score`       | Mean absolute difference vs previous frame   |
| 5 | `color_variance`     | Variance of HSV hue channel                  |
| 6 | `saturation_mean`    | Mean HSV saturation                          |
| 7 | `sharpness`          | Laplacian variance (focus measure)           |
| 8 | `face_like_regions`  | Skin-tone pixel fraction (YCrCb)             |
| 9 | `text_like_density`  | Adaptive threshold blob density              |
|10 | `scene_change`       | Histogram correlation drop vs prev frame     |
|11 | `temporal_position`  | Normalised position in video (0–1)           |
|12 | `activity_score`     | Composite of motion + edge density           |

### Model

- **Algorithm:** Random Forest Classifier (100 trees, max depth 10)
- **Class weighting:** balanced (handles imbalance automatically)
- **Preprocessing:** StandardScaler
- **Saved with:** Joblib

### Evaluation Metrics

After training, `model/metrics.json` contains:

```json
{
  "accuracy":  0.8950,
  "precision": 0.8812,
  "recall":    0.8763,
  "f1_score":  0.8787,
  "confusion_matrix": [[...], [...]],
  "feature_importances": { "edge_density": 0.142, ... }
}
```

All metrics are visible in the **Model Metrics** modal in the UI.

---

## 🎯 Highlight Selection Algorithm

1. Score every sampled frame with the Random Forest (probability of being important)
2. Select frames in the **top 30 %** by score
3. Merge nearby selected frames (gap < 2 s) into continuous segments
4. Pad each segment by ±1 second
5. Merge overlapping padded segments
6. Cap total highlight at **120 seconds**

---

## 🎨 Frontend Features

- **Drag-and-drop** video upload with XHR progress bar
- **Live pipeline visualisation** (extract → score → generate → done)
- **Importance timeline canvas** — bar chart of every scored frame
- **Segment list** with timestamps and duration bars
- **Model metrics modal** — accuracy / precision / recall / F1 + confusion
  matrix + feature importance chart
- **Inline video player** + download button
- Fully responsive dark theme (no external UI framework required)

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: cv2` | `pip install opencv-python-headless` |
| `No module named moviepy` | `pip install moviepy` |
| Video won't play in browser | Use MP4 with H.264 — most reliable format |
| Processing stuck at 70 % | Check `outputs/` is writable |
| Large video (> 500 MB) | Compress first or increase `MAX_CONTENT_LENGTH` in `app.py` |

---

## 🚀 Bonus Features (already included)

- [x] AI confidence score timeline
- [x] Segment timestamps with duration
- [x] Feature importance chart
- [x] Confusion matrix visualisation
- [x] MP4, AVI, MOV, MKV, WEBM support
- [x] Download button for highlight

---

## 📜 License

MIT — free for personal and commercial use.
=======
## ▶️ Installation & Setup

```bash
# Clone the repository
git clone https://github.com/your-username/ai-video-highlight-generator.git

# Navigate to project
cd ai-video-highlight-generator

# Install dependencies
pip install -r requirements.txt
```

---

## ▶️ Usage

```bash
# Run the application
python app.py
```

* Upload a video
* Wait for processing
* Download generated highlights

---

## 📊 Example

| Input Video Length | Output Highlight |
| ------------------ | ---------------- |
| 2 hours            | 5 minutes        |
| 30 minutes         | 3 minutes        |

---

## 📌 Applications

* 🎯 Sports highlights
* 📚 Lecture summarization
* 🎬 Content creation (YouTube, reels)
* 🔍 Surveillance analysis

---

## 🔮 Future Enhancements

* Emotion detection
* Real-time processing
* Custom highlight filters
* Multi-language support

---

## 🤝 Contributing

Contributions are welcome! Feel free to fork the repository and submit a pull request.

---


>>>>>>> ce9b07487297f9584f911943bfcc92ee72531f02
