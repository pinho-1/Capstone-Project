const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");
const sendBtn = document.getElementById("send-btn");
const loadingIndicator = document.getElementById("loading-indicator");
const clearChatBtn = document.getElementById("clear-chat-btn");
const chatEmpty = document.getElementById("chat-empty");

// Auto-resize textarea
chatInput.addEventListener("input", function () {
  this.style.height = "auto";
  this.style.height = Math.min(this.scrollHeight, 160) + "px";
});

// Enter to send, Shift+Enter newline
chatInput.addEventListener("keydown", function (e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatForm.requestSubmit();
  }
});

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideEmptyState() {
  if (chatEmpty) chatEmpty.style.display = "none";
}

function addMessage(text, role, timestamp = "") {
  const wrap = document.createElement("div");
  wrap.className = `msg msg--${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  const ts = document.createElement("div");
  ts.className = "timestamp";
  ts.textContent = timestamp || (role === "assistant" ? "Talentum" : "You");

  wrap.appendChild(bubble);
  wrap.appendChild(ts);
  chatMessages.appendChild(wrap);
  scrollToBottom();
}

async function sendMessage(message) {
  chatInput.disabled = true;
  sendBtn.disabled = true;
  loadingIndicator.style.display = "flex";

  try {
    const formData = new FormData();
    formData.append("message", message);

    const res = await fetch("/chat/message", { method: "POST", body: formData });

    if (res.status === 503) {
      addMessage("The model is overloaded right now. Try again in a moment.", "assistant");
      return;
    }

    const data = await res.json();

    if (!res.ok) {
      addMessage(data.error || "Something went wrong.", "assistant");
      return;
    }

    if (data.response) addMessage(data.response, "assistant");
  } catch (err) {
    console.error(err);
    addMessage("Sorry, I crashed briefly. Try again.", "assistant");
  } finally {
    chatInput.disabled = false;
    sendBtn.disabled = false;
    loadingIndicator.style.display = "none";
    chatInput.focus();
  }
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;

  hideEmptyState();
  addMessage(message, "user");
  chatInput.value = "";
  chatInput.style.height = "auto";

  await sendMessage(message);
});

// Suggestions (use your .btn buttons as chips)
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", async () => {
    const suggestion = chip.dataset.suggestion;
    if (!suggestion) return;

    hideEmptyState();
    addMessage(suggestion, "user");
    await sendMessage(suggestion);
  });
});

// Clear chat
clearChatBtn?.addEventListener("click", async () => {
  const ok = confirm("Clear chat history?");
  if (!ok) return;

  try {
    const res = await fetch("/chat/clear", { method: "POST" });
    if (!res.ok) return;

    // Remove all messages, then show empty state again
    [...chatMessages.querySelectorAll(".msg")].forEach((m) => m.remove());
    if (chatEmpty) chatEmpty.style.display = "block";
  } catch (err) {
    console.error(err);
  }
});

// Load history
function hasAnyMsg() {
  return chatMessages.querySelectorAll(".msg").length > 0;
}

async function loadHistory() {
  try {
    const res = await fetch("/chat/history");
    const data = await res.json();
    if (!res.ok) return;

    // Remove existing .msg blocks (if you removed the hardcoded welcome)
    [...chatMessages.querySelectorAll(".msg")].forEach((m) => m.remove());

    if (data.messages?.length) {
      if (chatEmpty) chatEmpty.style.display = "none";

      data.messages.forEach((msg) => {
        addMessage(
          msg.content,
          msg.role,
          msg.timestamp ? new Date(msg.timestamp).toLocaleString() : ""
        );
      });
    } else {
      if (chatEmpty) chatEmpty.style.display = "block";
    }

    scrollToBottom();
  } catch (err) {
    console.error(err);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  loadHistory();
  scrollToBottom();
});
