/* Main Serene SPA Controller */

import {
  apiRequest,
  escapeHtml,
  getLocalDateStr,
  getTimeOfDay,
  showToast,
} from "./api.js";
import { soundEngine } from "./audio.js";
import { DashboardManager } from "./dashboard.js";
import { FaceMoodScanner } from "./faceScan.js";
import { JournalManager } from "./journal.js";

const FOCUS_OPTIONS = [
  "Manage Stress",
  "Better Sleep",
  "Daily Reflection",
  "Emotional Clarity",
  "Build Calm",
  "Self-Compassion",
];

const BREATH_PRESETS = {
  "478": { name: "4-7-8 Calm Reset", phases: [["Inhale", 4, "inhale"], ["Hold", 7, "hold"], ["Exhale", 8, "exhale"]] },
  box: { name: "Box Breathing", phases: [["Inhale", 4, "inhale"], ["Hold", 4, "hold"], ["Exhale", 4, "exhale"], ["Hold", 4, "exhale"]] },
  coherent: { name: "Coherent 5-5", phases: [["Inhale", 5, "inhale"], ["Exhale", 5, "exhale"]] },
  sigh: { name: "Physiological Sigh", phases: [["Inhale", 3, "inhale"], ["Top-up", 1, "hold"], ["Long Exhale", 6, "exhale"]] },
};

const state = {
  user: null,
  currentView: "checkin",
  authMode: "login",
  pendingVerifyEmail: "",
  activeMood: "calm",
  activeBundle: null,
  breathTimer: null,
  breathRunning: false,
  onboardingGoals: new Set(),
  onboardingTint: "sage",
};

let scanner = null;
let journal = null;
let dashboard = null;

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme === "dark" ? "dark" : "light");
  const toggleBtn = document.getElementById("btn-theme-toggle");
  if (toggleBtn) {
    toggleBtn.textContent = theme === "dark" ? "Light Linen" : "Evening Mode";
  }
}

function switchView(viewName) {
  state.currentView = viewName;
  document.querySelectorAll("[data-view]").forEach((sec) => {
    sec.classList.toggle("hidden", sec.getAttribute("data-view") !== viewName);
  });
  document.querySelectorAll("[data-nav]").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-nav") === viewName);
  });

  if (viewName === "dashboard" && dashboard) {
    dashboard.load();
  } else if (viewName === "journal" && journal) {
    journal.loadToday();
  } else if (viewName === "archive" && journal) {
    journal.loadArchiveDays();
  }
}

async function loadAuthProviders() {
  try {
    const info = await apiRequest("/api/auth/providers");
    const notice = document.getElementById("mail-config-notice");
    if (notice) {
      notice.classList.toggle("hidden", Boolean(info.mail_configured || info.dev_outbox_enabled));
    }
  } catch {
    // Ignore provider check error
  }
}

async function refreshDevOutbox(filterEmail = "") {
  try {
    const res = await apiRequest(
      `/api/auth/dev-outbox${filterEmail ? `?email=${encodeURIComponent(filterEmail)}` : ""}`
    );
    const box = document.getElementById("dev-outbox-panel");
    const list = document.getElementById("dev-outbox-list");
    if (!box || !list) return;
    if (!res.dev_outbox_enabled || res.mail_configured || !res.messages.length) {
      box.classList.add("hidden");
      return;
    }
    box.classList.remove("hidden");
    list.innerHTML = res.messages
      .slice(0, 3)
      .map((m) => {
        let actionBtn = "";
        if (m.action_url && m.action_url.includes("reset_token=")) {
          actionBtn = `<button type="button" class="btn btn-soft btn-sm" style="margin-top:6px;" data-use-reset-token="${escapeHtml(m.otp_or_token)}">Open Password Reset</button>`;
        } else if (m.action_url && m.action_url.includes("verify_token=")) {
          actionBtn = `<button type="button" class="btn btn-soft btn-sm" style="margin-top:6px;" data-fill-verify="${escapeHtml(m.otp_or_token)}" data-fill-email="${escapeHtml(m.recipient)}">Use Verification Code</button>`;
        } else if (m.otp_or_token) {
          actionBtn = `<button type="button" class="btn btn-soft btn-sm" style="margin-top:6px;" data-fill-otp="${escapeHtml(m.otp_or_token)}" data-fill-email="${escapeHtml(m.recipient)}">Use Code</button>`;
        }
        return `
        <div class="outbox-item">
          <div style="font-weight:600;">${escapeHtml(m.subject)} → ${escapeHtml(m.recipient)}</div>
          <div style="color:var(--text-muted); font-size:12px; margin-top:2px;">
            ${m.otp_or_token ? `Code / Token: <code>${escapeHtml(m.otp_or_token)}</code>` : escapeHtml(m.body_text.slice(0, 120))}
          </div>
          ${actionBtn}
        </div>
      `;
      })
      .join("");

    list.querySelectorAll("[data-use-reset-token]").forEach((btn) => {
      btn.addEventListener("click", () => {
        setAuthMode("reset");
        document.getElementById("reset-token").value = btn.getAttribute("data-use-reset-token");
      });
    });
    list.querySelectorAll("[data-fill-verify]").forEach((btn) => {
      btn.addEventListener("click", () => {
        openVerifyPanel(btn.getAttribute("data-fill-email"));
        document.getElementById("verify-code").value = btn.getAttribute("data-fill-verify");
      });
    });
    list.querySelectorAll("[data-fill-otp]").forEach((btn) => {
      btn.addEventListener("click", () => {
        setAuthMode("otp");
        document.getElementById("otp-email").value = btn.getAttribute("data-fill-email");
        document.getElementById("otp-code").value = btn.getAttribute("data-fill-otp");
        document.getElementById("otp-verify-group").classList.remove("hidden");
      });
    });
  } catch {
    // Ignore outbox fetch failure
  }
}

function openVerifyPanel(email) {
  state.pendingVerifyEmail = email;
  const label = document.getElementById("verify-email-label");
  if (label) label.textContent = email;
  setAuthMode("verify");
}

function setAuthMode(mode) {
  state.authMode = mode;
  document.querySelectorAll("[data-auth-tab]").forEach((t) => {
    t.classList.toggle("active", t.getAttribute("data-auth-tab") === mode);
  });
  document.querySelectorAll("[data-auth-panel]").forEach((p) => {
    p.classList.toggle("hidden", p.getAttribute("data-auth-panel") !== mode);
  });
}

async function enterApp(user) {
  state.user = user;
  applyTheme(user.theme_preference || "light");

  document.getElementById("auth-view").classList.add("hidden");
  document.getElementById("app-view").classList.remove("hidden");

  renderUserChip();
  await loadMoodCatalog(state.activeMood);
  await loadTodayScans();
  await journal.loadToday();
  journal.startMidnightAndReminderWatchers();

  if (!user.onboarding_completed && !user.is_guest) {
    openOnboardingModal();
  }
}

function renderUserChip() {
  const user = state.user;
  if (!user) return;
  document.getElementById("topbar-user-name").textContent = user.display_name;
  const circle = document.getElementById("topbar-avatar");
  circle.className = `avatar-circle tint-${user.avatar_tint || "sage"}`;
  if (user.avatar_url) {
    circle.innerHTML = `<img src="${escapeHtml(user.avatar_url)}" alt="Avatar" />`;
  } else {
    circle.textContent = (user.display_name || "S").charAt(0).toUpperCase();
  }

  const greet = document.getElementById("checkin-greeting");
  if (greet) {
    const tod = getTimeOfDay();
    greet.textContent = `Good ${tod}, ${user.display_name}.`;
  }
}

async function loadMoodCatalog(mood) {
  state.activeMood = mood;
  const data = await apiRequest(`/api/moods/catalog?mood=${encodeURIComponent(mood)}`);
  state.activeBundle = data.bundle;
  renderMoodFeedback(data.bundle);
  renderCareTab(data.bundle);
}

function renderMoodFeedback(bundle) {
  const labelEl = document.getElementById("detected-mood-label");
  const reflEl = document.getElementById("detected-mood-reflection");
  const suggEl = document.getElementById("detected-mood-suggestions");
  if (labelEl) labelEl.textContent = bundle.label;
  if (reflEl) reflEl.textContent = bundle.reflection;
  if (suggEl) {
    suggEl.innerHTML = bundle.suggestions
      .map((s) => `<div class="suggestion-item"><span>•</span><span>${escapeHtml(s)}</span></div>`)
      .join("");
  }

  const camFrame = document.getElementById("camera-frame");
  if (camFrame) {
    camFrame.className = `camera-frame mood-${bundle.mood}`;
  }
}

function renderCareTab(bundle) {
  const moodBadge = document.getElementById("care-mood-badge");
  if (moodBadge) moodBadge.textContent = `Curated for: ${bundle.label}`;

  const playlistsEl = document.getElementById("care-playlists-grid");
  if (playlistsEl) {
    playlistsEl.innerHTML = bundle.playlists
      .map(
        (pl) => `
        <div class="playlist-card">
          <div>
            <span class="badge">${escapeHtml(pl.bpm)}</span>
            <h4 class="serif" style="font-size:22px; margin-top:8px;">${escapeHtml(pl.title)}</h4>
            <p style="font-size:13px; color:var(--text-muted); margin-top:4px;">${escapeHtml(pl.vibe)}</p>
          </div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            <a class="btn btn-soft btn-sm" href="${escapeHtml(pl.spotify_query)}" target="_blank" rel="noopener noreferrer" data-log-playlist="${escapeHtml(pl.title)}">Spotify</a>
            <a class="btn btn-outline btn-sm" href="${escapeHtml(pl.youtube_query)}" target="_blank" rel="noopener noreferrer" data-log-playlist="${escapeHtml(pl.title)}">YouTube Music</a>
          </div>
        </div>
      `
      )
      .join("");

    playlistsEl.querySelectorAll("[data-log-playlist]").forEach((a) => {
      a.addEventListener("click", () => {
        apiRequest("/api/activities", {
          method: "POST",
          body: {
            local_date: getLocalDateStr(),
            activity_type: "playlist",
            title: a.getAttribute("data-log-playlist"),
            duration_seconds: 180,
          },
        }).catch(() => {});
      });
    });
  }

  const actEl = document.getElementById("care-activities-list");
  if (actEl) {
    actEl.innerHTML = bundle.activities
      .map(
        (act) => `
        <div class="card-subtle" style="display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;">
          <div>
            <div style="font-weight:600;">${escapeHtml(act.title)} <span class="badge">${escapeHtml(act.duration)}</span></div>
            <p style="font-size:13px; color:var(--text-muted); margin-top:4px;">${escapeHtml(act.summary)}</p>
          </div>
          <button type="button" class="btn btn-soft btn-sm" data-start-activity="${escapeHtml(act.type)}" data-preset="${escapeHtml(act.preset || "478")}" data-act-title="${escapeHtml(act.title)}">Begin</button>
        </div>
      `
      )
      .join("");

    actEl.querySelectorAll("[data-start-activity]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const type = btn.getAttribute("data-start-activity");
        const preset = btn.getAttribute("data-preset");
        const title = btn.getAttribute("data-act-title");
        if (type === "breathing") {
          startBreathing(preset);
        } else {
          showToast(`${title} started — take your time.`);
          apiRequest("/api/activities", {
            method: "POST",
            body: { local_date: getLocalDateStr(), activity_type: type, title, duration_seconds: 120 },
          }).catch(() => {});
        }
      });
    });
  }
}

function updateLiveExpressionBars(result) {
  const scoreEl = document.getElementById("live-wellness-score");
  if (scoreEl) scoreEl.textContent = `${result.score}/100`;

  const barsEl = document.getElementById("expr-bars");
  if (!barsEl || !result.expressions) return;

  const items = [
    ["Happy", result.expressions.happy || 0],
    ["Calm", result.expressions.neutral || 0],
    ["Sad", result.expressions.sad || 0],
    ["Anxious", result.expressions.fearful || 0],
    ["Tense", result.expressions.angry || 0],
    ["Alert", result.expressions.surprised || 0],
  ];

  barsEl.innerHTML = items
    .map(([label, val]) => {
      const pct = Math.round(Math.min(1, Math.max(0, val)) * 100);
      return `
        <div class="expr-row">
          <span style="color:var(--text-muted);">${label}</span>
          <div class="expr-track"><div class="expr-fill" style="width:${pct}%"></div></div>
          <span style="text-align:right; color:var(--text-soft);">${pct}%</span>
        </div>
      `;
    })
    .join("");
}

async function loadTodayScans() {
  const data = await apiRequest(`/api/moods?local_date=${encodeURIComponent(getLocalDateStr())}`);
  const listEl = document.getElementById("today-scans-list");
  if (!listEl) return;

  if (!data.scans.length) {
    listEl.innerHTML = `<p style="color:var(--text-muted); font-size:13px;">No mood check-ins logged yet today.</p>`;
    return;
  }

  listEl.innerHTML = data.scans
    .slice(0, 5)
    .map((s) => {
      const tm = new Date(s.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      return `
        <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid var(--border-soft); font-size:13px;">
          <div>
            <span class="badge badge-sage">${escapeHtml(s.primary_mood)}</span>
            <span style="margin-left:6px; color:var(--text-muted);">${escapeHtml(s.source === "face_scan" ? "Face Scan" : "Manual")}</span>
          </div>
          <div>
            <strong>${s.wellness_score}</strong>/100 · <span style="color:var(--text-soft);">${escapeHtml(tm)}</span>
          </div>
        </div>
      `;
    })
    .join("");
}

function startBreathing(presetKey = "478") {
  stopBreathing();
  const presetSelect = document.getElementById("breath-preset-select");
  if (presetSelect) presetSelect.value = presetKey;
  const preset = BREATH_PRESETS[presetKey] || BREATH_PRESETS["478"];
  const orb = document.getElementById("breath-orb");
  const sub = document.getElementById("breath-instruction");
  const btn = document.getElementById("btn-breath-toggle");
  if (!orb || !sub) return;

  state.breathRunning = true;
  if (btn) btn.textContent = "Pause Breathing";

  let phaseIdx = 0;
  let remaining = preset.phases[0][1];

  const applyPhase = () => {
    const [label, secs, cls] = preset.phases[phaseIdx];
    remaining = secs;
    orb.className = `breath-orb ${cls}`;
    orb.textContent = label;
    sub.textContent = `${preset.name} · ${remaining}s`;
    soundEngine.playSoftChime(cls === "inhale" ? 432 : cls === "hold" ? 486 : 360);
  };

  applyPhase();
  state.breathTimer = setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) {
      phaseIdx = (phaseIdx + 1) % preset.phases.length;
      applyPhase();
    } else {
      const [label] = preset.phases[phaseIdx];
      orb.textContent = `${label} · ${remaining}`;
    }
  }, 1000);

  apiRequest("/api/activities", {
    method: "POST",
    body: {
      local_date: getLocalDateStr(),
      activity_type: "breathing",
      title: preset.name,
      duration_seconds: 120,
    },
  }).catch(() => {});
}

function stopBreathing() {
  clearInterval(state.breathTimer);
  state.breathRunning = false;
  const orb = document.getElementById("breath-orb");
  const sub = document.getElementById("breath-instruction");
  const btn = document.getElementById("btn-breath-toggle");
  if (orb) {
    orb.className = "breath-orb";
    orb.textContent = "Ready";
  }
  if (sub) sub.textContent = "Press Begin when you want a gentle breathing rhythm.";
  if (btn) btn.textContent = "Begin Breathing";
}

function openOnboardingModal() {
  const modal = document.getElementById("onboarding-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  document.getElementById("onboard-name").value = state.user.display_name || "";
  const container = document.getElementById("onboard-goals");
  state.onboardingGoals = new Set(state.user.focus_goals || []);
  container.innerHTML = FOCUS_OPTIONS.map(
    (g) => `<button type="button" class="chip ${state.onboardingGoals.has(g) ? "active" : ""}" data-goal="${escapeHtml(g)}">${escapeHtml(g)}</button>`
  ).join("");
  container.querySelectorAll("[data-goal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const g = btn.getAttribute("data-goal");
      if (state.onboardingGoals.has(g)) state.onboardingGoals.delete(g);
      else state.onboardingGoals.add(g);
      btn.classList.toggle("active");
    });
  });
}

function openProfileModal() {
  const u = state.user;
  if (!u) return;
  document.getElementById("profile-name").value = u.display_name || "";
  document.getElementById("profile-pronouns").value = u.pronouns || "";
  document.getElementById("profile-age").value = u.age_range || "";
  document.getElementById("profile-intention").value = u.intention || "";
  document.getElementById("profile-tone").value = u.tone_preference || "gentle";
  document.getElementById("profile-reminder-enabled").checked = Boolean(u.reminder_enabled);
  document.getElementById("profile-reminder-time").value = u.reminder_time || "20:00";
  document.getElementById("profile-pin").value = "";
  document.getElementById("profile-modal").classList.remove("hidden");
}

function wireEvents() {
  // Auth tabs
  document.querySelectorAll("[data-auth-tab]").forEach((tab) => {
    tab.addEventListener("click", () => setAuthMode(tab.getAttribute("data-auth-tab")));
  });

  // Password Login
  document.getElementById("form-login").addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("login-email").value;
    try {
      const res = await apiRequest("/api/auth/login", {
        method: "POST",
        body: {
          email,
          password: document.getElementById("login-password").value,
        },
      });
      await enterApp(res.user);
    } catch (err) {
      showToast(err.message);
      if (err.needsVerification) {
        openVerifyPanel(email.trim().toLowerCase());
      }
    }
  });

  // Register -> Email Verification Step
  document.getElementById("form-register").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await apiRequest("/api/auth/register", {
        method: "POST",
        body: {
          display_name: document.getElementById("reg-name").value,
          email: document.getElementById("reg-email").value,
          password: document.getElementById("reg-password").value,
        },
      });
      showToast(res.message);
      openVerifyPanel(res.email);
      refreshDevOutbox(res.email);
    } catch (err) {
      showToast(err.message);
    }
  });

  // Verify Email Ownership
  document.getElementById("form-verify-email").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await apiRequest("/api/auth/verify-email", {
        method: "POST",
        body: {
          email: state.pendingVerifyEmail,
          code: document.getElementById("verify-code").value,
        },
      });
      showToast("Email verified — welcome to Serene.");
      await enterApp(res.user);
    } catch (err) {
      showToast(err.message);
    }
  });

  document.getElementById("btn-resend-verify").addEventListener("click", async () => {
    if (!state.pendingVerifyEmail) return;
    try {
      const res = await apiRequest("/api/auth/verify-email/resend", {
        method: "POST",
        body: { email: state.pendingVerifyEmail },
      });
      showToast(res.message);
      refreshDevOutbox(state.pendingVerifyEmail);
    } catch (err) {
      showToast(err.message);
    }
  });

  document.getElementById("btn-back-to-login").addEventListener("click", () => {
    setAuthMode("login");
  });

  // Email Magic Code OTP
  document.getElementById("btn-send-otp").addEventListener("click", async () => {
    const email = document.getElementById("otp-email").value;
    try {
      const res = await apiRequest("/api/auth/otp/request", {
        method: "POST",
        body: { email },
      });
      document.getElementById("otp-verify-group").classList.remove("hidden");
      showToast(res.message);
      refreshDevOutbox(email);
    } catch (err) {
      showToast(err.message);
    }
  });

  document.getElementById("form-otp").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await apiRequest("/api/auth/otp/verify", {
        method: "POST",
        body: {
          email: document.getElementById("otp-email").value,
          code: document.getElementById("otp-code").value,
        },
      });
      await enterApp(res.user);
    } catch (err) {
      showToast(err.message);
    }
  });

  // Quick PIN Login
  document.getElementById("form-pin-login").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await apiRequest("/api/auth/pin-login", {
        method: "POST",
        body: {
          email: document.getElementById("pin-email").value,
          pin: document.getElementById("pin-code").value,
        },
      });
      await enterApp(res.user);
    } catch (err) {
      showToast(err.message);
    }
  });

  // Guest Demo Explorer
  document.getElementById("btn-guest-login").addEventListener("click", async () => {
    try {
      const res = await apiRequest("/api/auth/guest", {
        method: "POST",
        body: { local_date: getLocalDateStr() },
      });
      showToast("Welcome to your calm demo space.");
      await enterApp(res.user);
    } catch (err) {
      showToast(err.message);
    }
  });

  // Forgot Password Recovery
  document.getElementById("btn-forgot-link").addEventListener("click", () => setAuthMode("forgot"));
  document.getElementById("form-forgot").addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("forgot-email").value;
    try {
      const res = await apiRequest("/api/auth/recovery/request", {
        method: "POST",
        body: { email },
      });
      showToast(res.message);
      refreshDevOutbox(email);
    } catch (err) {
      showToast(err.message);
    }
  });

  document.getElementById("form-reset").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await apiRequest("/api/auth/recovery/reset", {
        method: "POST",
        body: {
          token: document.getElementById("reset-token").value,
          new_password: document.getElementById("reset-new-password").value,
        },
      });
      showToast("Password updated.");
      await enterApp(res.user);
    } catch (err) {
      showToast(err.message);
    }
  });

  // Navigation
  document.querySelectorAll("[data-nav]").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.getAttribute("data-nav")));
  });

  // Theme Toggle
  document.getElementById("btn-theme-toggle").addEventListener("click", async () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
    if (state.user) {
      const res = await apiRequest("/api/profile", {
        method: "PATCH",
        body: { theme_preference: next },
      });
      state.user = res.user;
    }
  });

  // Camera & Mood Scanner controls
  const videoEl = document.getElementById("webcam-video");
  const canvasEl = document.getElementById("webcam-overlay");
  const statusEl = document.getElementById("camera-status");
  const placeholderEl = document.getElementById("camera-placeholder");

  document.getElementById("btn-toggle-camera").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    if (scanner.running) {
      scanner.stopCamera(videoEl, canvasEl, statusEl);
      placeholderEl.classList.remove("hidden");
      btn.textContent = "Start Face Scan";
    } else {
      try {
        placeholderEl.classList.add("hidden");
        btn.textContent = "Pause Camera";
        await scanner.startCamera(videoEl, canvasEl, statusEl);
      } catch (err) {
        placeholderEl.classList.remove("hidden");
        btn.textContent = "Start Face Scan";
        statusEl.textContent = err.message;
        showToast(err.message);
      }
    }
  });

  document.getElementById("btn-guided-scan").addEventListener("click", () => {
    const btn = document.getElementById("btn-guided-scan");
    scanner.startGuidedScan(
      (secs) => {
        btn.textContent = secs > 0 ? `Sensing... ${secs}s` : "Guided 8s Scan";
      },
      async (saved) => {
        showToast(`Recorded mood: ${saved.bundle.label}`);
        await loadMoodCatalog(saved.scan.primary_mood);
        await loadTodayScans();
      }
    );
  });

  document.getElementById("btn-save-current-scan").addEventListener("click", async () => {
    const cur = scanner.latestResult;
    const saved = await scanner.saveMoodCheckin({
      mood: cur.mood,
      raw: cur.raw,
      score: cur.score,
      confidence: cur.confidence,
      expressions: cur.expressions,
      source: scanner.running ? "face_scan" : "manual",
    });
    showToast(`Saved check-in (${saved.bundle.label})`);
    await loadMoodCatalog(saved.scan.primary_mood);
    await loadTodayScans();
  });

  document.getElementById("toggle-landmarks").addEventListener("change", (e) => {
    scanner.showLandmarks = e.target.checked;
  });

  // Manual Mood Chips
  document.querySelectorAll("[data-manual-mood]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      document.querySelectorAll("[data-manual-mood]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const mood = btn.getAttribute("data-manual-mood");
      const score = Number(btn.getAttribute("data-mood-score"));
      scanner.latestResult = {
        ...scanner.latestResult,
        mood,
        score,
        raw: mood,
      };
      updateLiveExpressionBars(scanner.latestResult);
      await loadMoodCatalog(mood);
    });
  });

  // Soundscapes
  document.querySelectorAll("[data-sound-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-sound-toggle");
      const tile = btn.closest(".sound-tile");
      const slider = tile.querySelector("input[type='range']");
      if (soundEngine.isPlaying(id)) {
        soundEngine.stopSound(id);
        tile.classList.remove("playing");
        btn.textContent = "Play";
      } else {
        soundEngine.startSound(id, Number(slider.value) / 100);
        tile.classList.add("playing");
        btn.textContent = "Pause";
        apiRequest("/api/activities", {
          method: "POST",
          body: { local_date: getLocalDateStr(), activity_type: "soundscape", title: `Ambient: ${id}`, duration_seconds: 180 },
        }).catch(() => {});
      }
    });
  });

  document.querySelectorAll("[data-sound-vol]").forEach((slider) => {
    slider.addEventListener("input", () => {
      const id = slider.getAttribute("data-sound-vol");
      soundEngine.setVolume(id, Number(slider.value) / 100);
    });
  });

  // Breathing toggle
  document.getElementById("btn-breath-toggle").addEventListener("click", () => {
    if (state.breathRunning) stopBreathing();
    else startBreathing(document.getElementById("breath-preset-select").value);
  });

  // Journal controls
  document.getElementById("btn-rotate-prompt").addEventListener("click", () => journal.rotatePrompt());
  document.getElementById("journal-photo-input").addEventListener("change", (e) => {
    journal.addPhotos(e.target.files);
    e.target.value = "";
  });
  document.getElementById("btn-record-voice").addEventListener("click", () => journal.toggleVoiceRecording());
  document.getElementById("btn-discard-voice").addEventListener("click", () => journal.discardVoice());
  document.querySelectorAll("[data-journal-mood]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-journal-mood]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      journal.selectedMood = btn.getAttribute("data-journal-mood");
    });
  });
  document.getElementById("btn-save-journal").addEventListener("click", async () => {
    try {
      await journal.saveEntry();
    } catch (err) {
      showToast(err.message);
    }
  });
  document.getElementById("btn-preview-8pm").addEventListener("click", async () => {
    await journal.checkReminder(true);
    showToast("Triggered 8:00 PM check-in notification preview.");
  });
  document.getElementById("btn-banner-write").addEventListener("click", () => {
    switchView("journal");
    document.getElementById("journal-content").focus();
  });

  // Dashboard range filters
  document.querySelectorAll("[data-range-days]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-range-days]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      dashboard.customStart = "";
      dashboard.customEnd = "";
      dashboard.days = Number(btn.getAttribute("data-range-days"));
      dashboard.load();
    });
  });

  document.getElementById("btn-apply-custom-range").addEventListener("click", () => {
    const start = document.getElementById("dash-start").value;
    const end = document.getElementById("dash-end").value;
    if (!start || !end) {
      showToast("Pick both start and end dates.");
      return;
    }
    dashboard.customStart = start;
    dashboard.customEnd = end;
    dashboard.load();
  });

  // Onboarding modal
  document.querySelectorAll("[data-onboard-tint]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-onboard-tint]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.onboardingTint = btn.getAttribute("data-onboard-tint");
    });
  });

  document.getElementById("btn-onboard-skip").addEventListener("click", async () => {
    document.getElementById("onboarding-modal").classList.add("hidden");
    const res = await apiRequest("/api/profile", {
      method: "PATCH",
      body: { onboarding_completed: true },
    });
    state.user = res.user;
  });

  document.getElementById("btn-onboard-save").addEventListener("click", async () => {
    const res = await apiRequest("/api/profile", {
      method: "PATCH",
      body: {
        display_name: document.getElementById("onboard-name").value,
        avatar_tint: state.onboardingTint,
        focus_goals: [...state.onboardingGoals],
        tone_preference: document.getElementById("onboard-tone").value,
        reminder_enabled: document.getElementById("onboard-reminder").checked,
        onboarding_completed: true,
      },
    });
    state.user = res.user;
    renderUserChip();
    document.getElementById("onboarding-modal").classList.add("hidden");
    showToast("Your calm space is personalized.");
  });

  // Profile modal
  document.getElementById("btn-open-profile").addEventListener("click", openProfileModal);
  document.getElementById("btn-close-profile").addEventListener("click", () => {
    document.getElementById("profile-modal").classList.add("hidden");
  });
  document.getElementById("profile-avatar-file").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiRequest("/api/profile/avatar", { method: "POST", body: form });
      state.user = res.user;
      renderUserChip();
      showToast("Avatar updated.");
    } catch (err) {
      showToast(err.message);
    }
  });
  document.getElementById("form-profile").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const payload = {
        display_name: document.getElementById("profile-name").value,
        pronouns: document.getElementById("profile-pronouns").value,
        age_range: document.getElementById("profile-age").value,
        intention: document.getElementById("profile-intention").value,
        tone_preference: document.getElementById("profile-tone").value,
        reminder_enabled: document.getElementById("profile-reminder-enabled").checked,
        reminder_time: document.getElementById("profile-reminder-time").value || "20:00",
      };
      const pinVal = document.getElementById("profile-pin").value.trim();
      if (pinVal) payload.quick_pin = pinVal;

      const res = await apiRequest("/api/profile", { method: "PATCH", body: payload });
      state.user = res.user;
      renderUserChip();
      document.getElementById("profile-modal").classList.add("hidden");
      showToast("Profile saved.");
    } catch (err) {
      showToast(err.message);
    }
  });

  document.getElementById("btn-export-data").addEventListener("click", async () => {
    const data = await apiRequest("/api/profile/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `serene-wellness-${getLocalDateStr()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  });

  document.getElementById("btn-delete-account").addEventListener("click", async () => {
    if (!confirm("Permanently delete your account, mood scans, and journal entries? This cannot be undone.")) {
      return;
    }
    try {
      await apiRequest("/api/profile", { method: "DELETE" });
      soundEngine.stopAll();
      if (journal) journal.stopWatchers();
      state.user = null;
      document.getElementById("profile-modal").classList.add("hidden");
      document.getElementById("app-view").classList.add("hidden");
      document.getElementById("auth-view").classList.remove("hidden");
      showToast("Account permanently deleted.");
    } catch (err) {
      showToast(err.message);
    }
  });

  document.getElementById("btn-logout").addEventListener("click", async () => {
    await apiRequest("/api/auth/logout", { method: "POST" });
    soundEngine.stopAll();
    if (journal) journal.stopWatchers();
    if (scanner && scanner.running) {
      scanner.stopCamera(
        document.getElementById("webcam-video"),
        document.getElementById("webcam-overlay"),
        document.getElementById("camera-status")
      );
    }
    state.user = null;
    document.getElementById("profile-modal").classList.add("hidden");
    document.getElementById("app-view").classList.add("hidden");
    document.getElementById("auth-view").classList.remove("hidden");
    showToast("Signed out.");
  });

  // Crisis support modal
  document.getElementById("btn-open-support").addEventListener("click", () => {
    document.getElementById("support-modal").classList.remove("hidden");
  });
  document.getElementById("btn-close-support").addEventListener("click", () => {
    document.getElementById("support-modal").classList.add("hidden");
  });
}

async function init() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
    navigator.serviceWorker.addEventListener("message", (ev) => {
      if (ev.data && ev.data.type === "OPEN_JOURNAL") {
        switchView("journal");
      }
    });
  }

  scanner = new FaceMoodScanner({
    onMoodUpdate: (result, fromCamera) => {
      updateLiveExpressionBars(result);
      if (fromCamera && result.mood !== state.activeMood) {
        loadMoodCatalog(result.mood);
      }
    },
    onScanSaved: () => {
      loadTodayScans();
    },
  });

  journal = new JournalManager({
    onJournalChange: () => {
      const banner = document.getElementById("evening-reminder-banner");
      if (banner) banner.classList.add("hidden");
    },
    onReminderState: (res) => {
      const banner = document.getElementById("evening-reminder-banner");
      if (!banner) return;
      if (res && !res.written_today && (res.should_notify || new Date().getHours() >= 20)) {
        banner.classList.remove("hidden");
      } else {
        banner.classList.add("hidden");
      }
    },
  });

  dashboard = new DashboardManager({
    onSelectArchiveDay: (dateStr) => {
      switchView("archive");
      journal.loadArchiveDay(dateStr);
    },
  });

  wireEvents();
  loadAuthProviders();

  // Handle email verification link (?verify_token=...) or password recovery link (?reset_token=...)
  const params = new URLSearchParams(window.location.search);
  const verifyToken = params.get("verify_token");
  if (verifyToken) {
    try {
      const res = await apiRequest("/api/auth/verify-email", {
        method: "POST",
        body: { token: verifyToken },
      });
      window.history.replaceState({}, "", "/");
      showToast("Email verified — welcome to Serene.");
      await enterApp(res.user);
      return;
    } catch (err) {
      showToast(err.message);
    }
  }

  const resetToken = params.get("reset_token");
  if (resetToken) {
    setAuthMode("reset");
    document.getElementById("reset-token").value = resetToken;
  }

  // Restore session if signed in
  try {
    const me = await apiRequest("/api/auth/me");
    await enterApp(me.user);
  } catch {
    refreshDevOutbox();
  }
}

document.addEventListener("DOMContentLoaded", init);
