document.addEventListener("DOMContentLoaded", () => {
  const voiceBtn = document.getElementById("voice-toggle-btn");
  const statusEl = document.getElementById("interview-status");
  const statusDot = document.getElementById("voice-status-dot");
  const aiCircle = document.getElementById("ai-circle");

  if (!voiceBtn || !statusEl) return;

  let sessionReady = false;
  let listening = false;
  let aiSpeaking = false;

  const cfg = window.INTERVIEW_CONFIG || {};
  const lang = cfg.language || "en";

  const setAISpeaking = (isSpeaking) => {
    aiSpeaking = isSpeaking;
    if (!aiCircle) return;
    aiCircle.classList.toggle("speaking", aiSpeaking);
  };

  const setListening = (isOn) => {
    listening = isOn;
    voiceBtn.classList.toggle("active", listening);
    statusDot.classList.toggle("active", listening);

    voiceBtn.querySelector(".mic-label").textContent = listening
      ? (lang === "pt" ? "Parar sessão de voz" : "Stop voice session")
      : (lang === "pt" ? "Iniciar sessão de voz" : "Start voice session");

    statusEl.textContent = listening
      ? (lang === "pt"
          ? "A ouvir… responde como se estivesses numa entrevista real."
          : "Listening… answer the questions as if you were in a real interview.")
      : (lang === "pt"
          ? "Sessão pronta. Carrega no microfone para continuar."
          : "Session ready. Press the mic to continue.");

    if (!listening) {
      setAISpeaking(false);
    }
  };

  // Fake "preparing" delay – later plug your backend / LLM here
  setTimeout(() => {
    sessionReady = true;
    voiceBtn.disabled = false;

    const preparedMsgEn =
      `Interview prepared for ${cfg.role} (${cfg.seniority}), ` +
      `with ${cfg.questionCount} questions. Press the mic to start.`;

    const preparedMsgPt =
      `Entrevista preparada para ${cfg.role} (${cfg.seniority}), ` +
      `com ${cfg.questionCount} perguntas. Carrega no microfone para começar.`;

    statusEl.textContent = (lang === "pt" ? preparedMsgPt : preparedMsgEn);
  }, 600);

  voiceBtn.addEventListener("click", () => {
    if (!sessionReady || voiceBtn.disabled) return;

    const nextListening = !listening;
    setListening(nextListening);

    // TEMP DEMO: make AI bubble pulse for 3s when starting
    if (nextListening) {
      setAISpeaking(true);
      setTimeout(() => setAISpeaking(false), 3000);
    }

    // 🔊 here is where you'll later:
    // - start / stop ElevenLabs realtime stream
    // - send audio to backend
    // - receive AI audio back
  });
});
