/* Daily Digital Journal: text, photos, voice recorder, midnight reset & 8 PM reminders */

import {
  apiRequest,
  escapeHtml,
  formatNiceDate,
  getLocalDateStr,
  getLocalTimeStr,
  getTimeOfDay,
  showToast,
} from "./api.js";

export class JournalManager {
  constructor({ onJournalChange, onReminderState }) {
    this.onJournalChange = onJournalChange;
    this.onReminderState = onReminderState;

    this.activeDate = getLocalDateStr();
    this.writtenToday = false;
    this.prompts = [];
    this.promptIndex = 0;
    this.selectedMood = "calm";

    this.selectedPhotos = [];
    this.recordedBlob = null;
    this.recordedUrl = null;
    this.recordedSeconds = 0;

    this.mediaRecorder = null;
    this.micStream = null;
    this.audioChunks = [];
    this.recordTimer = null;
    this.analyser = null;
    this.waveAnimFrame = null;

    this.midnightTimer = null;
    this.reminderInterval = null;
  }

  async loadToday() {
    this.activeDate = getLocalDateStr();
    const data = await apiRequest(`/api/journal?local_date=${encodeURIComponent(this.activeDate)}`);
    this.writtenToday = Boolean(data.written_today);
    this.prompts = data.prompts || [];
    this.renderToday(data);
    this.loadArchiveDays();
    return data;
  }

  renderToday(data) {
    const dateLabel = document.getElementById("journal-today-label");
    if (dateLabel) {
      dateLabel.textContent = formatNiceDate(data.local_date);
    }

    const promptEl = document.getElementById("journal-prompt-text");
    if (promptEl && this.prompts.length) {
      promptEl.textContent = this.prompts[this.promptIndex % this.prompts.length];
    }

    const statusBadge = document.getElementById("journal-status-badge");
    if (statusBadge) {
      statusBadge.textContent = data.written_today
        ? `${data.count} reflection${data.count === 1 ? "" : "s"} saved today`
        : "Open canvas — resets at midnight";
    }

    const listEl = document.getElementById("journal-entries-list");
    if (!listEl) return;

    if (!data.entries || data.entries.length === 0) {
      listEl.innerHTML = `
        <div class="card-subtle" style="text-align:center; padding: 28px;">
          <p class="serif" style="font-size: 22px; margin-bottom: 6px;">A quiet blank page for today</p>
          <p style="color: var(--text-muted); font-size: 14px;">
            Write a few lines, attach a photo from your day, or record a gentle voice note whenever you're ready.
          </p>
        </div>
      `;
      return;
    }

    listEl.innerHTML = data.entries.map((entry) => this.renderEntryCard(entry, true)).join("");
    listEl.querySelectorAll("[data-delete-entry]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-delete-entry");
        await apiRequest(`/api/journal/${id}`, { method: "DELETE" });
        showToast("Reflection removed.");
        await this.loadToday();
        if (this.onJournalChange) this.onJournalChange();
      });
    });
  }

  renderEntryCard(entry, allowDelete = false) {
    const photos = (entry.media || []).filter((m) => m.media_type === "image");
    const audios = (entry.media || []).filter((m) => m.media_type === "audio");
    const createdTime = entry.created_at
      ? new Date(entry.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      : "";

    return `
      <article class="card entry-card">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge badge-sage">${escapeHtml(entry.mood_tag)}</span>
            <span class="badge">${escapeHtml(entry.time_of_day)} · ${escapeHtml(createdTime)}</span>
          </div>
          ${
            allowDelete
              ? `<button class="btn btn-ghost btn-sm" data-delete-entry="${escapeHtml(entry.id)}" type="button">Delete</button>`
              : ""
          }
        </div>
        ${
          entry.prompt_used
            ? `<p style="font-size:12px; color: var(--text-soft); font-style: italic;">Prompt: ${escapeHtml(entry.prompt_used)}</p>`
            : ""
        }
        ${entry.content ? `<p style="white-space: pre-wrap;">${escapeHtml(entry.content)}</p>` : ""}
        ${
          entry.gratitude_note
            ? `<div class="card-subtle" style="padding:10px 14px; font-size:13px;"><strong>Grateful for:</strong> ${escapeHtml(entry.gratitude_note)}</div>`
            : ""
        }
        ${
          photos.length
            ? `<div class="entry-photos">${photos
                .map((p) => `<img src="${escapeHtml(p.url)}" alt="Journal memory" loading="lazy" />`)
                .join("")}</div>`
            : ""
        }
        ${
          audios.length
            ? audios
                .map(
                  (a) => `
                  <div class="card-subtle" style="padding: 10px 14px; display:grid; gap:6px;">
                    <span style="font-size:12px; color: var(--text-muted);">Voice Note (${Math.round(a.duration_seconds || 0)}s)</span>
                    <audio controls src="${escapeHtml(a.url)}" style="width:100%; height:36px;"></audio>
                  </div>`
                )
                .join("")
            : ""
        }
      </article>
    `;
  }

  rotatePrompt() {
    this.promptIndex += 1;
    const promptEl = document.getElementById("journal-prompt-text");
    if (promptEl && this.prompts.length) {
      promptEl.textContent = this.prompts[this.promptIndex % this.prompts.length];
    }
  }

  addPhotos(fileList) {
    const incoming = Array.from(fileList || []).filter((f) => f.type.startsWith("image/"));
    this.selectedPhotos = [...this.selectedPhotos, ...incoming].slice(0, 6);
    this.renderPhotoPreviews();
  }

  renderPhotoPreviews() {
    const grid = document.getElementById("journal-photo-previews");
    if (!grid) return;
    if (!this.selectedPhotos.length) {
      grid.innerHTML = "";
      return;
    }
    grid.innerHTML = this.selectedPhotos
      .map((file, idx) => {
        const url = URL.createObjectURL(file);
        return `
          <div class="photo-thumb">
            <img src="${url}" alt="Preview" />
            <button type="button" data-remove-photo="${idx}"
              style="position:absolute; top:4px; right:4px; border:none; border-radius:999px; background:rgba(0,0,0,0.6); color:#fff; width:22px; height:22px; cursor:pointer; font-size:12px;">×</button>
          </div>
        `;
      })
      .join("");

    grid.querySelectorAll("[data-remove-photo]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.getAttribute("data-remove-photo"));
        this.selectedPhotos.splice(idx, 1);
        this.renderPhotoPreviews();
      });
    });
  }

  async toggleVoiceRecording() {
    if (this.mediaRecorder && this.mediaRecorder.state === "recording") {
      this.stopVoiceRecording();
      return;
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showToast("Microphone recording is not supported in this browser.");
      return;
    }

    try {
      this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      this.mediaRecorder = mimeType
        ? new MediaRecorder(this.micStream, { mimeType })
        : new MediaRecorder(this.micStream);
      this.audioChunks = [];
      this.recordedSeconds = 0;

      const box = document.getElementById("voice-recorder-box");
      const timerEl = document.getElementById("voice-timer");
      const btn = document.getElementById("btn-record-voice");
      if (box) box.classList.remove("hidden");
      if (btn) btn.textContent = "Stop Recording";

      this.setupWaveform(this.micStream);

      this.mediaRecorder.ondataavailable = (ev) => {
        if (ev.data && ev.data.size > 0) this.audioChunks.push(ev.data);
      };

      this.mediaRecorder.onstop = () => {
        const blob = new Blob(this.audioChunks, {
          type: this.mediaRecorder.mimeType || "audio/webm",
        });
        this.recordedBlob = blob;
        if (this.recordedUrl) URL.revokeObjectURL(this.recordedUrl);
        this.recordedUrl = URL.createObjectURL(blob);

        const previewAudio = document.getElementById("voice-preview-player");
        if (previewAudio) {
          previewAudio.src = this.recordedUrl;
          previewAudio.classList.remove("hidden");
        }
        const discardBtn = document.getElementById("btn-discard-voice");
        if (discardBtn) discardBtn.classList.remove("hidden");
        if (btn) btn.textContent = "Re-record Voice";
        this.cleanupMic();
      };

      this.mediaRecorder.start(250);
      this.recordTimer = setInterval(() => {
        this.recordedSeconds += 1;
        if (timerEl) {
          const mins = String(Math.floor(this.recordedSeconds / 60)).padStart(2, "0");
          const secs = String(this.recordedSeconds % 60).padStart(2, "0");
          timerEl.textContent = `Recording ${mins}:${secs}`;
        }
      }, 1000);
    } catch {
      showToast("Microphone permission was denied.");
    }
  }

  setupWaveform(stream) {
    const canvas = document.getElementById("voice-waveform");
    if (!canvas) return;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    const ctxAudio = new AudioCtx();
    const source = ctxAudio.createMediaStreamSource(stream);
    this.analyser = ctxAudio.createAnalyser();
    this.analyser.fftSize = 128;
    source.connect(this.analyser);
    const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
    const ctx2d = canvas.getContext("2d");

    const draw = () => {
      if (!this.analyser) return;
      this.analyser.getByteTimeDomainData(dataArray);
      ctx2d.clearRect(0, 0, canvas.width, canvas.height);
      ctx2d.strokeStyle = "#6b8e78";
      ctx2d.lineWidth = 2;
      ctx2d.beginPath();
      const slice = canvas.width / dataArray.length;
      for (let i = 0; i < dataArray.length; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * canvas.height) / 2;
        if (i === 0) ctx2d.moveTo(0, y);
        else ctx2d.lineTo(i * slice, y);
      }
      ctx2d.stroke();
      this.waveAnimFrame = requestAnimationFrame(draw);
    };
    draw();
  }

  stopVoiceRecording() {
    if (this.mediaRecorder && this.mediaRecorder.state === "recording") {
      this.mediaRecorder.stop();
    }
  }

  cleanupMic() {
    clearInterval(this.recordTimer);
    cancelAnimationFrame(this.waveAnimFrame);
    this.analyser = null;
    if (this.micStream) {
      this.micStream.getTracks().forEach((t) => t.stop());
      this.micStream = null;
    }
  }

  discardVoice() {
    this.stopVoiceRecording();
    this.cleanupMic();
    this.recordedBlob = null;
    this.recordedSeconds = 0;
    if (this.recordedUrl) URL.revokeObjectURL(this.recordedUrl);
    this.recordedUrl = null;
    const box = document.getElementById("voice-recorder-box");
    const player = document.getElementById("voice-preview-player");
    const discardBtn = document.getElementById("btn-discard-voice");
    const btn = document.getElementById("btn-record-voice");
    if (box) box.classList.add("hidden");
    if (player) {
      player.src = "";
      player.classList.add("hidden");
    }
    if (discardBtn) discardBtn.classList.add("hidden");
    if (btn) btn.textContent = "Record Voice";
  }

  async saveEntry() {
    const contentEl = document.getElementById("journal-content");
    const gratitudeEl = document.getElementById("journal-gratitude");
    const promptEl = document.getElementById("journal-prompt-text");

    const form = new FormData();
    form.append("local_date", getLocalDateStr());
    form.append("time_of_day", getTimeOfDay());
    form.append("mood_tag", this.selectedMood);
    form.append("prompt_used", promptEl ? promptEl.textContent : "");
    form.append("content", contentEl ? contentEl.value : "");
    form.append("gratitude_note", gratitudeEl ? gratitudeEl.value : "");
    form.append("audio_duration", String(this.recordedSeconds || 0));

    for (const file of this.selectedPhotos) {
      form.append("photos", file);
    }
    if (this.recordedBlob) {
      form.append("audio", this.recordedBlob, "voice-note.webm");
    }

    const res = await apiRequest("/api/journal", {
      method: "POST",
      body: form,
    });

    if (contentEl) contentEl.value = "";
    if (gratitudeEl) gratitudeEl.value = "";
    this.selectedPhotos = [];
    this.renderPhotoPreviews();
    this.discardVoice();
    this.writtenToday = true;

    showToast("Saved to today's journal.");
    await this.loadToday();
    if (this.onJournalChange) this.onJournalChange();
    return res;
  }

  async loadArchiveDays() {
    const data = await apiRequest("/api/journal/days");
    const listEl = document.getElementById("archive-days-list");
    if (!listEl) return;

    if (!data.days || !data.days.length) {
      listEl.innerHTML = `<p style="color:var(--text-muted); font-size:14px;">Past reflections will appear here after your first day.</p>`;
      return;
    }

    listEl.innerHTML = data.days
      .map(
        (d) => `
          <button type="button" class="chip" data-archive-date="${escapeHtml(d.local_date)}">
            ${escapeHtml(formatNiceDate(d.local_date))} (${d.entry_count})
          </button>
        `
      )
      .join("");

    listEl.querySelectorAll("[data-archive-date]").forEach((btn) => {
      btn.addEventListener("click", () => {
        listEl.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
        btn.classList.add("active");
        this.loadArchiveDay(btn.getAttribute("data-archive-date"));
      });
    });

    // Load latest day into archive viewer automatically
    const first = data.days[0];
    if (first) {
      const firstBtn = listEl.querySelector(`[data-archive-date="${first.local_date}"]`);
      if (firstBtn) firstBtn.classList.add("active");
      this.loadArchiveDay(first.local_date);
    }
  }

  async loadArchiveDay(dateStr) {
    const data = await apiRequest(`/api/journal?local_date=${encodeURIComponent(dateStr)}`);
    const container = document.getElementById("archive-day-entries");
    if (!container) return;
    if (!data.entries.length) {
      container.innerHTML = `<p style="color:var(--text-muted);">No entries found for ${escapeHtml(formatNiceDate(dateStr))}.</p>`;
      return;
    }
    container.innerHTML = data.entries.map((e) => this.renderEntryCard(e, false)).join("");
  }

  startMidnightAndReminderWatchers() {
    this.scheduleMidnightReset();
    clearInterval(this.reminderInterval);
    this.checkReminder(false);
    this.reminderInterval = setInterval(() => {
      if (getLocalDateStr() !== this.activeDate) {
        this.handleMidnightRollover();
      }
      this.checkReminder(false);
    }, 60 * 1000);

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && getLocalDateStr() !== this.activeDate) {
        this.handleMidnightRollover();
      }
    });
  }

  scheduleMidnightReset() {
    clearTimeout(this.midnightTimer);
    const now = new Date();
    const nextMidnight = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate() + 1,
      0,
      0,
      2
    );
    const ms = Math.max(1000, nextMidnight.getTime() - now.getTime());
    this.midnightTimer = setTimeout(() => {
      this.handleMidnightRollover();
      this.scheduleMidnightReset();
    }, ms);
  }

  async handleMidnightRollover() {
    this.activeDate = getLocalDateStr();
    this.writtenToday = false;
    await this.loadToday();
    if (this.onReminderState) {
      this.onReminderState({ should_notify: false, written_today: false });
    }
    showToast("A new day has begun — your daily journal canvas has reset for today.");
  }

  async checkReminder(forcePreview = false) {
    try {
      const res = await apiRequest("/api/reminders/check", {
        method: "POST",
        body: {
          local_date: getLocalDateStr(),
          local_time: getLocalTimeStr(),
          force_preview: forcePreview,
        },
      });
      if (this.onReminderState) {
        this.onReminderState(res);
      }
      if (res.should_notify) {
        await this.dispatchBrowserNotification(res.title, res.body);
      }
      return res;
    } catch {
      return null;
    }
  }

  async dispatchBrowserNotification(title, body) {
    if (!("Notification" in window)) return;
    if (Notification.permission === "default") {
      try {
        await Notification.requestPermission();
      } catch {
        return;
      }
    }
    if (Notification.permission !== "granted") return;

    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({
        type: "SHOW_REMINDER",
        title,
        body,
      });
    } else {
      new Notification(title, { body, tag: "serene-8pm-reminder" });
    }
  }
}
