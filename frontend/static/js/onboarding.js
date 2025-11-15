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
    other_interest: null,
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

    // Enable or disable Back button
    if (current === 0) {
      if (isUpdate) {
        prevBtn.classList.remove('disabled');
        prevBtn.removeAttribute("disabled");
      } else {
        prevBtn.classList.add('disabled');
        prevBtn.setAttribute("disabled", "true");
      }
    } else {
      prevBtn.classList.remove('disabled');
      prevBtn.removeAttribute("disabled");
    }

    // Show Next/Previous buttons based on steps
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
    const stepNum = parseInt(stepEl.dataset.step, 10);

    // clear message before next step
    if (validationMsg) validationMsg.classList.remove("visible");

    // --- Step 2: handle "Other" field ---
    let otherValue = "";
    if (stepNum === 2) {
      const otherInput = stepEl.querySelector(".other-interest-input");
      if (otherInput) {
        otherValue = otherInput.value.trim();
      }
    }
    const hasOtherInterest = stepNum === 2 && otherValue !== "";

    // only validate steps with options
    const needsSelection = stepEl.querySelector(".options");

    // for steps 1–3, require at least one choice,
    // EXCEPT step 2 where "Other" alone is enough
    if (
      needsSelection &&
      selectedBtns.length === 0 &&
      current < 3 &&
      !hasOtherInterest
    ) {
      if (validationMsg) {
        validationMsg.textContent =
          stepNum === 2
            ? "Select at least one option or write your own area. This helps us better understand your interests."
            : "Take a moment to choose one. It helps us tailor things for you.";
        validationMsg.classList.add("visible");

        setTimeout(() => {
          validationMsg.classList.remove("visible");
        }, 4000);
      }
      return; // stop progression
    }

    // --- Save answers from the current step ---
    if (stepNum === 1 && selectedBtns.length > 0) {
      answers.career_stage = selectedBtns[0].textContent;
    }

    if (stepNum === 2) {
      // multiple choice interests
      const selectedValues = Array.from(selectedBtns).map((btn) =>
        btn.textContent.trim()
      );
      answers.interest =
        selectedValues.length > 0 ? selectedValues.join(",") : null;

      // save "Other" (even if no buttons selected)
      answers.other_interest = otherValue || null;
    }

    if (stepNum === 3 && selectedBtns.length > 0) {
      answers.goal = selectedBtns[0].textContent;
    }

    if (range && stepEl.dataset.step === "4") {
      answers.experience = range.value;
    }

    if (stepEl.dataset.step === "5") {
      const focusText = stepEl.querySelector("textarea");
      answers.focus = focusText ? focusText.value : null;
    }

    // --- Move to next step / auto-submit at the end ---
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
            input.value = value ?? "";
            form.appendChild(input);
          };

          Object.entries(answers).forEach(([key, val]) => appendField(key, val));

          document.body.appendChild(form);
          form.submit();
        }, 4000);
      }
    }
  });

  prevBtn.addEventListener("click", () => {
    if (current === 0 && isUpdate) {
      // If we're on Step 1 in update mode, go back to the homepage
      window.location.href = '/';
    } else if (current > 0) {
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

  // --- Accordion for Step 2 interest categories ---
  const interestStep = document.querySelector('.step[data-step="2"]');
  if (interestStep) {
    const categoriesEls = interestStep.querySelectorAll('.interest-category');

    categoriesEls.forEach((cat, index) => {
      const header = cat.querySelector('h3');
      const options = cat.querySelector('.options');
      if (!header || !options) return;

      // Auto-open if:
      // - it's the first category, or
      // - it already has selected buttons, or
      // - it has a filled "Other" input
      const hasSelected = options.querySelector('button.selected');
      const otherInput = options.querySelector('.other-interest-input');
      const hasOtherValue = otherInput && otherInput.value.trim() !== "";

      if (index === 0 || hasSelected || hasOtherValue) {
        cat.classList.add('open');
      } else {
        cat.classList.remove('open');
      }

      // Toggle on header click
      header.addEventListener('click', () => {
        cat.classList.toggle('open');
      });
    });
  }


  updateSteps();
});