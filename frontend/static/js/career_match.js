// Show overlay before an HTMX request triggered by Analyze Match
document.addEventListener("htmx:beforeRequest", function (evt) {
    if (evt.target && evt.target.matches(".cm-job-analyze-btn")) {
        const overlay = document.getElementById("cm-analyzing-overlay");
        if (overlay) {
            overlay.classList.add("is-visible");
        }
    }
});

// Hide overlay after the request finishes
document.addEventListener("htmx:afterRequest", function (evt) {
    if (evt.target && evt.target.matches(".cm-job-analyze-btn")) {
        const overlay = document.getElementById("cm-analyzing-overlay");
        if (overlay) {
            overlay.classList.remove("is-visible");
        }
    }
});
