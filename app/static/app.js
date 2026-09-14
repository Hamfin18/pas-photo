const STORAGE_KEY = "pasfoto_settings";
const MIN_SIZE = 50;
const MAX_SIZE = 4000;

const form = document.getElementById("form");
const photoInput = document.getElementById("photo");
const widthInput = document.getElementById("outputWidth");
const heightInput = document.getElementById("outputHeight");
const colorPicker = document.getElementById("colorPicker");
const bgColorInput = document.getElementById("bgColor");
const submitBtn = document.getElementById("submitBtn");
const statusEl = document.getElementById("status");
const previewEl = document.getElementById("preview");
const resultImg = document.getElementById("resultImg");
const downloadLink = document.getElementById("downloadLink");

let resultUrl = null;

function showStatus(message, type = "info") {
  statusEl.hidden = false;
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
}

function hideStatus() {
  statusEl.hidden = true;
}

function loadSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const { width, height } = JSON.parse(raw);
    if (width) widthInput.value = width;
    if (height) heightInput.value = height;
  } catch {
    /* ignore corrupt storage */
  }
}

function saveSettings() {
  const width = parseInt(widthInput.value, 10);
  const height = parseInt(heightInput.value, 10);
  if (!Number.isFinite(width) || !Number.isFinite(height)) return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ width, height }));
}

function validateSize() {
  const width = parseInt(widthInput.value, 10);
  const height = parseInt(heightInput.value, 10);

  if (!Number.isFinite(width) || !Number.isFinite(height)) {
    return "Width and height must be numbers.";
  }
  if (width < MIN_SIZE || width > MAX_SIZE) {
    return `Width must be ${MIN_SIZE}–${MAX_SIZE} px.`;
  }
  if (height < MIN_SIZE || height > MAX_SIZE) {
    return `Height must be ${MIN_SIZE}–${MAX_SIZE} px.`;
  }
  return null;
}

function syncColorFromPicker() {
  bgColorInput.value = colorPicker.value.toUpperCase();
}

function syncPickerFromText() {
  const hex = bgColorInput.value.trim();
  if (/^#?[0-9A-Fa-f]{6}$/.test(hex)) {
    colorPicker.value = hex.startsWith("#") ? hex : `#${hex}`;
  }
}

colorPicker.addEventListener("input", syncColorFromPicker);
bgColorInput.addEventListener("input", syncPickerFromText);

document.querySelectorAll(".preset-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    widthInput.value = btn.dataset.w;
    heightInput.value = btn.dataset.h;
    saveSettings();
  });
});

widthInput.addEventListener("change", saveSettings);
heightInput.addEventListener("change", saveSettings);

loadSettings();

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideStatus();
  previewEl.hidden = true;

  const sizeError = validateSize();
  if (sizeError) {
    showStatus(sizeError, "error");
    return;
  }

  const width = parseInt(widthInput.value, 10);
  const height = parseInt(heightInput.value, 10);
  saveSettings();

  const file = photoInput.files[0];
  if (!file) {
    showStatus("Please choose a photo first.", "error");
    return;
  }

  const ext = file.name.split(".").pop()?.toLowerCase();
  const allowedExt = ["jpg", "jpeg", "png"];
  const allowedTypes = ["image/jpeg", "image/png"];
  const extOk = allowedExt.includes(ext);
  const typeOk = !file.type || allowedTypes.includes(file.type);
  if (!extOk || !typeOk) {
    showStatus("Only JPG/JPEG or PNG files are allowed.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("photo", file);
  formData.append("bg_color", bgColorInput.value.trim() || "#FFFFFF");
  formData.append("width", String(width));
  formData.append("height", String(height));

  submitBtn.disabled = true;
  showStatus("Processing… background removal may take a few seconds.", "info");

  try {
    const res = await fetch("/api/process", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = err.detail;
      const message = Array.isArray(detail)
        ? detail.map((d) => d.msg).join(", ")
        : detail || `Error ${res.status}`;
      throw new Error(message);
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
    hideStatus();
  } catch (err) {
    showStatus(err.message || "Failed to process photo.", "error");
  } finally {
    submitBtn.disabled = false;
  }
});
