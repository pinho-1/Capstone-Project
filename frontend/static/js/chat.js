window.addEventListener("DOMContentLoaded", () => {
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatMessages = document.getElementById("chat-messages");
  const sendBtn = document.getElementById("send-btn");
  const clearChatBtn = document.getElementById("clear-chat-btn");
  const chatEmpty = document.getElementById("chat-empty");

  if (!chatForm || !chatInput || !chatMessages || !sendBtn) {
    console.error("[chat] Missing required DOM elements:", {
      chatForm, chatInput, chatMessages, sendBtn
    });
    return;
  }

  // --- Helpers ---
  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function hideEmptyState() {
    if (chatEmpty) chatEmpty.style.display = "none";
  }

  function showEmptyState() {
    if (chatEmpty) chatEmpty.style.display = "block";
  }

  let typingEl = null;

  function addTyping() {
    if (typingEl) return;

    const wrap = document.createElement("div");
    wrap.className = "msg msg--assistant";
    wrap.dataset.typing = "true";

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    const dots = document.createElement("div");
    dots.className = "typing-bubble";
    dots.innerHTML = "<span></span><span></span><span></span>";

    bubble.appendChild(dots);

    const ts = document.createElement("div");
    ts.className = "timestamp";
    ts.textContent = "Talentum is typing…";

    wrap.appendChild(bubble);
    wrap.appendChild(ts);

    chatMessages.appendChild(wrap);
    typingEl = wrap;
    scrollToBottom();
  }

  function removeTyping() {
    if (!typingEl) return;
    typingEl.remove();
    typingEl = null;
  }

  // --- Real Functions ---
  function addMessage(text, role, timestamp = "") {
    hideEmptyState();

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

    addTyping(); // ✅ show typing bubble in chat

    try {
      const formData = new FormData();
      formData.append("message", message);

      const res = await fetch("/chat/message", { method: "POST", body: formData });

      if (res.status === 503) {
        removeTyping();
        addMessage("The model is overloaded right now. Try again in a moment.", "assistant");
        return;
      }

      const data = await res.json();

      removeTyping();

      if (!res.ok) {
        addMessage(data.error || "Something went wrong.", "assistant");
        return;
      }

      if (data.response) addMessage(data.response, "assistant");

    } catch (err) {
      console.error(err);
      removeTyping();
      addMessage("Sorry, I crashed briefly. Try again.", "assistant");
    } finally {
      chatInput.disabled = false;
      sendBtn.disabled = false;
      chatInput.focus();
    }
  }

  // --- Auto-resize textarea ---
  chatInput.addEventListener("input", function () {
    this.style.height = "auto";
    this.style.height = Math.min(this.scrollHeight, 160) + "px";
  });

  // --- Enter sends, Shift+Enter newline ---
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();

      // More reliable than requestSubmit in some setups:
      chatForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
  });

  // --- Submit handler ---
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const message = chatInput.value.trim();
    if (!message) return;

    addMessage(message, "user");
    chatInput.value = "";
    chatInput.style.height = "auto";

    await sendMessage(message);
  });

  // --- Suggestions ---
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", async () => {
      const suggestion = chip.dataset.suggestion;
      if (!suggestion) return;

      addMessage(suggestion, "user");
      await sendMessage(suggestion);
    });
  });

  // --- Clear chat ---
  clearChatBtn?.addEventListener("click", async () => {
    const ok = confirm("Clear chat history?");
    if (!ok) return;

    try {
      const res = await fetch("/chat/clear", { method: "POST" });
      if (!res.ok) return;

      [...chatMessages.querySelectorAll(".msg")].forEach((m) => m.remove());
      showEmptyState();
      scrollToBottom();
    } catch (err) {
      console.error(err);
    }
  });

  // --- Load history ---
  async function loadHistory() {
    try {
      const res = await fetch("/chat/history");
      const data = await res.json();
      if (!res.ok) return;

      [...chatMessages.querySelectorAll(".msg")].forEach((m) => m.remove());

      if (data.messages?.length) {
        hideEmptyState();
        data.messages.forEach((msg) => {
          addMessage(
            msg.content,
            msg.role,
            msg.timestamp ? new Date(msg.timestamp).toLocaleString() : ""
          );
        });
      } else {
        showEmptyState();
      }

      scrollToBottom();
    } catch (err) {
      console.error(err);
    }
  }

  const rail = document.getElementById("chat-rail");
  const railBody = document.getElementById("rail-body");
  const railToggle = document.getElementById("rail-toggle");
  const chatGrid = document.querySelector(".chat-grid");

  railToggle?.addEventListener("click", () => {
    const collapsed = rail.classList.toggle("is-collapsed");
    chatGrid?.classList.toggle("rail-collapsed", collapsed);
    railToggle.textContent = collapsed ? "Show" : "Hide";
    railToggle.title = collapsed ? "Show quick actions" : "Hide quick actions";
    railToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  });

  loadHistory();
  scrollToBottom();
});
