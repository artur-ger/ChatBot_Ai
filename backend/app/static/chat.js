const CHAT_SESSION_STORAGE_KEY = "chatbot_ai_chat_id";

const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const messages = document.getElementById("messages");
const newChatBtn = document.getElementById("newChatBtn");
const resetChatBtn = document.getElementById("resetChatBtn");
const chatSessionHint = document.getElementById("chatSessionHint");
const toast = document.getElementById("toast");

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
  const short = chatId.length > 12 ? `${chatId.slice(0, 8)}…` : chatId;
  chatSessionHint.textContent = `Сессия: ${short}`;
}

function getChatId() {
  return getOrCreateChatId();
}

function appendMessage(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  const title = role === "user" ? "Вы" : "Бот";
  wrap.textContent = `${title}: ${text}`;
  messages.appendChild(wrap);
  messages.scrollTop = messages.scrollHeight;
}

async function sendChatMessage(event) {
  event.preventDefault();
  const text = chatInput.value.trim();
  const chatId = getChatId();
  if (!text) {
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
  const chatId = getChatId();
  try {
    const data = await fetchJson(`${apiPrefix}/chat/${encodeURIComponent(chatId)}/history?limit=20`);
    messages.innerHTML = "";
    data.items.forEach((item) => {
      appendMessage("user", item.question);
      appendMessage("assistant", item.answer);
    });
    if (data.items.length) {
      showToast(toast, "История загружена");
    }
  } catch (error) {
    showToast(toast, `Ошибка истории: ${error.message}`, true);
  }
}

async function resetChat() {
  const chatId = getChatId();
  if (!confirm("Удалить историю сообщений в этом диалоге?")) return;
  try {
    const data = await fetchJson(`${apiPrefix}/chat/${encodeURIComponent(chatId)}/reset`, { method: "POST" });
    messages.innerHTML = "";
    showToast(toast, `Удалено сообщений: ${data.deleted_messages}`);
  } catch (error) {
    showToast(toast, `Ошибка сброса: ${error.message}`, true);
  }
}

function startNewChatSession() {
  const id = createChatSessionId();
  setChatSessionId(id);
  messages.innerHTML = "";
  showToast(toast, "Новая сессия");
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
  } catch (_error) {}
}

initPublicUi();
