const apiPrefix = "/api/v1";
const ADMIN_TOKEN_KEY = "chatbot_admin_token";

function getAdminToken() {
  return sessionStorage.getItem(ADMIN_TOKEN_KEY) || "";
}

function setAdminToken(token) {
  sessionStorage.setItem(ADMIN_TOKEN_KEY, token.trim());
}

function clearAdminToken() {
  sessionStorage.removeItem(ADMIN_TOKEN_KEY);
}

function showToast(toastEl, text, isError = false) {
  if (!toastEl) return;
  toastEl.textContent = text;
  toastEl.classList.remove("hidden", "toast-error");
  if (isError) {
    toastEl.classList.add("toast-error");
  }
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => {
    toastEl.classList.add("hidden");
  }, 3200);
}

function statusChip(status) {
  const safe = String(status).toLowerCase().replace(/[^a-z0-9_-]/g, "");
  return `<span class="status-chip status-${safe}">${status}</span>`;
}

async function fetchJson(url, options = {}) {
  const fetchOptions = { ...options };
  if (!("credentials" in fetchOptions)) {
    fetchOptions.credentials = "same-origin";
  }
  const response = await fetch(url, fetchOptions);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const message =
      data && data.message
        ? data.message
        : data && data.detail
          ? typeof data.detail === "string"
            ? data.detail
            : data.detail.message || JSON.stringify(data.detail)
          : `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return data;
}

async function fetchAdminJson(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getAdminToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetchJson(url, { ...options, headers });
}
