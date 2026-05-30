const CHAT_SESSION_STORAGE_KEY = "chatbot_ai_chat_id";

const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatSubmitBtn = document.getElementById("chatSubmitBtn");
const messages = document.getElementById("messages");
const newChatBtn = document.getElementById("newChatBtn");
const resetChatBtn = document.getElementById("resetChatBtn");
const chatSessionHint = document.getElementById("chatSessionHint");
const toast = document.getElementById("toast");

let isSending = false;
let typingNode = null;

function createChatSessionId() {
  const uuid =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
  return `web-${uuid}`;
}

function getOrCreateChatId() {
  let id = localStorage.getItem(CHAT_SESSION_STORAGE_KEY);
  if (!id || !id.trim()) {
    id = createChatSessionId();
    localStorage.setItem(CHAT_SESSION_STORAGE_KEY, id);
  }
  return id.trim();
}

function setChatSessionId(id) {
  localStorage.setItem(CHAT_SESSION_STORAGE_KEY, id);
  updateSessionHint(id);
}

function updateSessionHint(chatId) {
  if (!chatSessionHint) return;
  const short = chatId.length > 16 ? `${chatId.slice(0, 12)}…` : chatId;
  chatSessionHint.textContent = `Сессия: ${short}`;
}

function getChatId() {
  return getOrCreateChatId();
}

function renderEmptyState() {
  if (!messages) return;
  if (messages.querySelector(".msg-row") || messages.querySelector(".messages-empty")) {
    return;
  }
  const empty = document.createElement("div");
  empty.className = "messages-empty";
  empty.textContent = "Задайте вопрос — ответ будет сформирован на основе базы знаний.";
  messages.appendChild(empty);
}

function clearEmptyState() {
  messages?.querySelector(".messages-empty")?.remove();
}

function appendMessage(role, text) {
  clearEmptyState();
  const row = document.createElement("div");
  row.className = `msg-row ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  const meta = document.createElement("span");
  meta.className = "msg-meta";
  meta.textContent = role === "user" ? "Вы" : "Ассистент";

  const body = document.createElement("span");
  body.textContent = text;

  bubble.appendChild(meta);
  bubble.appendChild(body);
  row.appendChild(bubble);
  messages.appendChild(row);
  messages.scrollTop = messages.scrollHeight;
  return row;
}

function showTypingIndicator() {
  removeTypingIndicator();
  clearEmptyState();
  typingNode = document.createElement("div");
  typingNode.className = "msg-row assistant typing";
  typingNode.innerHTML =
    '<div class="msg-bubble"><span class="msg-meta">Ассистент</span><span>Формирую ответ…</span></div>';
  messages.appendChild(typingNode);
  messages.scrollTop = messages.scrollHeight;
}

function removeTypingIndicator() {
  typingNode?.remove();
  typingNode = null;
}

function setSendingState(active) {
  isSending = active;
  if (chatSubmitBtn) chatSubmitBtn.disabled = active;
  if (chatInput) chatInput.disabled = active;
}

async function sendChatMessage(event) {
  event.preventDefault();
  if (isSending) return;

  const text = chatInput.value.trim();
  const chatId = getChatId();
  if (!text) return;

  appendMessage("user", text);
  chatInput.value = "";
  setSendingState(true);
  showTypingIndicator();

  try {
    const data = await fetchJson(`${apiPrefix}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, chat_id: chatId }),
    });
    removeTypingIndicator();
    appendMessage("assistant", data.text);
  } catch (error) {
    removeTypingIndicator();
    appendMessage("assistant", `Не удалось получить ответ: ${error.message}`);
  } finally {
    setSendingState(false);
    chatInput.focus();
  }
}

async function loadHistory() {
  const chatId = getChatId();
  try {
    const data = await fetchJson(`${apiPrefix}/chat/${encodeURIComponent(chatId)}/history?limit=20`);
    messages.innerHTML = "";
    if (!data.items.length) {
      renderEmptyState();
      return;
    }
    data.items.forEach((item) => {
      appendMessage("user", item.question);
      appendMessage("assistant", item.answer);
    });
  } catch (error) {
    renderEmptyState();
    showToast(toast, `Ошибка загрузки истории: ${error.message}`, true);
  }
}

async function resetChat() {
  const chatId = getChatId();
  if (!confirm("Удалить историю сообщений в этом диалоге?")) return;
  try {
    const data = await fetchJson(`${apiPrefix}/chat/${encodeURIComponent(chatId)}/reset`, {
      method: "POST",
    });
    messages.innerHTML = "";
    renderEmptyState();
    showToast(toast, `Удалено сообщений: ${data.deleted_messages}`);
  } catch (error) {
    showToast(toast, `Ошибка сброса: ${error.message}`, true);
  }
}

function startNewChatSession() {
  const id = createChatSessionId();
  setChatSessionId(id);
  messages.innerHTML = "";
  renderEmptyState();
  showToast(toast, "Начат новый диалог");
  chatInput.focus();
}

chatForm.addEventListener("submit", sendChatMessage);
if (newChatBtn) {
  newChatBtn.addEventListener("click", startNewChatSession);
}
resetChatBtn.addEventListener("click", resetChat);

async function initPublicUi() {
  const chatId = getOrCreateChatId();
  updateSessionHint(chatId);
  await loadHistory();

  const adminLink = document.getElementById("adminLink");
  try {
    const config = await fetchJson("/system/ui-config");
    if (adminLink && config.show_admin_link) {
      adminLink.classList.remove("hidden");
    }
  } catch (_error) {
    /* ui-config optional */
  }
}

initPublicUi();
