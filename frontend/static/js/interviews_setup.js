document.addEventListener("DOMContentLoaded", () => {
  const roleSelect = document.getElementById("role-select");
  const customRoleInput = document.getElementById("custom-role");
  const jobRoleInput = document.getElementById("job-role-input");

  const seniorityGroup = document.getElementById("seniority-group");
  const seniorityInput = document.getElementById("seniority-input");

  const languageGroup = document.getElementById("language-group");
  const languageInput = document.getElementById("language-input");

  const form = document.getElementById("interview-form");

  if (!form) return;

  const updateJobRole = () => {
    if (roleSelect.value === "custom") {
      customRoleInput.classList.remove("hidden");
      const val = customRoleInput.value.trim() || "Your chosen role";
      jobRoleInput.value = val;
    } else {
      customRoleInput.classList.add("hidden");
      const label = roleSelect.options[roleSelect.selectedIndex].text;
      jobRoleInput.value = label;
    }
  };

  roleSelect.addEventListener("change", updateJobRole);
  customRoleInput.addEventListener("input", updateJobRole);
  updateJobRole();

  const wireToggleGroup = (groupEl, hiddenInput) => {
    groupEl.addEventListener("click", (e) => {
      if (e.target.tagName !== "BUTTON") return;
      groupEl.querySelectorAll("button").forEach(btn => btn.classList.remove("active"));
      e.target.classList.add("active");
      hiddenInput.value = e.target.dataset.value;
    });
  };

  wireToggleGroup(seniorityGroup, seniorityInput);
  wireToggleGroup(languageGroup, languageInput);
});
