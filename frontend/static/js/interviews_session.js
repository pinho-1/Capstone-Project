document.addEventListener("DOMContentLoaded", () => {
  const statusEl = document.getElementById("interview-status");
  const statusDot = document.getElementById("text-status-dot");

  const startBtn = document.getElementById("start-text-btn");
  const resetBtn = document.getElementById("reset-btn");

  const chatPanel = document.getElementById("chat-panel");
  const chatMessages = document.getElementById("chat-messages");
  const typingRow = document.getElementById("typing-row");

  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");

  // Results UI
  const resultsPanel = document.getElementById("results-panel");
  const resultsEmoji = document.getElementById("results-emoji");
  const resultsTitle = document.getElementById("results-title");
  const resultsScoreNum = document.getElementById("results-score-num");
  const resultsSub = document.getElementById("results-sub");
  const resultsFeedback = document.getElementById("results-feedback");
  const resultsRestartBtn = document.getElementById("results-restart-btn");

  if (!statusEl || !startBtn || !resetBtn || !chatMessages || !input || !form || !sendBtn) return;

  const cfg = window.INTERVIEW_CONFIG || {};
  const lang = cfg.language || "en";
  const totalTurns = Number(cfg.questionCount || 5); // interpreted as max turns

  let sessionReady = false;
  let sessionStarted = false;
  let awaitingAi = false;

  const t = (en, pt) => (lang === "pt" ? pt : en);

  const setReady = (isReady) => {
    sessionReady = isReady;
    startBtn.disabled = !isReady;
    resetBtn.disabled = !isReady;
    if (statusDot) statusDot.classList.toggle("active", isReady);
  };

  const setChatEnabled = (enabled) => {
    input.disabled = !enabled;
    sendBtn.disabled = !enabled;
  };

  const setTyping = (isTyping) => {
    awaitingAi = isTyping;
    if (typingRow) typingRow.hidden = !isTyping;
  };

  const scrollToBottom = () => {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  };

  const addMessage = (who, text) => {
    const row = document.createElement("div");
    row.className = `chat-msg ${who}`;

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.textContent = text;

    row.appendChild(bubble);
    chatMessages.appendChild(row);
    scrollToBottom();
  };

  const chooseEmoji = (score) => {
    if (score >= 90) return "🏆";
    if (score >= 80) return "🔥";
    if (score >= 70) return "✅";
    if (score >= 60) return "👍";
    if (score >= 45) return "🛠️";
    return "📌";
  };

  const animateScore = (to) => {
    if (!resultsScoreNum) return;

    const from = 0;
    const duration = 900;
    const start = performance.now();

    const step = (now) => {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const val = Math.round(from + (to - from) * eased);
      resultsScoreNum.textContent = String(val);
      if (p < 1) requestAnimationFrame(step);
    };

    resultsScoreNum.textContent = "0";
    requestAnimationFrame(step);
  };

  const showResults = ({ final_score, feedback }) => {
    if (chatPanel) chatPanel.classList.add("is-finished");
    if (resultsPanel) resultsPanel.hidden = false;

    const score = typeof final_score === "number" ? final_score : null;

    if (resultsTitle) resultsTitle.textContent = t("Interview Results", "Resultado da Entrevista");

    if (score !== null) {
      if (resultsEmoji) resultsEmoji.textContent = chooseEmoji(score);
      animateScore(score);
    } else {
      if (resultsEmoji) resultsEmoji.textContent = "📌";
      if (resultsScoreNum) resultsScoreNum.textContent = "—";
    }

    if (resultsSub) {
      resultsSub.textContent = t(
        "Here’s what to improve next time.",
        "Aqui vai o que podes melhorar para a próxima."
      );
    }

    if (resultsFeedback) {
      resultsFeedback.innerHTML = "";
      if (Array.isArray(feedback) && feedback.length) {
        feedback.forEach((item) => {
          const li = document.createElement("li");
          li.textContent = item;
          resultsFeedback.appendChild(li);
        });
      } else {
        const li = document.createElement("li");
        li.textContent = t("No feedback returned.", "Sem feedback.");
        resultsFeedback.appendChild(li);
      }
    }
  };

  const resetUI = () => {
    chatMessages.innerHTML = "";
    sessionStarted = false;
    awaitingAi = false;

    setTyping(false);
    setChatEnabled(false);

    if (chatPanel) chatPanel.classList.remove("is-finished");
    if (resultsPanel) resultsPanel.hidden = true;
    if (resultsFeedback) resultsFeedback.innerHTML = "";
    if (resultsScoreNum) resultsScoreNum.textContent = "0";
    if (resultsEmoji) resultsEmoji.textContent = "🎯";

    statusEl.textContent = t("Preparing your interview…", "A preparar a tua entrevista…");
  };

  const prepareSession = () => {
    setReady(false);
    setChatEnabled(false);

    setTimeout(() => {
      setReady(true);
      statusEl.textContent = t(
        `Interview prepared for ${cfg.role} (${cfg.seniority}), with ${totalTurns} turns.`,
        `Entrevista preparada para ${cfg.role} (${cfg.seniority}), com ${totalTurns} turnos.`
      );
    }, 350);
  };

  async function callInterviewApi(userMessage) {
    const payload = {
      session_id: cfg.sessionId,
      role: cfg.role,
      seniority: cfg.seniority,
      language: cfg.language,
      total_questions: totalTurns,
      message: userMessage,
    };

    const res = await fetch("/interviews/api/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const txt = await res.text();
      throw new Error(txt || "API error");
    }

    return res.json();
  }

  startBtn.addEventListener("click", () => {
    if (!sessionReady || sessionStarted) return;

    sessionStarted = true;

    statusEl.textContent = t(
      "Session started. Answer naturally, like a real interview.",
      "Sessão iniciada. Responde naturalmente, como numa entrevista real."
    );

    addMessage(
      "ai",
      t(
        "Hi, I'm your AI recruiter. Let's begin. Tell me briefly about yourself and why you're a good fit.",
        "Olá, sou o teu recrutador IA. Vamos começar. Apresenta-te brevemente e diz porque és uma boa opção."
      )
    );

    setChatEnabled(true);
    input.focus();
  });

  resetBtn.addEventListener("click", () => {
    resetUI();
    prepareSession();
  });

  if (resultsRestartBtn) {
    resultsRestartBtn.addEventListener("click", () => {
      resetUI();
      prepareSession();
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!sessionStarted || awaitingAi) return;

    const text = (input.value || "").trim();
    if (!text) return;

    addMessage("user", text);
    input.value = "";

    setChatEnabled(false);
    setTyping(true);

    try {
      const data = await callInterviewApi(text);

      addMessage("ai", data.reply || "...");

      if (data.done) {
        statusEl.textContent = t("Interview completed.", "Entrevista concluída.");
        setTyping(false);
        setChatEnabled(false);

        showResults({
          final_score: data.final_score,
          feedback: data.feedback,
        });

        return;
      }

      setTyping(false);
      setChatEnabled(true);
      input.focus();
    } catch (err) {
      console.error(err);
      addMessage(
        "ai",
        t(
          "Something went wrong talking to the server. Check the terminal logs.",
          "Algo correu mal ao falar com o servidor. Vê os logs no terminal."
        )
      );
      setTyping(false);
      setChatEnabled(true);
      input.focus();
    }
  });

  // INIT
  resetUI();
  prepareSession();
});
