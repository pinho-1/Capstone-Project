// ---------- ANALYZING OVERLAY ----------

// Show overlay before an HTMX request triggered by "Analyze match"
document.addEventListener("htmx:beforeRequest", function (evt) {
  const elt = evt.detail && evt.detail.elt;
  if (!elt || !elt.classList.contains("cm-job-analyze-btn")) return;

  const overlay = document.getElementById("cm-analyzing-overlay");
  if (overlay) {
    overlay.classList.add("is-visible");
  }
});

// Hide overlay after the request finishes
document.addEventListener("htmx:afterRequest", function (evt) {
  const elt = evt.detail && evt.detail.elt;
  if (!elt || !elt.classList.contains("cm-job-analyze-btn")) return;

  const overlay = document.getElementById("cm-analyzing-overlay");
  if (overlay) {
    overlay.classList.remove("is-visible");
  }
});

// ---------- "LOAD MORE" HANDLER ----------

document.addEventListener("htmx:afterSwap", function (evt) {
  // only care when the jobs list (#cm-jobs-list) has just been swapped
  if (!evt.detail || evt.detail.target.id !== "cm-jobs-list") return;

  const btn = document.getElementById("cm-load-more-btn");
  if (!btn) return;

  btn.onclick = function () {
    document.querySelectorAll(".cm-job-card--hidden").forEach(function (el) {
      el.classList.remove("cm-job-card--hidden");
    });
    btn.closest("li").remove();
  };
});
