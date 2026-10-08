const configuredRoot =
  import.meta.env.VITE_API_ROOT ||
  "https://freshfusion-backend-production.up.railway.app";
export const API_ROOT = configuredRoot.replace(/\/$/, "");
export const API = `${API_ROOT}/api/v1`;

async function json(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    if (!res.ok) {
      const body = await res.text();
      let detail;
      try {
        detail = JSON.parse(body).detail;
      } catch {
        /* HTTP text response */
      }
      throw new Error(
        typeof detail === "string"
          ? detail
          : `HTTP ${res.status}: ${body.slice(0, 240)}`,
      );
    }
    return res.status === 204 ? null : res.json();
  } finally {
    clearTimeout(timer);
  }
}

export const health = () => json(`${API}/health`);
export const createSample = (fruit_type = "Auto") =>
  json(`${API}/samples`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fruit_type }),
  });
export const listSamples = () => json(`${API}/samples?limit=200`);
export const assetUrl = (path) => (path ? new URL(path, API_ROOT).href : null);
export const bundle = async (id) => {
  const result = await json(`${API}/samples/${encodeURIComponent(id)}/bundle`);
  result.images = result.images.map((image) => ({
    ...image,
    url: assetUrl(image.url),
    analysis: {
      ...image.analysis,
      artifacts: Object.fromEntries(
        Object.entries(image.analysis?.artifacts || {}).map(([key, path]) => [
          key,
          assetUrl(path),
        ]),
      ),
    },
  }));
  return result;
};
export const investigation = (id) =>
  json(`${API}/samples/${encodeURIComponent(id)}/investigation`);
export const askInspectionAssistant = (id, question) =>
  json(`${API}/samples/${encodeURIComponent(id)}/assistant/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
export const explainInvestigation = (id) =>
  json(`${API}/samples/${encodeURIComponent(id)}/investigation/explain`, {
    method: "POST",
  });
export const ollamaHealth = () => json(`${API}/ai/ollama/health`);
export const activeSample = () => json(`${API}/samples/active`);
export const activateSample = (id) =>
  json(`${API}/samples/${encodeURIComponent(id)}/active`, { method: "PUT" });
export const inspectionProfile = (id) =>
  json(`${API}/samples/${encodeURIComponent(id)}/profile`);
export const updateInspectionProfile = (id, payload) =>
  json(`${API}/samples/${encodeURIComponent(id)}/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const inspectionEvents = (id) =>
  json(`${API}/samples/${encodeURIComponent(id)}/events?limit=100`);
export const validationSummary = () => json(`${API}/datasets/validation`);
export const verifyAssessment = (id, payload) =>
  json(`${API}/samples/${encodeURIComponent(id)}/verification`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const fuse = (id) =>
  json(`${API}/samples/${id}/fusion`, { method: "POST" });
export const pushReading = (payload) =>
  json(`${API}/sensors/readings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
export const captureSensorBaseline = (sampleId) =>
  json(`${API}/sensors/${encodeURIComponent(sampleId)}/baseline/from-latest`, {
    method: "POST",
  });
export const datasetRegistry = (fruit) =>
  json(
    `${API}/datasets/registry${fruit ? `?fruit_type=${encodeURIComponent(fruit)}` : ""}`,
  );
export const referenceStatus = () => json(`${API}/datasets/reference-status`);

function imageForm(sampleId, angle, truth, file) {
  const fd = new FormData();
  fd.append("sample_id", sampleId);
  fd.append("angle", angle);
  if (truth) fd.append("ground_truth", truth);
  fd.append("file", file, file.name || `frame-${Date.now()}.jpg`);
  return fd;
}

export const uploadImage = (sampleId, angle, truth, file) =>
  json(`${API}/images/upload`, {
    method: "POST",
    body: imageForm(sampleId, angle, truth, file),
  });

export const uploadStreamFrame = (sampleId, view, truth, file) => {
  const fd = imageForm(sampleId, `live-${view}`, truth, file);
  fd.append("view", view);
  return json(`${API}/images/stream-frame`, { method: "POST", body: fd });
};

export const context = (fruit, lat, lon) =>
  json(
    `${API}/external/context?fruit_type=${encodeURIComponent(fruit)}${lat != null ? `&lat=${lat}&lon=${lon}` : ""}`,
  );

export const wsUrl = (id) => {
  const base = new URL(API_ROOT, window.location.origin);
  const protocol = base.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${base.host}/ws/live/${id}`;
};
