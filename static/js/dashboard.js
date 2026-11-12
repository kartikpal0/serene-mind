/* Wellness Tracker Dashboard powered by Chart.js */

import { apiRequest, escapeHtml, formatNiceDate, getLocalDateStr } from "./api.js";

const MOOD_COLORS = {
  happy: "#6b8e78",
  calm: "#84a993",
  surprised: "#c6a15b",
  tired: "#8d9aa3",
  anxious: "#8c7fa8",
  stressed: "#c88a70",
  sad: "#7390a6",
};

export class DashboardManager {
  constructor({ onSelectArchiveDay }) {
    this.onSelectArchiveDay = onSelectArchiveDay;
    this.days = 14;
    this.customStart = "";
    this.customEnd = "";
    this.trendChart = null;
    this.distChart = null;
    this.rhythmChart = null;
  }

  async load() {
    const today = getLocalDateStr();
    let url = `/api/dashboard?today=${encodeURIComponent(today)}&days=${this.days}`;
    if (this.customStart && this.customEnd) {
      url = `/api/dashboard?today=${encodeURIComponent(today)}&start_date=${encodeURIComponent(
        this.customStart
      )}&end_date=${encodeURIComponent(this.customEnd)}`;
    }
    const data = await apiRequest(url);
    this.renderSummary(data.summary);
    this.renderTrendChart(data.timeline);
    this.renderDistributionChart(data.mood_distribution);
    this.renderRhythmChart(data.time_of_day_rhythm);
    this.renderHeatmap(data.heatmap);
    this.renderInsights(data.insights);
    return data;
  }

  renderSummary(summary) {
    const avgEl = document.getElementById("kpi-avg-score");
    const deltaEl = document.getElementById("kpi-avg-delta");
    const moodEl = document.getElementById("kpi-dominant-mood");
    const streakEl = document.getElementById("kpi-streak");
    const totalEl = document.getElementById("kpi-totals");

    if (avgEl) avgEl.textContent = summary.avg_score !== null ? `${summary.avg_score}` : "—";
    if (deltaEl) {
      if (summary.delta_vs_prev === null) {
        deltaEl.textContent = "Baseline period";
      } else if (summary.delta_vs_prev >= 0) {
        deltaEl.textContent = `+${summary.delta_vs_prev} pts vs prior period`;
      } else {
        deltaEl.textContent = `${summary.delta_vs_prev} pts vs prior period`;
      }
    }
    if (moodEl) {
      moodEl.textContent = summary.dominant_mood
        ? summary.dominant_mood.charAt(0).toUpperCase() + summary.dominant_mood.slice(1)
        : "—";
    }
    if (streakEl) {
      streakEl.textContent = `${summary.checkin_streak}d`;
    }
    if (totalEl) {
      totalEl.textContent = `${summary.total_scans} scans · ${summary.total_journals} journal`;
    }
  }

  renderTrendChart(timeline) {
    const canvas = document.getElementById("chart-wellness-trend");
    if (!canvas || !window.Chart) return;
    if (this.trendChart) this.trendChart.destroy();

    const labels = timeline.map((t) => t.date.slice(5));
    const scores = timeline.map((t) => t.avg_score);
    const journalPoints = timeline.map((t) => (t.journal_count > 0 && t.avg_score !== null ? t.avg_score : null));

    this.trendChart = new window.Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Wellness Score",
            data: scores,
            borderColor: "#6b8e78",
            backgroundColor: "rgba(107, 142, 120, 0.16)",
            fill: true,
            tension: 0.36,
            spanGaps: true,
            pointRadius: 4,
            pointBackgroundColor: "#6b8e78",
          },
          {
            label: "Journaled Day",
            data: journalPoints,
            borderColor: "#c88a70",
            backgroundColor: "#c88a70",
            showLine: false,
            pointRadius: 6,
            pointStyle: "circle",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { min: 0, max: 100, grid: { color: "rgba(128,128,128,0.1)" } },
          x: { grid: { display: false } },
        },
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 10, usePointStyle: true } },
        },
      },
    });
  }

  renderDistributionChart(dist) {
    const canvas = document.getElementById("chart-mood-dist");
    if (!canvas || !window.Chart) return;
    if (this.distChart) this.distChart.destroy();

    const labels = dist.length ? dist.map((d) => d.mood) : ["No data yet"];
    const values = dist.length ? dist.map((d) => d.count) : [1];
    const colors = dist.length
      ? dist.map((d) => MOOD_COLORS[d.mood] || "#84a993")
      : ["rgba(128,128,128,0.2)"];

    this.distChart = new window.Chart(canvas, {
      type: "doughnut",
      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: colors,
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "66%",
        plugins: {
          legend: { position: "bottom", labels: { boxWidth: 10, usePointStyle: true } },
        },
      },
    });
  }

  renderRhythmChart(rhythm) {
    const canvas = document.getElementById("chart-tod-rhythm");
    if (!canvas || !window.Chart) return;
    if (this.rhythmChart) this.rhythmChart.destroy();

    this.rhythmChart = new window.Chart(canvas, {
      type: "bar",
      data: {
        labels: rhythm.map((r) => r.slot.charAt(0).toUpperCase() + r.slot.slice(1)),
        datasets: [
          {
            label: "Avg Wellness by Time of Day",
            data: rhythm.map((r) => r.avg_score || 0),
            backgroundColor: ["#84a993", "#6b8e78", "#7390a6", "#8c7fa8"],
            borderRadius: 10,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { min: 0, max: 100, grid: { color: "rgba(128,128,128,0.1)" } },
          x: { grid: { display: false } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  renderHeatmap(heatmap) {
    const grid = document.getElementById("wellness-heatmap");
    if (!grid) return;

    grid.innerHTML = heatmap
      .map((cell) => {
        let lvl = "";
        if (cell.avg_score !== null) {
          if (cell.avg_score >= 80) lvl = "lvl-4";
          else if (cell.avg_score >= 65) lvl = "lvl-3";
          else if (cell.avg_score >= 48) lvl = "lvl-2";
          else lvl = "lvl-1";
        }
        const journalCls = cell.journals > 0 ? "has-journal" : "";
        const title = `${formatNiceDate(cell.date)} — ${
          cell.avg_score !== null ? `Wellness ${cell.avg_score}/100` : "No mood scan"
        }${cell.journals > 0 ? ` · ${cell.journals} journal` : ""}`;
        return `<div class="heat-cell ${lvl} ${journalCls}" data-heat-date="${escapeHtml(
          cell.date
        )}" title="${escapeHtml(title)}"></div>`;
      })
      .join("");

    grid.querySelectorAll("[data-heat-date]").forEach((el) => {
      el.addEventListener("click", () => {
        const dt = el.getAttribute("data-heat-date");
        if (this.onSelectArchiveDay) this.onSelectArchiveDay(dt);
      });
    });
  }

  renderInsights(insights) {
    const list = document.getElementById("dashboard-insights-list");
    if (!list) return;
    list.innerHTML = (insights || [])
      .map((text) => `<div class="suggestion-item"><span>•</span><span>${escapeHtml(text)}</span></div>`)
      .join("");
  }
}
