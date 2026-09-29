const STORAGE_KEY = "pasfoto_settings";
const MIN_SIZE = 50;
const MAX_SIZE = 4000;
const FETCH_TIMEOUT_MS = 120000;

const form = document.getElementById("form");
const photoInput = document.getElementById("photo");
const widthInput = document.getElementById("outputWidth");
const heightInput = document.getElementById("outputHeight");
const colorPicker = document.getElementById("colorPicker");
const bgColorInput = document.getElementById("bgColor");
const submitBtn = document.getElementById("submitBtn");
const statusEl = document.getElementById("status");
const progressEl = document.getElementById("progress");
const progressText = document.getElementById("progressText");
const progressElapsed = document.getElementById("progressElapsed");
const cropSection = document.getElementById("cropSection");
const cropViewport = document.getElementById("cropViewport");
const cropStage = document.getElementById("cropStage");
const cutoutImg = document.getElementById("cutoutImg");
const zoomSlider = document.getElementById("zoomSlider");
const zoomLabel = document.getElementById("zoomLabel");
const resetCropBtn = document.getElementById("resetCropBtn");
const downloadBtn = document.getElementById("downloadBtn");
const previewEl = document.getElementById("preview");
const resultImg = document.getElementById("resultImg");
const downloadLink = document.getElementById("downloadLink");

let resultUrl = null;
let cutoutBlob = null;
let cutoutUrl = null;
let progressTimer = null;
let progressStartedAt = 0;

/** Normalized pan offsets in [-1, 1], matching server compose. */
let offsetX = 0;
let offsetY = 0;
let zoom = 1;

let dragging = false;
let dragStartX = 0;
let dragStartY = 0;
let dragOriginOx = 0;
let dragOriginOy = 0;

function showStatus(message, type = "info") {
  statusEl.hidden = false;
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
}

function hideStatus() {
  statusEl.hidden = true;
}

function startProgress(stageText) {
  progressEl.hidden = false;
  progressText.textContent = stageText || "Memproses…";
  progressStartedAt = Date.now();
  progressElapsed.textContent = "0 dtk";
  if (progressTimer) clearInterval(progressTimer);
  progressTimer = setInterval(() => {
    const sec = Math.floor((Date.now() - progressStartedAt) / 1000);
    progressElapsed.textContent = `${sec} dtk`;
    if (sec < 15) {
      progressText.textContent = "Menghapus latar (AI)…";
    } else if (sec < 40) {
      progressText.textContent = "Masih memproses — sabar ya…";
    } else {
      progressText.textContent = "Hampir selesai / VPS sedang sibuk…";
    }
  }, 500);
}

function stopProgress() {
  progressEl.hidden = true;
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
}

function loadSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const { width, height, bg } = JSON.parse(raw);
    if (width) widthInput.value = width;
    if (height) heightInput.value = height;
    if (bg && /^#[0-9A-Fa-f]{6}$/.test(bg)) {
      bgColorInput.value = bg.toUpperCase();
      colorPicker.value = bg;
    }
  } catch {
    /* ignore */
  }
}

function saveSettings() {
  const width = parseInt(widthInput.value, 10);
  const height = parseInt(heightInput.value, 10);
  const bg = bgColorInput.value.trim();
  if (!Number.isFinite(width) || !Number.isFinite(height)) return;
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ width, height, bg })
  );
}

function validateSize() {
  const width = parseInt(widthInput.value, 10);
  const height = parseInt(heightInput.value, 10);
  if (!Number.isFinite(width) || !Number.isFinite(height)) {
    return "Lebar dan tinggi harus angka.";
  }
  if (width < MIN_SIZE || width > MAX_SIZE) {
    return `Lebar harus ${MIN_SIZE}–${MAX_SIZE} px.`;
  }
  if (height < MIN_SIZE || height > MAX_SIZE) {
    return `Tinggi harus ${MIN_SIZE}–${MAX_SIZE} px.`;
  }
  return null;
}

function syncColorFromPicker() {
  bgColorInput.value = colorPicker.value.toUpperCase();
  saveSettings();
  updateCropBg();
}

function syncPickerFromText() {
  const hex = bgColorInput.value.trim();
  if (/^#?[0-9A-Fa-f]{6}$/.test(hex)) {
    const normalized = hex.startsWith("#") ? hex : `#${hex}`;
    colorPicker.value = normalized;
    bgColorInput.value = normalized.toUpperCase();
    saveSettings();
    updateCropBg();
  }
}

function setBgColor(hex) {
  const normalized = hex.toUpperCase();
  bgColorInput.value = normalized;
  colorPicker.value = normalized;
  saveSettings();
  updateCropBg();
}

function updateCropBg() {
  cropViewport.style.background = bgColorInput.value.trim() || "#FFFFFF";
}

function setViewportAspect() {
  const w = parseInt(widthInput.value, 10) || 300;
  const h = parseInt(heightInput.value, 10) || 400;
  cropViewport.style.aspectRatio = `${w} / ${h}`;
}

function applyCropTransform() {
  // Visual approx of server pan/zoom: scale from center + translate
  const maxPan = 40; // % of viewport for full offset ±1
  const tx = offsetX * maxPan;
  const ty = offsetY * maxPan;
  cutoutImg.style.transform = `translate(${tx}%, ${ty}%) scale(${zoom})`;
  zoomLabel.textContent = `${zoom.toFixed(2)}×`;
  zoomSlider.value = String(zoom);
}

function resetCrop() {
  offsetX = 0;
  offsetY = 0;
  zoom = 1;
  applyCropTransform();
}

function revokeCutout() {
  if (cutoutUrl) {
    URL.revokeObjectURL(cutoutUrl);
    cutoutUrl = null;
  }
  cutoutBlob = null;
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function friendlyError(err, resStatus) {
  if (err && err.name === "AbortError") {
    return "Waktu habis. Proses AI terlalu lama — coba foto lebih kecil atau ulangi.";
  }
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    return "Tidak ada koneksi internet.";
  }
  const msg = (err && err.message) || "";
  if (resStatus === 429 || /terlalu banyak|sedang memproses/i.test(msg)) {
    return msg || "Terlalu banyak permintaan atau server sibuk. Coba lagi sebentar.";
  }
  if (/Failed to fetch|NetworkError|network/i.test(msg)) {
    return "Gagal terhubung ke server. Periksa koneksi lalu coba lagi.";
  }
  return msg || "Gagal memproses foto.";
}

async function parseErrorDetail(res) {
  try {
    const err = await res.json();
    const detail = err.detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
    }
    if (typeof detail === "string") return detail;
    return `Error ${res.status}`;
  } catch {
    return `Error ${res.status}`;
  }
}

colorPicker.addEventListener("input", syncColorFromPicker);
bgColorInput.addEventListener("input", syncPickerFromText);

document.querySelectorAll(".preset-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    widthInput.value = btn.dataset.w;
    heightInput.value = btn.dataset.h;
    saveSettings();
    setViewportAspect();
  });
});

document.querySelectorAll(".color-preset").forEach((btn) => {
  btn.addEventListener("click", () => setBgColor(btn.dataset.color));
});

widthInput.addEventListener("change", () => {
  saveSettings();
  setViewportAspect();
});
heightInput.addEventListener("change", () => {
  saveSettings();
  setViewportAspect();
});

zoomSlider.addEventListener("input", () => {
  zoom = parseFloat(zoomSlider.value) || 1;
  applyCropTransform();
});

resetCropBtn.addEventListener("click", resetCrop);

function onPointerDown(e) {
  if (!cutoutBlob) return;
  dragging = true;
  const point = e.touches ? e.touches[0] : e;
  dragStartX = point.clientX;
  dragStartY = point.clientY;
  dragOriginOx = offsetX;
  dragOriginOy = offsetY;
  cropViewport.classList.add("dragging");
  e.preventDefault();
}

function onPointerMove(e) {
  if (!dragging) return;
  const point = e.touches ? e.touches[0] : e;
  const rect = cropViewport.getBoundingClientRect();
  const dx = point.clientX - dragStartX;
  const dy = point.clientY - dragStartY;
  // Map drag pixels to offset ±1 (drag ~half viewport = full offset)
  const nextX = dragOriginOx + dx / (rect.width * 0.45);
  const nextY = dragOriginOy + dy / (rect.height * 0.45);
  offsetX = Math.max(-1, Math.min(1, nextX));
  offsetY = Math.max(-1, Math.min(1, nextY));
  applyCropTransform();
  e.preventDefault();
}

function onPointerUp() {
  dragging = false;
  cropViewport.classList.remove("dragging");
}

cropViewport.addEventListener("mousedown", onPointerDown);
window.addEventListener("mousemove", onPointerMove);
window.addEventListener("mouseup", onPointerUp);
cropViewport.addEventListener("touchstart", onPointerDown, { passive: false });
window.addEventListener("touchmove", onPointerMove, { passive: false });
window.addEventListener("touchend", onPointerUp);

loadSettings();
setViewportAspect();
updateCropBg();

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideStatus();
  previewEl.hidden = true;
  cropSection.hidden = true;
  revokeCutout();

  const sizeError = validateSize();
  if (sizeError) {
    showStatus(sizeError, "error");
    return;
  }

  const file = photoInput.files[0];
  if (!file) {
    showStatus("Pilih foto terlebih dahulu.", "error");
    return;
  }

  const ext = file.name.split(".").pop()?.toLowerCase();
  const allowedExt = ["jpg", "jpeg", "png"];
  const allowedTypes = ["image/jpeg", "image/png"];
  const extOk = allowedExt.includes(ext);
  const typeOk = !file.type || allowedTypes.includes(file.type);
  if (!extOk || !typeOk) {
    showStatus("Hanya file JPG/JPEG atau PNG yang diizinkan.", "error");
    return;
  }

  saveSettings();
  const formData = new FormData();
  formData.append("photo", file);

  submitBtn.disabled = true;
  startProgress("Mengunggah & menghapus latar…");

  let resStatus = 0;
  try {
    const res = await fetchWithTimeout(
      "/api/cutout",
      { method: "POST", body: formData },
      FETCH_TIMEOUT_MS
    );
    resStatus = res.status;

    if (!res.ok) {
      const detail = await parseErrorDetail(res);
      throw new Error(detail);
    }

    cutoutBlob = await res.blob();
    if (cutoutUrl) URL.revokeObjectURL(cutoutUrl);
    cutoutUrl = URL.createObjectURL(cutoutBlob);
    cutoutImg.src = cutoutUrl;

    resetCrop();
    setViewportAspect();
    updateCropBg();
    cropSection.hidden = false;
    hideStatus();
    showStatus("Latar dihapus. Sesuaikan posisi lalu unduh JPG.", "info");
  } catch (err) {
    showStatus(friendlyError(err, resStatus), "error");
  } finally {
    stopProgress();
    submitBtn.disabled = false;
  }
});

downloadBtn.addEventListener("click", async () => {
  if (!cutoutBlob) {
    showStatus("Belum ada hasil cutout. Proses foto dulu.", "error");
    return;
  }

  const sizeError = validateSize();
  if (sizeError) {
    showStatus(sizeError, "error");
    return;
  }

  const width = parseInt(widthInput.value, 10);
  const height = parseInt(heightInput.value, 10);
  saveSettings();

  const formData = new FormData();
  formData.append("cutout", cutoutBlob, "cutout.png");
  formData.append("bg_color", bgColorInput.value.trim() || "#FFFFFF");
  formData.append("width", String(width));
  formData.append("height", String(height));
  formData.append("offset_x", String(offsetX));
  formData.append("offset_y", String(offsetY));
  formData.append("zoom", String(zoom));

  downloadBtn.disabled = true;
  resetCropBtn.disabled = true;
  submitBtn.disabled = true;
  startProgress("Menyusun JPG akhir…");
  hideStatus();

  let resStatus = 0;
  try {
    const res = await fetchWithTimeout(
      "/api/compose",
      { method: "POST", body: formData },
      60000
    );
    resStatus = res.status;

    if (!res.ok) {
      const detail = await parseErrorDetail(res);
      throw new Error(detail);
    }

    const blob = await res.blob();
    if (resultUrl) URL.revokeObjectURL(resultUrl);
    resultUrl = URL.createObjectURL(blob);

    resultImg.src = resultUrl;
    resultImg.style.maxWidth = `${Math.min(width, 420)}px`;
    downloadLink.href = resultUrl;
    downloadLink.download =
      res.headers.get("Content-Disposition")?.match(/filename="(.+)"/)?.[1] ||
      `pasfoto-${width}x${height}.jpg`;

    previewEl.hidden = false;
    showStatus("Selesai! Silakan unduh JPG.", "info");

    // Auto-trigger download
    const a = document.createElement("a");
    a.href = resultUrl;
    a.download = downloadLink.download;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch (err) {
    showStatus(friendlyError(err, resStatus), "error");
  } finally {
    stopProgress();
    downloadBtn.disabled = false;
    resetCropBtn.disabled = false;
    submitBtn.disabled = false;
  }
});
