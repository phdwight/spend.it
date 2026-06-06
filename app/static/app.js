/* spend.it — frontend logic */
(() => {
  "use strict";

  const API = {
    list: (params = "") => fetch(`/api/expenses${params}`).then(must2xx),
    create: (body) =>
      fetch("/api/expenses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(must2xx),
    remove: (id) =>
      fetch(`/api/expenses/${id}`, { method: "DELETE" }).then((r) => {
        if (!r.ok && r.status !== 204) throw new Error("Delete failed");
      }),
    summary: (period) =>
      fetch(`/api/reports/summary?period=${period}`).then(must2xx),
  };

  function must2xx(res) {
    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    return res.json();
  }

  // ---------- state ----------
  const state = {
    period: "daily",
    categoryChart: null,
    periodChart: null,
    lastSummary: null,
    selectedBucket: null,
  };

  // ---------- formatting ----------
  const currency = new Intl.NumberFormat(undefined, {
    style: "decimal",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const fmt = (n) => currency.format(n ?? 0);

  const palette = [
    "#38bdf8", "#a78bfa", "#f472b6", "#34d399",
    "#fbbf24", "#f87171", "#60a5fa", "#c084fc",
    "#4ade80", "#fb923c",
  ];

  // ---------- DOM helpers ----------
  const $ = (sel) => document.querySelector(sel);

  function setStatus(msg, kind = "") {
    const el = $("#form-status");
    el.textContent = msg;
    el.className = "form-status" + (kind ? ` is-${kind}` : "");
    if (msg) setTimeout(() => { if (el.textContent === msg) setStatus(""); }, 2500);
  }

  // ---------- form ----------
  // Holds the resized base64 data URL of the currently attached photo, or null.
  let pendingPhoto = null;

  // Resize an image File to fit within `maxEdge` px and re-encode as JPEG.
  // Keeps payloads small (~30–80 KB) so storage and transfer stay snappy.
  function resizeImageFile(file, maxEdge = 480, quality = 0.72) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("Could not read file"));
      reader.onload = () => {
        const img = new Image();
        img.onerror = () => reject(new Error("Could not decode image"));
        img.onload = () => {
          const ratio = Math.min(1, maxEdge / Math.max(img.width, img.height));
          const w = Math.max(1, Math.round(img.width * ratio));
          const h = Math.max(1, Math.round(img.height * ratio));
          const canvas = document.createElement("canvas");
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext("2d");
          ctx.drawImage(img, 0, 0, w, h);
          try {
            resolve(canvas.toDataURL("image/jpeg", quality));
          } catch (err) {
            reject(err);
          }
        };
        img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  function setPhotoStatus(msg, kind = "") {
    const el = $("#photo-status");
    if (!el) return;
    el.textContent = msg;
    el.className = "photo-status" + (kind ? ` is-${kind}` : "");
  }

  function clearPhoto() {
    pendingPhoto = null;
    const input = $("#photo-input");
    if (input) input.value = "";
    const preview = $("#photo-preview");
    const img = $("#photo-preview-img");
    if (img) img.removeAttribute("src");
    if (preview) preview.hidden = true;
    setPhotoStatus("");
  }

  function initPhotoInput() {
    const input = $("#photo-input");
    const preview = $("#photo-preview");
    const previewImg = $("#photo-preview-img");
    const clearBtn = $("#photo-clear");
    if (!input || !preview || !previewImg || !clearBtn) return;

    input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (!file.type.startsWith("image/")) {
        setPhotoStatus("Pick an image file.", "error");
        input.value = "";
        return;
      }
      try {
        setPhotoStatus("Resizing…");
        const dataUrl = await resizeImageFile(file);
        pendingPhoto = dataUrl;
        previewImg.src = dataUrl;
        preview.hidden = false;
        // Show approximate size of the encoded payload.
        const approxKb = Math.round((dataUrl.length * 0.75) / 1024);
        setPhotoStatus(`Attached (~${approxKb} KB)`);
      } catch (err) {
        console.error(err);
        clearPhoto();
        setPhotoStatus("Could not process image.", "error");
      }
    });

    clearBtn.addEventListener("click", clearPhoto);
  }

  function initForm() {
    const today = new Date().toISOString().slice(0, 10);
    $("#spent_at").value = today;
    $("#spent_at").max = today;

    initPhotoInput();

    $("#expense-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = e.currentTarget;
      const payload = {
        amount: parseFloat($("#amount").value),
        category: $("#category").value.trim(),
        note: $("#note").value.trim() || null,
        photo: pendingPhoto || null,
        spent_at: $("#spent_at").value || null,
      };

      if (!payload.amount || payload.amount <= 0 || !payload.category) {
        setStatus("Enter a positive amount and category.", "error");
        return;
      }

      try {
        await API.create(payload);
        form.reset();
        $("#spent_at").value = today;
        clearPhoto();
        setStatus("Saved.", "success");
        await refreshAll();
      } catch (err) {
        console.error(err);
        setStatus("Could not save. Try again.", "error");
      }
    });
  }

  // ---------- period toggle ----------
  // Labels are computed at call time so the chart titles always reflect the
  // *actual* current day / month / year (e.g. "By category \u2014 June 2026").
  function periodLabels() {
    const now = new Date();
    const longDate = now.toLocaleString(undefined, {
      month: "long",
      day: "numeric",
      year: "numeric",
    });
    const monthYear = now.toLocaleString(undefined, {
      month: "long",
      year: "numeric",
    });
    const year = String(now.getFullYear());
    return {
      daily: {
        period: "Daily totals",
        category: `By category \u2014 ${longDate}`,
        total: "Today's total",
      },
      monthly: {
        period: "Monthly totals",
        category: `By category \u2014 ${monthYear}`,
        total: `${monthYear} total`,
      },
      yearly: {
        period: "Yearly totals",
        category: `By category \u2014 ${year}`,
        total: `${year} total`,
      },
    };
  }

  function applyPeriodLabels() {
    const labels = periodLabels()[state.period];
    $("#period-title").textContent = labels.period;
  }

  function initPeriodToggle() {
    document.querySelectorAll(".chip[data-period]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        document.querySelectorAll(".chip[data-period]").forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
        state.period = btn.dataset.period;
        applyPeriodLabels();
        await refreshReport();
      });
    });
  }

  // ---------- expense list ----------
  function formatReceiptDate(iso) {
    // iso like "2026-06-06" -> "MON 06 JUN 2026"
    const d = new Date(`${iso}T00:00:00`);
    if (Number.isNaN(d.getTime())) return iso;
    const day = d.toLocaleString(undefined, { weekday: "short" }).toUpperCase();
    const dd = String(d.getDate()).padStart(2, "0");
    const mon = d.toLocaleString(undefined, { month: "short" }).toUpperCase();
    const yy = d.getFullYear();
    return `${day} ${dd} ${mon} ${yy}`;
  }

  function setReceiptHeaderDate() {
    const el = document.getElementById("receipt-date");
    if (!el) return;
    const today = new Date().toISOString().slice(0, 10);
    el.textContent = formatReceiptDate(today);
  }

  async function refreshList() {
    const items = await API.list("?limit=50");
    const list = $("#expense-list");
    list.innerHTML = "";
    $("#empty-state").hidden = items.length > 0;

    let subtotal = 0;
    for (const it of items) {
      subtotal += Number(it.amount) || 0;
      const li = document.createElement("li");
      li.className = "receipt__item";
      li.innerHTML = `
        <div class="receipt__date"></div>
        <div class="receipt__line">
          <span class="receipt__name"></span>
          <span class="receipt__dots" aria-hidden="true"></span>
          <span class="receipt__amount"></span>
        </div>
        <p class="receipt__note" hidden></p>
        <div class="receipt__photo" hidden>
          <a target="_blank" rel="noopener noreferrer">
            <img alt="Attached photo" />
          </a>
        </div>
        <button class="receipt__void" type="button" aria-label="Void this entry">[ Void ]</button>
      `;
      li.querySelector(".receipt__date").textContent = formatReceiptDate(it.spent_at);
      li.querySelector(".receipt__name").textContent = it.category;
      li.querySelector(".receipt__amount").textContent = fmt(it.amount);
      const noteEl = li.querySelector(".receipt__note");
      if (it.note) {
        noteEl.textContent = `— ${it.note}`;
        noteEl.hidden = false;
      }
      const photoWrap = li.querySelector(".receipt__photo");
      if (it.photo) {
        const link = photoWrap.querySelector("a");
        const img = photoWrap.querySelector("img");
        link.href = it.photo;
        img.src = it.photo;
        photoWrap.hidden = false;
      }
      li.querySelector("button").addEventListener("click", async () => {
        if (!confirm("Void this entry?")) return;
        try {
          await API.remove(it.id);
          await refreshAll();
        } catch (err) {
          console.error(err);
          setStatus("Delete failed.", "error");
        }
      });
      list.appendChild(li);
    }

    const countEl = document.getElementById("receipt-count");
    const totalEl = document.getElementById("receipt-subtotal");
    if (countEl) countEl.textContent = String(items.length);
    if (totalEl) totalEl.textContent = fmt(subtotal);
  }

  // ---------- charts ----------
  function renderCategoryChart(byCategory) {
    const ctx = document.getElementById("chart-category");
    const labels = byCategory.map((r) => r.category);
    const data = byCategory.map((r) => r.total);

    const cfg = {
      type: "doughnut",
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: labels.map((_, i) => palette[i % palette.length]),
          borderColor: "rgba(15,23,42,0.7)",
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { color: "#cbd5e1", boxWidth: 12 } },
          tooltip: { callbacks: { label: (c) => `${c.label}: ${fmt(c.parsed)}` } },
        },
        cutout: "60%",
      },
    };

    if (state.categoryChart) state.categoryChart.destroy();
    state.categoryChart = new Chart(ctx, cfg);
  }

  // Convert a flat list of {period, category, total} into stacked datasets
  // keyed by category, aligned to a single ordered list of period buckets.
  function buildStackedDatasets(byPeriodCategory) {
    const buckets = [];
    const seenBucket = new Set();
    const cats = [];
    const seenCat = new Set();

    for (const row of byPeriodCategory) {
      if (!seenBucket.has(row.period)) { seenBucket.add(row.period); buckets.push(row.period); }
      if (!seenCat.has(row.category)) { seenCat.add(row.category); cats.push(row.category); }
    }
    buckets.sort();

    // Use the doughnut-derived order so colors line up with the category card.
    const catTotals = new Map();
    for (const row of byPeriodCategory) {
      catTotals.set(row.category, (catTotals.get(row.category) || 0) + row.total);
    }
    cats.sort((a, b) => (catTotals.get(b) || 0) - (catTotals.get(a) || 0));

    const lookup = new Map(); // `${bucket}|${cat}` -> total
    for (const row of byPeriodCategory) {
      lookup.set(`${row.period}|${row.category}`, row.total);
    }

    const datasets = cats.map((cat, i) => ({
      label: cat,
      data: buckets.map((b) => lookup.get(`${b}|${cat}`) || 0),
      backgroundColor: palette[i % palette.length],
      borderWidth: 0,
      borderRadius: 4,
      stack: "spend",
    }));

    return { buckets, datasets };
  }

  function renderPeriodChart(byPeriodCategory) {
    const ctx = document.getElementById("chart-period");
    const { buckets, datasets } = buildStackedDatasets(byPeriodCategory);

    const cfg = {
      type: "bar",
      data: { labels: buckets, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        // Treat hovers and clicks as a vertical column so any click within a
        // bucket (even on whitespace above the stack) selects that bucket.
        interaction: { mode: "index", intersect: false, axis: "x" },
        onClick: (evt, _elements, chart) => {
          // Use index mode so the click resolves to the column closest to the
          // cursor instead of requiring a pixel-perfect hit on a bar.
          const hits = chart.getElementsAtEventForMode(
            evt,
            "index",
            { intersect: false, axis: "x" },
            false,
          );
          if (!hits.length) return;
          const idx = hits[0].index;
          const bucket = buckets[idx];
          if (bucket == null) return;
          state.selectedBucket = state.selectedBucket === bucket ? null : bucket;
          renderFromState();
        },
        plugins: {
          legend: { position: "bottom", labels: { color: "#cbd5e1", boxWidth: 12 } },
          tooltip: {
            callbacks: {
              label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y)}`,
              footer: (items) => {
                const total = items.reduce((acc, it) => acc + (it.parsed.y || 0), 0);
                return `Total: ${fmt(total)}`;
              },
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            ticks: {
              color: (ctx2) =>
                ctx2.tick && ctx2.tick.label === state.selectedBucket ? "#f8fafc" : "#94a3b8",
              font: (ctx2) =>
                ctx2.tick && ctx2.tick.label === state.selectedBucket
                  ? { weight: "700" }
                  : { weight: "400" },
            },
            grid: { color: "rgba(148,163,184,0.08)" },
          },
          y: {
            stacked: true,
            ticks: { color: "#94a3b8", callback: (v) => fmt(v) },
            grid: { color: "rgba(148,163,184,0.08)" },
            beginAtZero: true,
          },
        },
      },
    };

    if (state.periodChart) state.periodChart.destroy();
    state.periodChart = new Chart(ctx, cfg);
  }

  // Compute category breakdown for a single bucket from the stacked dataset.
  function categoriesForBucket(byPeriodCategory, bucket) {
    return byPeriodCategory
      .filter((r) => r.period === bucket)
      .map((r) => ({ category: r.category, total: r.total }))
      .sort((a, b) => b.total - a.total);
  }

  function bucketLabel(bucket) {
    if (state.period === "daily") return bucket;
    if (state.period === "monthly") {
      const [y, m] = bucket.split("-");
      const d = new Date(Number(y), Number(m) - 1, 1);
      return d.toLocaleString(undefined, { month: "long", year: "numeric" });
    }
    return bucket; // yearly
  }

  // Re-paint the category card (doughnut + total + label) from current state.
  function renderFromState() {
    const r = state.lastSummary;
    if (!r) return;

    let categories;
    let total;
    let label;
    let chartTitle;

    if (state.selectedBucket) {
      categories = categoriesForBucket(r.by_period_category, state.selectedBucket);
      total = categories.reduce((a, c) => a + c.total, 0);
      const human = bucketLabel(state.selectedBucket);
      label = `${human} total`;
      chartTitle = `By category — ${human}`;
    } else {
      const labels = periodLabels()[state.period];
      categories = r.by_category;
      total = r.grand_total;
      label = labels.total;
      chartTitle = labels.category;
    }

    $("#grand-total").textContent = fmt(total);
    $("#grand-total-label").textContent = label;
    $("#category-title").textContent = chartTitle;
    $("#top-category").textContent = categories[0] ? categories[0].category : "—";
    $("#entries-count").textContent = r.by_period.length || "0";
    renderCategoryChart(categories);

    // Re-render bar chart so the active tick styling refreshes.
    if (state.periodChart) state.periodChart.update("none");
  }

  async function refreshReport() {
    const r = await API.summary(state.period);
    state.lastSummary = r;
    state.selectedBucket = null;
    renderPeriodChart(r.by_period_category);
    renderFromState();
  }

  async function refreshAll() {
    await Promise.all([refreshReport(), refreshList()]);
  }

  // ---------- service worker ----------
  function registerSW() {
    if (!("serviceWorker" in navigator)) return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch((err) => {
        console.warn("Service worker registration failed:", err);
      });
    });
  }

  // ---------- bootstrap ----------
  document.addEventListener("DOMContentLoaded", async () => {
    initForm();
    initPeriodToggle();
    setReceiptHeaderDate();
    registerSW();
    try {
      await refreshAll();
    } catch (err) {
      console.error(err);
      setStatus("Could not load data.", "error");
    }
  });
})();
