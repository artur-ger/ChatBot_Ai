const chatIdInput = document.getElementById("chatId");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const messages = document.getElementById("messages");
const loadHistoryBtn = document.getElementById("loadHistoryBtn");
const resetChatBtn = document.getElementById("resetChatBtn");
const toast = document.getElementById("toast");

function appendMessage(role, text, sources = [], confidence = null) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  const title = role === "user" ? "Вы" : "Бот";
  const src = sources.length
    ? `\n\nИсточники:\n${sources
        .slice(0, 3)
        .map((s) => `- [${s.doc_id}] ${String(s.snippet || "").slice(0, 120)}`)
        .join("\n")}`
    : "";
  const conf =
    role === "assistant" && typeof confidence === "number" && confidence > 0
      ? `\n\nУверенность: ${confidence.toFixed(2)}`
      : "";
  wrap.textContent = `${title}: ${text}${src}${conf}`;
  messages.appendChild(wrap);
  messages.scrollTop = messages.scrollHeight;
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
    appendMessage("assistant", data.text, data.sources || [], data.confidence);
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
    showToast(toast, "История загружена");
  } catch (error) {
    showToast(toast, `Ошибка истории: ${error.message}`, true);
  }
}

async function resetChat() {
  const chatId = chatIdInput.value.trim();
  if (!chatId) return;
  if (!confirm("Удалить историю текущего чата?")) return;
  try {
    const data = await fetchJson(`${apiPrefix}/chat/${encodeURIComponent(chatId)}/reset`, { method: "POST" });
    messages.innerHTML = "";
    showToast(toast, `Удалено сообщений: ${data.deleted_messages}`);
  } catch (error) {
    showToast(toast, `Ошибка сброса: ${error.message}`, true);
  }
}

chatForm.addEventListener("submit", sendChatMessage);
loadHistoryBtn.addEventListener("click", loadHistory);
resetChatBtn.addEventListener("click", resetChat);

async function initPublicUi() {
  const adminLink = document.getElementById("adminLink");
  try {
    const config = await fetchJson("/system/ui-config");
    if (adminLink && config.show_admin_link) {
      adminLink.classList.remove("hidden");
    }
  } catch (_error) {
    // Public chat works without ui-config; admin link stays hidden.
  }
}

initPublicUi();
