const apiPrefix = "/api/v1";

const chatIdInput = document.getElementById("chatId");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const messages = document.getElementById("messages");
const loadHistoryBtn = document.getElementById("loadHistoryBtn");
const resetChatBtn = document.getElementById("resetChatBtn");

const uploadForm = document.getElementById("uploadForm");
const fileInput = document.getElementById("fileInput");
const uploadResult = document.getElementById("uploadResult");

const docsTable = document.getElementById("docsTable");
const refreshDocsBtn = document.getElementById("refreshDocsBtn");

const tasksTable = document.getElementById("tasksTable");
const refreshTasksBtn = document.getElementById("refreshTasksBtn");

const toast = document.getElementById("toast");

function showToast(text, isError = false) {
  toast.textContent = text;
  toast.classList.remove("hidden");
  toast.style.background = isError ? "#991b1b" : "#1f2937";
  setTimeout(() => toast.classList.add("hidden"), 2800);
}

function appendMessage(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  const title = role === "user" ? "Вы" : "Бот";
  wrap.textContent = `${title}: ${text}`;
  messages.appendChild(wrap);
  messages.scrollTop = messages.scrollHeight;
}

function statusChip(status) {
  return `<span class="status-chip status-${String(status).toLowerCase()}">${status}</span>`;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const message = data && data.message ? data.message : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

async function sendChatMessage(event) {
  event.preventDefault();
  const text = chatInput.value.trim();
  const chatId = chatIdInput.value.trim();
  if (!text || !chatId) {
    return;
  }

  appendMessage("user", text);
  chatInput.value = "";
  try {
    const data = await fetchJson(`${apiPrefix}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, chat_id: chatId }),
    });
    appendMessage("assistant", data.text);
  } catch (error) {
    appendMessage("assistant", `Ошибка: ${error.message}`);
  }
}

async function loadHistory() {
  const chatId = chatIdInput.value.trim();
  if (!chatId) return;
  try {
    const data = await fetchJson(`${apiPrefix}/chat/${encodeURIComponent(chatId)}/history?limit=20`);
    messages.innerHTML = "";
    data.items.forEach((item) => {
      appendMessage("user", item.question);
      appendMessage("assistant", item.answer);
    });
    showToast("История загружена");
  } catch (error) {
    showToast(`Ошибка истории: ${error.message}`, true);
  }
}

async function resetChat() {
  const chatId = chatIdInput.value.trim();
  if (!chatId) return;
  if (!confirm("Удалить историю текущего чата?")) return;
  try {
    const data = await fetchJson(`${apiPrefix}/chat/${encodeURIComponent(chatId)}/reset`, { method: "POST" });
    messages.innerHTML = "";
    showToast(`Удалено сообщений: ${data.deleted_messages}`);
  } catch (error) {
    showToast(`Ошибка сброса: ${error.message}`, true);
  }
}

async function uploadDocument(event) {
  event.preventDefault();
  if (!fileInput.files || !fileInput.files.length) {
    showToast("Выберите файл", true);
    return;
  }
  const formData = new FormData();
  const file = fileInput.files[0];
  formData.append("file", file);
  const isKbArchive = file.name.toLowerCase().endsWith(".zip");
  const uploadUrl = isKbArchive ? `${apiPrefix}/documents/kb-archive` : `${apiPrefix}/documents`;
  try {
    const data = await fetchJson(uploadUrl, {
      method: "POST",
      body: formData,
    });
    if (isKbArchive) {
      uploadResult.textContent = `KB archive принят: документов=${data.accepted}, задач=${data.items.length}`;
      showToast("База знаний отправлена в индексацию");
    } else {
      uploadResult.textContent = `Принято: document_id=${data.document_id}, task_id=${data.task_id}`;
      showToast("Документ отправлен в индексацию");
    }
    fileInput.value = "";
    await Promise.all([loadDocuments(), loadTasks()]);
  } catch (error) {
    showToast(`Ошибка загрузки: ${error.message}`, true);
  }
}

async function loadDocuments() {
  try {
    const data = await fetchJson(`${apiPrefix}/documents?limit=50`);
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
  } catch (error) {
    showToast(`Ошибка документов: ${error.message}`, true);
  }
}

async function deleteDocument(documentId) {
  if (!confirm(`Удалить документ ${documentId}?`)) return;
  try {
    await fetchJson(`${apiPrefix}/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
    showToast("Документ удален");
    await loadDocuments();
  } catch (error) {
    showToast(`Ошибка удаления: ${error.message}`, true);
  }
}

async function loadTasks() {
  try {
    const data = await fetchJson(`${apiPrefix}/indexing-tasks?limit=100`);
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
  } catch (error) {
    showToast(`Ошибка задач: ${error.message}`, true);
  }
}

async function retryTask(taskId) {
  try {
    await fetchJson(`${apiPrefix}/indexing-tasks/${encodeURIComponent(taskId)}/retry`, { method: "POST" });
    showToast("Retry отправлен");
    await loadTasks();
  } catch (error) {
    showToast(`Ошибка retry: ${error.message}`, true);
  }
}

async function cancelTask(taskId) {
  try {
    await fetchJson(`${apiPrefix}/indexing-tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" });
    showToast("Задача отменена");
    await Promise.all([loadTasks(), loadDocuments()]);
  } catch (error) {
    showToast(`Ошибка cancel: ${error.message}`, true);
  }
}

chatForm.addEventListener("submit", sendChatMessage);
loadHistoryBtn.addEventListener("click", loadHistory);
resetChatBtn.addEventListener("click", resetChat);
uploadForm.addEventListener("submit", uploadDocument);
refreshDocsBtn.addEventListener("click", loadDocuments);
refreshTasksBtn.addEventListener("click", loadTasks);

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

loadDocuments();
loadTasks();
