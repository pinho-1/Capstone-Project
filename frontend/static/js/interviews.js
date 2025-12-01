document.addEventListener("DOMContentLoaded", () => {
  const roleSelect = document.getElementById("role-select");
  const customRoleInput = document.getElementById("custom-role");
  const seniorityGroup = document.getElementById("seniority-group");
  const languageGroup = document.getElementById("language-group");
  const questionCountSelect = document.getElementById("question-count");

  const startBtn = document.getElementById("start-btn");
  const statusEl = document.getElementById("interview-status");
  const voiceBtn = document.getElementById("voice-toggle-btn");
  const statusDot = document.getElementById("voice-status-dot");
  const aiCircle = document.getElementById("ai-circle");

  // If we're not on the interviews page, do nothing
  if (!roleSelect || !startBtn || !voiceBtn) return;

  let sessionReady = false;
  let listening = false;
  let aiSpeaking = false;

  // ===== Helpers =====

  const getActiveValue = groupEl => {
    const activeBtn = groupEl.querySelector("button.active");
    return activeBtn ? activeBtn.dataset.value : null;
  };

  const setAISpeaking = isSpeaking => {
    aiSpeaking = isSpeaking;
    if (!aiCircle) return;
    aiCircle.classList.toggle("speaking", aiSpeaking);
  };

  const setListening = isOn => {
    listening = isOn;
    voiceBtn.classList.toggle("active", listening);
    statusDot.classList.toggle("active", listening);
    voiceBtn.querySelector(".mic-label").textContent = listening
      ? "Stop voice session"
      : "Start voice session";
    statusEl.textContent = listening
      ? "Listening… answer the questions as if you were in a real interview."
      : "Session ready. Press the mic to continue.";

    // If we stop listening, make sure AI circle stops too
    if (!listening) {
      setAISpeaking(false);
    }
  };

  // ===== UI: select role (show/hide custom input) =====

  roleSelect.addEventListener("change", () => {
    if (roleSelect.value === "custom") {
      customRoleInput.classList.remove("hidden");
    } else {
      customRoleInput.classList.add("hidden");
    }
  });

  // ===== UI: toggle groups (seniority + language) =====

  document.querySelectorAll(".toggle-group").forEach(group => {
    group.addEventListener("click", e => {
      if (e.target.tagName !== "BUTTON") return;
      group.querySelectorAll("button").forEach(btn =>
        btn.classList.remove("active")
      );
      e.target.classList.add("active");
    });
  });

  // ===== Start / prepare interview (no LLM yet, just UI state) =====

  startBtn.addEventListener("click", () => {
    const role =
      roleSelect.value === "custom"
        ? (customRoleInput.value.trim() || "your target role")
        : roleSelect.options[roleSelect.selectedIndex].text;

    const seniority = getActiveValue(seniorityGroup) || "junior";
    const language = getActiveValue(languageGroup) || "en";
    const questionCount = parseInt(questionCountSelect.value) || 5;

    // Here later you will call your backend:
    // await fetch("/api/interview/start", { method: "POST", body: JSON.stringify({...}) })

    sessionReady = true;
    voiceBtn.disabled = false;
    setListening(false);

    statusEl.textContent =
      language === "pt"
        ? `Entrevista preparada para ${role} (${seniority}), com ${questionCount} perguntas. Carrega no microfone para começar.`
        : `Interview prepared for ${role} (${seniority}), with ${questionCount} questions. Press the mic to start.`;
  });

  // ===== Toggle microphone (later: hook ElevenLabs here) =====

  voiceBtn.addEventListener("click", () => {
    if (!sessionReady || voiceBtn.disabled) return;

    // Later you will:
    // - start / stop audio stream to ElevenLabs
    // - notify backend about listening state
    const nextListening = !listening;
    setListening(nextListening);

    // TEMP DEMO: when we start listening, make the AI circle pulse for 3s
    if (nextListening) {
      setAISpeaking(true);
      setTimeout(() => setAISpeaking(false), 3000);
    }
  });
});
