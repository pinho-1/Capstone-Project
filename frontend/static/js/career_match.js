// ---------- ANALYZING OVERLAY + ACTIVE CARD ----------

function setActiveJobCard(btnEl) {
  const card = btnEl.closest(".cm-job-card");
  if (!card) return;

  document.querySelectorAll(".cm-job-card.cm-job-card--active").forEach((el) => {
    el.classList.remove("cm-job-card--active");
  });

  card.classList.add("cm-job-card--active");
}

// Show overlay before an HTMX request triggered by "Analyze match"
document.addEventListener("htmx:beforeRequest", function (evt) {
  const elt = evt.detail && evt.detail.elt;
  if (!elt || !elt.classList.contains("cm-job-analyze-btn")) return;

  setActiveJobCard(elt);

  const overlay = document.getElementById("cm-analyzing-overlay");
  if (overlay) overlay.classList.add("is-visible");
});

// Hide overlay after request finishes
document.addEventListener("htmx:afterRequest", function (evt) {
  const elt = evt.detail && evt.detail.elt;
  if (!elt || !elt.classList.contains("cm-job-analyze-btn")) return;

  const overlay = document.getElementById("cm-analyzing-overlay");
  if (overlay) overlay.classList.remove("is-visible");
});

// After match panel swaps, gently bring it into view on smaller screens
document.addEventListener("htmx:afterSwap", function (evt) {
  if (!evt.detail || !evt.detail.target) return;

  // only when the match panel updates
  if (evt.detail.target.id === "cm-match-panel") {
    if (window.innerWidth <= 1024) {
      evt.detail.target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  // only care when the jobs list (#cm-jobs-list) has just been swapped
  if (evt.detail.target.id !== "cm-jobs-list") return;

  const btn = document.getElementById("cm-load-more-btn");
  if (!btn) return;

  btn.onclick = function () {
    document.querySelectorAll(".cm-job-card--hidden").forEach(function (el) {
      el.classList.remove("cm-job-card--hidden");
    });
    const row = btn.closest("li");
    if (row) row.remove();
  };
});
