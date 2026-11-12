/* Real-time webcam facial mood detection powered by @vladmandic/face-api */

import { apiRequest, getLocalDateStr, getTimeOfDay, showToast } from "./api.js";

const MODEL_URI = "/static/models";
const EXPR_KEYS = ["happy", "neutral", "sad", "angry", "fearful", "surprised", "disgusted"];

function mapExpressionToMood(expr) {
  if (!expr) return { mood: "calm", raw: "neutral", score: 74, confidence: 0.7 };
  const entries = EXPR_KEYS.map((k) => [k, Number(expr[k] || 0)]).sort((a, b) => b[1] - a[1]);
  const [topKey, topProb] = entries[0];

  const happy = Number(expr.happy || 0);
  const neutral = Number(expr.neutral || 0);
  const sad = Number(expr.sad || 0);
  const angry = Number(expr.angry || 0);
  const fearful = Number(expr.fearful || 0);
  const disgusted = Number(expr.disgusted || 0);
  const surprised = Number(expr.surprised || 0);

  let mood = "calm";
  if (topKey === "happy") mood = "happy";
  else if (topKey === "neutral") mood = "calm";
  else if (topKey === "sad") mood = "sad";
  else if (topKey === "fearful") mood = "anxious";
  else if (topKey === "angry" || topKey === "disgusted") mood = "stressed";
  else if (topKey === "surprised") mood = "surprised";

  const rawScore =
    happy * 94 +
    neutral * 78 +
    surprised * 66 +
    sad * 34 +
    fearful * 36 +
    angry * 32 +
    disgusted * 38;

  const weightSum = happy + neutral + surprised + sad + fearful + angry + disgusted || 1;
  const score = Math.max(15, Math.min(98, Math.round(rawScore / weightSum)));

  return {
    mood,
    raw: topKey,
    score,
    confidence: Math.min(1, Math.max(0.1, topProb)),
  };
}

export class FaceMoodScanner {
  constructor({ onMoodUpdate, onScanSaved }) {
    this.onMoodUpdate = onMoodUpdate;
    this.onScanSaved = onScanSaved;
    this.modelsLoaded = false;
    this.stream = null;
    this.running = false;
    this.loopTimer = null;
    this.smoothed = {};
    this.latestResult = {
      mood: "calm",
      raw: "neutral",
      score: 76,
      confidence: 0.85,
      expressions: { happy: 0.15, neutral: 0.75, sad: 0.03, angry: 0.02, fearful: 0.02, surprised: 0.03 },
    };
    this.showLandmarks = true;
    this.autoScanCountdown = 0;
    this.autoScanTimer = null;
    this.autoSamples = [];
  }

  async ensureModels() {
    if (this.modelsLoaded) return;
    if (!window.faceapi) {
      throw new Error("Facial analysis script did not load.");
    }
    await Promise.all([
      window.faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URI),
      window.faceapi.nets.faceExpressionNet.loadFromUri(MODEL_URI),
      window.faceapi.nets.faceLandmark68TinyNet.loadFromUri(MODEL_URI),
    ]);
    this.modelsLoaded = true;
  }

  async startCamera(videoEl, canvasEl, statusEl) {
    if (this.running) return;
    statusEl.textContent = "Loading local facial expression model...";
    await this.ensureModels();

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("Camera access is not supported in this browser context.");
    }

    statusEl.textContent = "Requesting camera permission...";
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });

    videoEl.srcObject = this.stream;
    await videoEl.play();
    this.running = true;
    statusEl.textContent = "Scanning expressions locally — nothing leaves your device.";
    this.runDetectionLoop(videoEl, canvasEl, statusEl);
  }

  stopCamera(videoEl, canvasEl, statusEl) {
    this.running = false;
    clearTimeout(this.loopTimer);
    this.cancelAutoScan();
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    if (videoEl) videoEl.srcObject = null;
    if (canvasEl) {
      const ctx = canvasEl.getContext("2d");
      ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
    }
    if (statusEl) {
      statusEl.textContent = "Camera paused. Turn on anytime or log your mood manually.";
    }
  }

  async runDetectionLoop(videoEl, canvasEl, statusEl) {
    if (!this.running) return;

    try {
      if (videoEl.readyState >= 2) {
        const displaySize = {
          width: videoEl.videoWidth || 640,
          height: videoEl.videoHeight || 480,
        };
        if (canvasEl.width !== displaySize.width || canvasEl.height !== displaySize.height) {
          canvasEl.width = displaySize.width;
          canvasEl.height = displaySize.height;
        }

        const options = new window.faceapi.TinyFaceDetectorOptions({
          inputSize: 224,
          scoreThreshold: 0.45,
        });

        const detection = await window.faceapi
          .detectSingleFace(videoEl, options)
          .withFaceLandmarks(true)
          .withFaceExpressions();

        const ctx = canvasEl.getContext("2d");
        ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);

        if (detection) {
          if (this.showLandmarks && detection.landmarks) {
            ctx.fillStyle = "rgba(107, 142, 120, 0.72)";
            for (const pt of detection.landmarks.positions) {
              ctx.beginPath();
              ctx.arc(pt.x, pt.y, 1.8, 0, Math.PI * 2);
              ctx.fill();
            }
          }

          // Smooth probabilities with exponential moving average
          const rawExpr = detection.expressions || {};
          for (const key of EXPR_KEYS) {
            const val = Number(rawExpr[key] || 0);
            this.smoothed[key] =
              this.smoothed[key] === undefined ? val : this.smoothed[key] * 0.65 + val * 0.35;
          }

          const mapped = mapExpressionToMood(this.smoothed);
          this.latestResult = {
            ...mapped,
            expressions: { ...this.smoothed },
          };

          if (this.autoScanCountdown > 0) {
            this.autoSamples.push(this.latestResult);
          }

          statusEl.textContent = `Detected: ${mapped.mood} (${Math.round(mapped.confidence * 100)}% confidence)`;
          this.onMoodUpdate(this.latestResult, true);
        } else {
          statusEl.textContent = "Center your face gently in soft light...";
        }
      }
    } catch {
      // Keep loop resilient across transient frame errors
    }

    if (this.running) {
      this.loopTimer = setTimeout(() => this.runDetectionLoop(videoEl, canvasEl, statusEl), 260);
    }
  }

  startGuidedScan(onTick, onComplete) {
    if (!this.running) {
      showToast("Start the camera first, or choose a mood below.");
      return;
    }
    this.cancelAutoScan();
    this.autoScanCountdown = 8;
    this.autoSamples = [];
    onTick(this.autoScanCountdown);

    this.autoScanTimer = setInterval(async () => {
      this.autoScanCountdown -= 1;
      onTick(this.autoScanCountdown);
      if (this.autoScanCountdown <= 0) {
        clearInterval(this.autoScanTimer);
        this.autoScanTimer = null;
        const samples = this.autoSamples.length ? this.autoSamples : [this.latestResult];
        const avgScore = Math.round(
          samples.reduce((acc, s) => acc + s.score, 0) / samples.length
        );
        const moodFreq = {};
        for (const s of samples) {
          moodFreq[s.mood] = (moodFreq[s.mood] || 0) + 1;
        }
        const dominantMood = Object.entries(moodFreq).sort((a, b) => b[1] - a[1])[0][0];
        const last = samples[samples.length - 1];

        const saved = await this.saveMoodCheckin({
          mood: dominantMood,
          raw: last.raw,
          score: avgScore,
          confidence: last.confidence,
          expressions: last.expressions,
          source: "face_scan",
          note: "8-second guided facial reflection",
        });
        onComplete(saved);
      }
    }, 1000);
  }

  cancelAutoScan() {
    this.autoScanCountdown = 0;
    if (this.autoScanTimer) {
      clearInterval(this.autoScanTimer);
      this.autoScanTimer = null;
    }
  }

  async saveMoodCheckin({
    mood,
    raw = "neutral",
    score = 75,
    confidence = 0.9,
    expressions = {},
    source = "face_scan",
    note = "",
  }) {
    const data = await apiRequest("/api/moods", {
      method: "POST",
      body: {
        local_date: getLocalDateStr(),
        time_of_day: getTimeOfDay(),
        primary_mood: mood,
        raw_expression: raw,
        wellness_score: score,
        confidence,
        expressions,
        source,
        note,
      },
    });
    if (this.onScanSaved) {
      this.onScanSaved(data);
    }
    return data;
  }
}
