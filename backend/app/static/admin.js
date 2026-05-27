const loginScreen = document.getElementById("loginScreen");
const adminPanel = document.getElementById("adminPanel");
const adminUsernameInput = document.getElementById("adminUsernameInput");
const adminPasswordInput = document.getElementById("adminPasswordInput");
const loginBtn = document.getElementById("loginBtn");
const logoutBtn = document.getElementById("logoutBtn");
const systemInfoEl = document.getElementById("systemInfo");
const llmWarningEl = document.getElementById("llmWarning");

const uploadForm = document.getElementById("uploadForm");
const fileInput = document.getElementById("fileInput");
const uploadResult = document.getElementById("uploadResult");
const docsTable = document.getElementById("docsTable");
const refreshDocsBtn = document.getElementById("refreshDocsBtn");
const tasksTable = document.getElementById("tasksTable");
const refreshTasksBtn = document.getElementById("refreshTasksBtn");

const llmTable = document.getElementById("llmTable");
const refreshLlmBtn = document.getElementById("refreshLlmBtn");
const llmForm = document.getElementById("llmForm");
const llmIdInput = document.getElementById("llmId");
const llmNameInput = document.getElementById("llmName");
const llmProviderInput = document.getElementById("llmProvider");
const llmModelInput = document.getElementById("llmModel");
const llmRefreshModelsBtn = document.getElementById("llmRefreshModelsBtn");
const llmModelsHint = document.getElementById("llmModelsHint");
const llmBaseUrlInput = document.getElementById("llmBaseUrl");
const llmApiKeyInput = document.getElementById("llmApiKey");
const llmEnabledInput = document.getElementById("llmEnabled");
const llmActivateInput = document.getElementById("llmActivate");
const llmFormResetBtn = document.getElementById("llmFormResetBtn");
const llmFormResult = document.getElementById("llmFormResult");

const promptForm = document.getElementById("promptForm");
const systemInstructionInput = document.getElementById("systemInstructionInput");
const promptMeta = document.getElementById("promptMeta");
const promptFormResult = document.getElementById("promptFormResult");
const resetPromptBtn = document.getElementById("resetPromptBtn");

const toast = document.getElementById("toast");

let statusPollTimer = null;
let lastDocsSnapshot = "";
let lastTasksSnapshot = "";
/** @type {Record<string, object>} */
let llmProviderSpecs = {};
let llmModelsAutoLoadTimer = null;
let llmModelsLoading = false;

/** Offline fallback — mirrors backend llm_provider_registry.py */
const LLM_PROVIDER_FALLBACKS = [
  {
    id: "openai_compatible",
    label: "OpenAI-compatible",
    requires_base_url: true,
    requires_api_key: false,
    api_key_optional: true,
    base_url_placeholder: "https://api.openai.com/v1 · http://localhost:11434/v1 (Ollama)",
    api_key_placeholder: "API key (если требуется провайдером)",
    models_source: "remote",
    description: "OpenAI API, Ollama, LM Studio, OpenRouter и другие совместимые сервисы",
  },
  {
    id: "gigachat",
    label: "GigaChat",
    requires_base_url: false,
    requires_api_key: true,
    api_key_optional: false,
    base_url_placeholder: "Можно оставить пустым — используется адрес по умолчанию",
    api_key_placeholder: "Authorization Basic ... из кабинета Sber",
    models_source: "remote",
    description: "GigaChat API (OAuth, токен обновляется автоматически)",
  },
  {
    id: "rule_based",
    label: "rule_based (dev)",
    requires_base_url: false,
    requires_api_key: false,
    api_key_optional: true,
    base_url_placeholder: "",
    api_key_placeholder: "",
    models_source: "static",
    description: "Локальная заглушка без внешней нейросети",
  },
];

function getCurrentProviderSpec() {
  return llmProviderSpecs[llmProviderInput.value] || null;
}

function providerCredentialsReady(spec) {
  if (!spec) return false;
  if (spec.models_source === "static") return true;
  if (spec.requires_base_url && !llmBaseUrlInput.value.trim()) return false;
  if (spec.requires_api_key && !llmApiKeyInput.value.trim()) return false;
  return true;
}

function setProviderValue(providerId) {
  if (!providerId) return false;
  const exists = Array.from(llmProviderInput.options).some((option) => option.value === providerId);
  if (exists) {
    llmProviderInput.value = providerId;
    return true;
  }
  if (llmProviderInput.options.length) {
    llmProviderInput.value = llmProviderInput.options[0].value;
    return true;
  }
  return false;
}

function renderProviderOptions(items, preferredId = "") {
  const previous = preferredId || llmProviderInput.value;
  llmProviderSpecs = {};
  llmProviderInput.innerHTML = "";
  items.forEach((spec) => {
    llmProviderSpecs[spec.id] = spec;
    const option = document.createElement("option");
    option.value = spec.id;
    option.textContent = spec.label;
    llmProviderInput.appendChild(option);
  });
  setProviderValue(previous || items[0]?.id || "");
  updateProviderFormHints();
}

function updateProviderFormHints() {
  const spec = getCurrentProviderSpec();
  if (!spec || !llmModelsHint) return;
  llmBaseUrlInput.placeholder = spec.base_url_placeholder || "";
  llmApiKeyInput.placeholder = spec.api_key_placeholder || "";
  const credParts = [];
  if (spec.requires_base_url) credParts.push("Base URL");
  if (spec.requires_api_key) credParts.push("API key");
  const credText = credParts.length ? credParts.join(" и ") : "дополнительные поля не нужны";
  if (spec.models_source === "static") {
    llmModelsHint.textContent = `${spec.description}. Модель подставится автоматически.`;
    return;
  }
  llmModelsHint.textContent = `Сначала выберите провайдера и укажите ${credText}, затем нажмите «Загрузить модели» или дождитесь автозагрузки. ${spec.description}`;
}

async function loadLlmProviderSpecs() {
  const previous = llmProviderInput.value;
  try {
    const data = await fetchAdminJson(`${apiPrefix}/admin/llm/providers`);
    const items = data.items?.length ? data.items : LLM_PROVIDER_FALLBACKS;
    renderProviderOptions(items, previous);
  } catch (error) {
    renderProviderOptions(LLM_PROVIDER_FALLBACKS, previous);
    showToast(toast, `Провайдеры: использован локальный каталог (${error.message})`, true);
  }
}

function scheduleAutoLoadModels(selectedModel = "") {
  if (llmModelsAutoLoadTimer) {
    clearTimeout(llmModelsAutoLoadTimer);
  }
  llmModelsAutoLoadTimer = setTimeout(() => {
    const spec = getCurrentProviderSpec();
    const integrationId = llmIdInput.value.trim();
    if (!spec) return;
    if (spec.models_source === "static") {
      refreshLlmModels(selectedModel || (spec.id === "rule_based" ? "rule-based-llm" : ""));
      return;
    }
    if (integrationId || providerCredentialsReady(spec)) {
      refreshLlmModels(selectedModel);
    }
  }, 400);
}

function showAdminPanel() {
  loginScreen.classList.add("hidden");
  adminPanel.classList.remove("hidden");
}

function showLoginScreen() {
  adminPanel.classList.add("hidden");
  loginScreen.classList.remove("hidden");
}

async function verifyAdminSession() {
  try {
    await fetchAdminJson(`${apiPrefix}/admin/llm/integrations`);
    showAdminPanel();
    await refreshAdminData();
    return true;
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      showLoginScreen();
      showToast(toast, "Сессия администратора недействительна", true);
      return false;
    }
    showAdminPanel();
    await refreshAdminData();
    return true;
  }
}

async function loginAdmin() {
  const username = adminUsernameInput?.value?.trim() || "";
  const password = adminPasswordInput?.value?.trim() || "";
  if (!username || !password) {
    showToast(toast, "Введите логин и пароль", true);
    return;
  }
  try {
    await fetchJson(`${apiPrefix}/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const ok = await verifyAdminSession();
    if (ok) {
      resetLlmForm();
      showToast(toast, "Вход выполнен");
    }
  } catch (error) {
    showToast(toast, `Ошибка входа: ${error.message}`, true);
  }
}

function logoutAdmin() {
  // Cookie сбрасывается на сервере (best-effort).
  fetchJson(`${apiPrefix}/admin/logout`, { method: "POST" }).catch(() => {});
  stopStatusPolling();
  showLoginScreen();
}

async function loadSystemInfo() {
  try {
    const info = await fetchJson("/system/info");
    const llmLabel = info.llm_using_fallback
      ? "fallback rule_based"
      : `${info.active_llm_provider || "—"} / ${info.active_llm_model || "—"}`;
    systemInfoEl.textContent = [
      `LLM: ${llmLabel}`,
      `интеграций: ${info.llm_integrations_count}`,
      `embedding: ${info.embedding_model_version}`,
      `fake embeddings: ${info.use_fake_embeddings}`,
    ].join(" · ");

    if (llmWarningEl) {
      if (info.llm_using_fallback) {
        llmWarningEl.textContent =
          "Активная LLM-интеграция не настроена — чат использует rule_based заглушку. Добавьте gigachat или openai_compatible и нажмите Activate.";
        llmWarningEl.classList.remove("hidden");
      } else {
        llmWarningEl.textContent = "";
        llmWarningEl.classList.add("hidden");
      }
    }
  } catch (error) {
    systemInfoEl.textContent = `Ошибка: ${error.message}`;
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  if (!fileInput.files || !fileInput.files.length) {
    showToast(toast, "Выберите файл", true);
    return;
  }
  const formData = new FormData();
  const file = fileInput.files[0];
  formData.append("file", file);
  const isKbArchive = file.name.toLowerCase().endsWith(".zip");
  const uploadUrl = isKbArchive ? `${apiPrefix}/documents/kb-archive` : `${apiPrefix}/documents`;
  try {
    const data = await fetchAdminJson(uploadUrl, { method: "POST", body: formData });
    if (isKbArchive) {
      uploadResult.textContent = `KB archive: документов=${data.accepted}. Индексация идёт в фоне — статусы обновятся автоматически.`;
      showToast(toast, "Архив отправлен в индексацию");
    } else {
      uploadResult.textContent = `document_id=${data.document_id}, task_id=${data.task_id}. Статус обновится автоматически.`;
      showToast(toast, "Документ отправлен");
    }
    fileInput.value = "";
    const [docItems, taskItems] = await Promise.all([loadDocuments(), loadTasks()]);
    syncStatusPolling(docItems, taskItems);
  } catch (error) {
    showToast(toast, `Ошибка загрузки: ${error.message}`, true);
  }
}

function hasInFlightStatuses(items) {
  return items.some((item) => item.status === "pending" || item.status === "processing");
}

function scheduleStatusPolling() {
  if (statusPollTimer !== null) {
    return;
  }
  statusPollTimer = window.setInterval(async () => {
    if (adminPanel.classList.contains("hidden")) {
      return;
    }
    await Promise.all([loadDocuments({ silent: true }), loadTasks({ silent: true })]);
  }, 3000);
}

function stopStatusPolling() {
  if (statusPollTimer === null) {
    return;
  }
  window.clearInterval(statusPollTimer);
  statusPollTimer = null;
}

function syncStatusPolling(docItems, taskItems) {
  if (hasInFlightStatuses(docItems) || hasInFlightStatuses(taskItems)) {
    scheduleStatusPolling();
    return;
  }
  stopStatusPolling();
}

async function loadDocuments(options = {}) {
  const { silent = false } = options;
  try {
    const data = await fetchAdminJson(`${apiPrefix}/documents?limit=50`);
    const snapshot = data.items.map((item) => `${item.document_id}:${item.status}`).join("|");
    if (silent && snapshot === lastDocsSnapshot) {
      return data.items;
    }
    lastDocsSnapshot = snapshot;
    docsTable.innerHTML = "";
    data.items.forEach((item) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${item.document_id}</td>
        <td>${item.original_filename}</td>
        <td>${item.doc_type}</td>
        <td>${statusChip(item.status)}</td>
        <td><button data-doc-id="${item.document_id}" class="danger js-delete-doc">Удалить</button></td>
      `;
      docsTable.appendChild(tr);
    });
    return data.items;
  } catch (error) {
    if (!silent) {
      showToast(toast, `Ошибка документов: ${error.message}`, true);
    }
    return [];
  }
}

async function deleteDocument(documentId) {
  if (!confirm(`Удалить документ ${documentId}?`)) return;
  try {
    await fetchAdminJson(`${apiPrefix}/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
    showToast(toast, "Документ удалён");
    await loadDocuments();
  } catch (error) {
    showToast(toast, `Ошибка удаления: ${error.message}`, true);
  }
}

async function loadTasks(options = {}) {
  const { silent = false } = options;
  try {
    const data = await fetchAdminJson(`${apiPrefix}/indexing-tasks?limit=100`);
    const snapshot = data.items.map((item) => `${item.task_id}:${item.status}:${item.celery_status || ""}`).join("|");
    if (silent && snapshot === lastTasksSnapshot) {
      return data.items;
    }
    lastTasksSnapshot = snapshot;
    tasksTable.innerHTML = "";
    data.items.forEach((item) => {
      const canRetry = item.status === "failed";
      const canCancel = item.status !== "indexed" && item.status !== "cancelled";
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${item.task_id}</td>
        <td>${item.document_id}</td>
        <td>${statusChip(item.status)}</td>
        <td>${item.celery_status || "-"}</td>
        <td>
          <button data-task-id="${item.task_id}" class="btn-secondary js-retry-task" ${canRetry ? "" : "disabled"}>Retry</button>
          <button data-task-id="${item.task_id}" class="danger js-cancel-task" ${canCancel ? "" : "disabled"}>Cancel</button>
        </td>
      `;
      tasksTable.appendChild(tr);
    });
    return data.items;
  } catch (error) {
    if (!silent) {
      showToast(toast, `Ошибка задач: ${error.message}`, true);
    }
    return [];
  }
}

async function retryTask(taskId) {
  try {
    await fetchAdminJson(`${apiPrefix}/indexing-tasks/${encodeURIComponent(taskId)}/retry`, { method: "POST" });
    showToast(toast, "Retry отправлен");
    await loadTasks();
  } catch (error) {
    showToast(toast, `Ошибка retry: ${error.message}`, true);
  }
}

async function cancelTask(taskId) {
  try {
    await fetchAdminJson(`${apiPrefix}/indexing-tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" });
    showToast(toast, "Задача отменена");
    await Promise.all([loadTasks(), loadDocuments()]);
  } catch (error) {
    showToast(toast, `Ошибка cancel: ${error.message}`, true);
  }
}

function setLlmModelOptions(models, selectedModel = "", state = "loaded") {
  llmModelInput.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  if (state === "pending") {
    placeholder.textContent = "Сначала загрузите модели";
  } else if (state === "loading") {
    placeholder.textContent = "Загрузка списка…";
  } else if (models.length) {
    placeholder.textContent = "— выберите модель —";
  } else {
    placeholder.textContent = "— нет моделей —";
  }
  llmModelInput.appendChild(placeholder);
  models.forEach((modelId) => {
    const option = document.createElement("option");
    option.value = modelId;
    option.textContent = modelId;
    llmModelInput.appendChild(option);
  });
  if (selectedModel && models.includes(selectedModel)) {
    llmModelInput.value = selectedModel;
  } else {
    llmModelInput.value = "";
  }
}

function setModelsButtonLoading(loading) {
  llmModelsLoading = loading;
  llmRefreshModelsBtn.disabled = loading;
  llmRefreshModelsBtn.textContent = loading ? "Загрузка…" : "Загрузить модели";
  if (loading) {
    llmRefreshModelsBtn.setAttribute("aria-busy", "true");
  } else {
    llmRefreshModelsBtn.removeAttribute("aria-busy");
  }
}

async function refreshLlmModels(selectedModel = "") {
  const spec = getCurrentProviderSpec();
  const provider = llmProviderInput.value;
  if (!spec) {
    showToast(toast, "Список провайдеров ещё не загружен", true);
    return;
  }
  if (spec.models_source === "static") {
    const models = provider === "rule_based" ? ["rule-based-llm"] : [];
    setLlmModelOptions(models, selectedModel || models[0] || "");
    if (llmModelsHint) {
      llmModelsHint.textContent = spec.description;
    }
    return;
  }

  const integrationId = llmIdInput.value.trim();
  const apiKey = llmApiKeyInput.value.trim();
  setLlmModelOptions([], selectedModel, "loading");
  if (llmModelsHint) {
    llmModelsHint.textContent = `Загрузка моделей (${spec.label})…`;
  }
  setModelsButtonLoading(true);

  try {
    let data;
    if (integrationId && !apiKey) {
      data = await fetchAdminJson(
        `${apiPrefix}/admin/llm/integrations/${encodeURIComponent(integrationId)}/models`,
        { method: "POST" }
      );
    } else {
      if (!providerCredentialsReady(spec)) {
        throw new Error(
          spec.requires_base_url && spec.requires_api_key
            ? "Укажите Base URL и API key"
            : spec.requires_api_key
              ? "Укажите API key / OAuth Basic"
              : "Укажите Base URL"
        );
      }
      data = await fetchAdminJson(`${apiPrefix}/admin/llm/models/lookup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider,
          api_key: apiKey || null,
          base_url: llmBaseUrlInput.value.trim() || null,
        }),
      });
    }
    setLlmModelOptions(data.models || [], selectedModel);
    if (llmModelsHint) {
      llmModelsHint.textContent = `${spec.label}: доступно моделей ${(data.models || []).length}`;
    }
  } catch (error) {
    setLlmModelOptions([], "", "pending");
    if (llmModelsHint) {
      llmModelsHint.textContent = `Не удалось загрузить модели (${spec.label}): ${error.message}`;
    }
    showToast(toast, error.message, true);
  } finally {
    setModelsButtonLoading(false);
  }
}

function resetLlmForm() {
  llmIdInput.value = "";
  llmNameInput.value = "";
  setProviderValue("openai_compatible");
  llmBaseUrlInput.value = "";
  llmApiKeyInput.value = "";
  llmEnabledInput.checked = true;
  llmActivateInput.checked = false;
  llmFormResult.textContent = "";
  setLlmModelOptions([], "", "pending");
  updateProviderFormHints();
  scheduleAutoLoadModels();
}

async function fillLlmForm(item) {
  llmIdInput.value = item.id;
  llmNameInput.value = item.name;
  setProviderValue(item.provider);
  llmBaseUrlInput.value = item.base_url || "";
  llmApiKeyInput.value = "";
  llmEnabledInput.checked = item.enabled;
  llmActivateInput.checked = false;
  llmFormResult.textContent = item.api_key_masked ? `Ключ: ${item.api_key_masked}` : "";
  updateProviderFormHints();
  await refreshLlmModels(item.model);
}

async function loadLlmIntegrations() {
  try {
    const data = await fetchAdminJson(`${apiPrefix}/admin/llm/integrations`);
    llmTable.innerHTML = "";
    data.items.forEach((item) => {
      const tr = document.createElement("tr");
      const activeMark = item.is_active ? " (активна)" : "";
      tr.innerHTML = `
        <td>${item.name}${activeMark}</td>
        <td>${item.provider}</td>
        <td>${item.model}</td>
        <td>${item.api_key_masked || "—"}</td>
        <td>${item.enabled ? "да" : "нет"}</td>
        <td class="actions-cell">
          <button data-id="${item.id}" class="btn-secondary js-llm-edit">Изменить</button>
          <button data-id="${item.id}" class="btn-secondary js-llm-activate">Активировать</button>
          <button data-id="${item.id}" class="btn-secondary js-llm-test">Тест</button>
          <button data-id="${item.id}" class="danger js-llm-delete">Удалить</button>
        </td>
      `;
      llmTable.appendChild(tr);
    });
  } catch (error) {
    showToast(toast, `Ошибка LLM: ${error.message}`, true);
  }
}

async function saveLlmIntegration(event) {
  event.preventDefault();
  const id = llmIdInput.value.trim();
  if (!llmModelInput.value.trim()) {
    showToast(toast, "Выберите модель из списка (сначала «Загрузить модели»)", true);
    return;
  }
  const payload = {
    name: llmNameInput.value.trim(),
    provider: llmProviderInput.value,
    model: llmModelInput.value.trim(),
    base_url: llmBaseUrlInput.value.trim() || null,
    enabled: llmEnabledInput.checked,
    activate: llmActivateInput.checked,
  };
  const apiKey = llmApiKeyInput.value.trim();
  const spec = getCurrentProviderSpec();
  if (!id && spec?.requires_api_key && !apiKey) {
    showToast(toast, `Для ${spec.label} укажите ключ в поле API key`, true);
    return;
  }
  if (apiKey) {
    payload.api_key = apiKey;
  }

  try {
    if (id) {
      await fetchAdminJson(`${apiPrefix}/admin/llm/integrations/${encodeURIComponent(id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      llmFormResult.textContent = "Интеграция обновлена";
    } else {
      const created = await fetchAdminJson(`${apiPrefix}/admin/llm/integrations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      llmIdInput.value = created.id;
      llmFormResult.textContent = `Создано: ${created.id}`;
    }
    showToast(toast, "LLM сохранена");
    await Promise.all([loadLlmIntegrations(), loadSystemInfo()]);
  } catch (error) {
    showToast(toast, `Ошибка сохранения LLM: ${error.message}`, true);
  }
}

async function activateLlm(id) {
  try {
    await fetchAdminJson(`${apiPrefix}/admin/llm/integrations/${encodeURIComponent(id)}/activate`, {
      method: "POST",
    });
    showToast(toast, "LLM активирована");
    await Promise.all([loadLlmIntegrations(), loadSystemInfo()]);
  } catch (error) {
    showToast(toast, `Ошибка активации: ${error.message}`, true);
  }
}

async function testLlm(id) {
  try {
    const result = await fetchAdminJson(`${apiPrefix}/admin/llm/integrations/${encodeURIComponent(id)}/test`, {
      method: "POST",
    });
    showToast(toast, result.ok ? result.message : `Тест не прошёл: ${result.message}`, !result.ok);
  } catch (error) {
    showToast(toast, `Ошибка теста: ${error.message}`, true);
  }
}

async function deleteLlm(id) {
  if (!confirm("Удалить эту LLM-интеграцию?")) return;
  try {
    await fetchAdminJson(`${apiPrefix}/admin/llm/integrations/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    showToast(toast, "Интеграция удалена");
    resetLlmForm();
    await Promise.all([loadLlmIntegrations(), loadSystemInfo()]);
  } catch (error) {
    showToast(toast, `Ошибка удаления: ${error.message}`, true);
  }
}

async function loadRagPrompt() {
  try {
    const data = await fetchAdminJson(`${apiPrefix}/admin/rag/prompt`);
    systemInstructionInput.value = data.system_instruction || "";
    updatePromptMeta(data);
  } catch (error) {
    showToast(toast, `Ошибка загрузки промпта: ${error.message}`, true);
  }
}

function updatePromptMeta(data) {
  const length = systemInstructionInput.value.length;
  const maxLength = data.max_length || 4000;
  const defaultHint = data.is_default ? "используется значение по умолчанию" : "изменён";
  promptMeta.textContent = `${length} / ${maxLength} символов · ${defaultHint} · обновлено: ${data.updated_at || "—"}`;
}

async function saveRagPrompt(event) {
  event.preventDefault();
  const system_instruction = systemInstructionInput.value.trim();
  if (!system_instruction) {
    showToast(toast, "Введите системную инструкцию", true);
    return;
  }
  try {
    const data = await fetchAdminJson(`${apiPrefix}/admin/rag/prompt`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ system_instruction }),
    });
    systemInstructionInput.value = data.system_instruction;
    updatePromptMeta(data);
    promptFormResult.textContent = "Промпт сохранён. Новые ответы чата используют эту инструкцию.";
    showToast(toast, "Промпт сохранён");
  } catch (error) {
    promptFormResult.textContent = "";
    showToast(toast, `Ошибка сохранения: ${error.message}`, true);
  }
}

async function resetRagPrompt() {
  if (!confirm("Вернуть системную инструкцию к значению по умолчанию?")) return;
  try {
    const data = await fetchAdminJson(`${apiPrefix}/admin/rag/prompt/reset`, { method: "POST" });
    systemInstructionInput.value = data.system_instruction;
    updatePromptMeta(data);
    promptFormResult.textContent = "Восстановлен промпт по умолчанию.";
    showToast(toast, "Промпт по умолчанию восстановлен");
  } catch (error) {
    showToast(toast, `Ошибка сброса: ${error.message}`, true);
  }
}

async function refreshAdminData() {
  await loadLlmProviderSpecs();
  const results = await Promise.all([
    loadSystemInfo(),
    loadRagPrompt(),
    loadDocuments(),
    loadTasks(),
    loadLlmIntegrations(),
  ]);
  syncStatusPolling(results[2], results[3]);
}

loginBtn.addEventListener("click", loginAdmin);
logoutBtn.addEventListener("click", logoutAdmin);
uploadForm.addEventListener("submit", uploadDocument);
refreshDocsBtn.addEventListener("click", loadDocuments);
refreshTasksBtn.addEventListener("click", loadTasks);
refreshLlmBtn.addEventListener("click", loadLlmIntegrations);
llmForm.addEventListener("submit", saveLlmIntegration);
llmFormResetBtn.addEventListener("click", resetLlmForm);
llmRefreshModelsBtn.addEventListener("click", () => refreshLlmModels(llmModelInput.value));
llmProviderInput.addEventListener("change", () => {
  setLlmModelOptions([], "", "pending");
  updateProviderFormHints();
  scheduleAutoLoadModels();
});
llmBaseUrlInput.addEventListener("input", () => scheduleAutoLoadModels(llmModelInput.value));
llmApiKeyInput.addEventListener("input", () => scheduleAutoLoadModels(llmModelInput.value));
promptForm.addEventListener("submit", saveRagPrompt);
resetPromptBtn.addEventListener("click", resetRagPrompt);
systemInstructionInput.addEventListener("input", () => {
  const maxLength = 4000;
  promptMeta.textContent = `${systemInstructionInput.value.length} / ${maxLength} символов`;
});

docsTable.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (target.classList.contains("js-delete-doc")) {
    deleteDocument(target.dataset.docId);
  }
});

tasksTable.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (target.classList.contains("js-retry-task")) {
    retryTask(target.dataset.taskId);
  }
  if (target.classList.contains("js-cancel-task")) {
    cancelTask(target.dataset.taskId);
  }
});

llmTable.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const id = target.dataset.id;
  if (!id) return;
  if (target.classList.contains("js-llm-edit")) {
    fetchAdminJson(`${apiPrefix}/admin/llm/integrations/${encodeURIComponent(id)}`)
      .then(fillLlmForm)
      .catch((error) => showToast(toast, error.message, true));
  }
  if (target.classList.contains("js-llm-activate")) {
    activateLlm(id);
  }
  if (target.classList.contains("js-llm-test")) {
    testLlm(id);
  }
  if (target.classList.contains("js-llm-delete")) {
    deleteLlm(id);
  }
});

renderProviderOptions(LLM_PROVIDER_FALLBACKS, llmProviderInput.value || "openai_compatible");
setLlmModelOptions([], "", "pending");
updateProviderFormHints();
verifyAdminSession();
