document.addEventListener("DOMContentLoaded", () => {
  const steps = document.querySelectorAll(".step");
  const nextBtn = document.querySelector(".next");
  const prevBtn = document.querySelector(".prev");
  const progress = document.querySelector(".progress");
  const range = document.getElementById("experienceRange");
  const expValue = document.getElementById("expValue");
  const messageBox = document.querySelector(".transition-message");
  let current = 0;

  const data = JSON.parse(document.getElementById("page-data").textContent);
  const userExperience = data.userExperience;
  const isUpdate = data.isUpdate;

  
  const answers = {
    career_stage: null,
    interest: null,
    goal: null,
    experience: null,
    focus: null,
  };

  // --- PRELOAD EXPERIENCE (works for both new and returning users) ---
  let initialExperience = 2; // default for fresh accounts
  if (typeof userExperience !== "undefined" && userExperience !== null && !Number.isNaN(Number(userExperience))) {
    initialExperience = Number(userExperience);
  }

  if (range) {
    range.value = initialExperience;
    if (expValue) expValue.textContent = String(initialExperience);

    const pct = (Number(range.value) / Number(range.max)) * 100;
    range.style.setProperty("--progress", `${pct}%`);
  }
  answers.experience = initialExperience;
  
  const messages = isUpdate
  ? [
      "Let’s refresh things a bit.",
      "Nice time to realign your interests.",
      "Let’s tweak your goals to match where you’re heading.",
      "Update your experience so we keep up with your growth.",
      "Almost done. A quick check-in on your focus areas.", 
    ]
  : [
      "Let’s take the first step.",
      "Love it. Now, what inspires you most?",
      "Great choice. Let's set your goal next.",
      "Almost done. Tell us about your experience.",
      "This last bit helps us personalize things for you.",
    ];

  function updateSteps() {
    steps.forEach((step, i) => step.classList.toggle("active", i === current));
    prevBtn.disabled = current === 0;
    if (current === steps.length - 1) {
      nextBtn.style.display = "none";
      prevBtn.style.display = "none"; // hide Back button on last step
    } else {
      nextBtn.style.display = "inline-block";
      prevBtn.style.display = "inline-block";
    }
    progress.style.width = ((current + 1) / steps.length) * 100 + "%";

    if (messageBox && messages[current]) {
      messageBox.textContent = messages[current];
      messageBox.classList.add("visible");
      setTimeout(() => messageBox.classList.remove("visible"), 5000);
    }
  }

  nextBtn.addEventListener("click", () => {
    const stepEl = steps[current];
    const selectedBtns = stepEl.querySelectorAll(".options button.selected");
    const validationMsg = stepEl.querySelector(".validation-message");

    // clear message before next step
    if (validationMsg) validationMsg.classList.remove("visible");

    // only validate steps with options
    const needsSelection = stepEl.querySelector(".options");
    const stepNum = parseInt(stepEl.dataset.step);
    if (needsSelection && selectedBtns.length === 0 && current < 3) {
      if (validationMsg) {
        // Different message for multi-choice Step 2
        validationMsg.textContent =
          stepNum === 2
            ? "Select at least one option. This helps us better understand your interests."
            : "Take a moment to choose one. It helps us tailor things for you.";
        validationMsg.classList.add("visible");

        // auto-hide after 2 seconds
        setTimeout(() => {
          validationMsg.classList.remove("visible");
        }, 4000);
      }
      return; // stop progression
    }

    if (selectedBtns.length > 0) {
      const stepNum = parseInt(stepEl.dataset.step);
      if (stepNum === 1) answers.career_stage = selectedBtns[0].textContent;
      if (stepNum === 2){
        const selectedValues = Array.from(selectedBtns).map(btn => btn.textContent.trim());
        answers.interest = selectedValues.join(",");
      }
      if (stepNum === 3) answers.goal = selectedBtns[0].textContent;
    }

    if (range && stepEl.dataset.step === "4") {
      answers.experience = range.value;
    }

    if (stepEl.dataset.step === "5") {
      answers.focus = stepEl.querySelector("textarea").value;
    }

    if (current < steps.length - 1) {
      current++;
      updateSteps();

      if (current === steps.length - 1) {
        setTimeout(() => {
          const form = document.createElement("form");
          form.method = "POST";
          form.action = "/onboarding/submit";

          const appendField = (name, value) => {
            const input = document.createElement("input");
            input.type = "hidden";
            input.name = name;
            input.value = value;
            form.appendChild(input);
          };

          Object.entries(answers).forEach(([key, val]) =>
            appendField(key, val)
          );

          document.body.appendChild(form);
          form.submit();
        }, 4000);
      }
    }
  });


  prevBtn.addEventListener("click", () => {
    if (current > 0) {
      current--;
      updateSteps();
    }
  });

  range?.addEventListener("input", () => {
    expValue.textContent = range.value;
  });

  range?.addEventListener("input", () => {
    expValue.textContent = range.value;
    const progress = (range.value / range.max) * 100;
    range.style.setProperty("--progress", `${progress}%`);
  });

  document.querySelectorAll(".options button").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const group = e.target.closest(".options");
      const stepEl = e.target.closest(".step");
      const stepNum = parseInt(stepEl.dataset.step);

      if (stepNum === 2) {
        // Step 2 = multiple choice (toggle)
        e.target.classList.toggle("selected");
      } else {
        // Single choice for other steps
        group.querySelectorAll("button").forEach((b) => b.classList.remove("selected"));
        e.target.classList.add("selected");
      }
    });
  });
  updateSteps();
});
