document.addEventListener("DOMContentLoaded", () => {

  // Loading overlay
  const overlay = document.getElementById("loading-overlay");
  const statusUrl = window.location.pathname.replace("/view/", "/status/");

  async function checkStatus() {
    try {
      const res = await fetch(statusUrl);
      const data = await res.json();
      if (data.status === "ready") {
        // Hide loading and refresh the page to show results
        overlay.classList.add("hidden");
        window.location.reload();
      }
    } catch (e) {
      console.error("Error checking CV status:", e);
    }
  }

  // Only start polling if the overlay is visible
  if (overlay && !overlay.classList.contains("hidden")) {
    overlay.classList.remove("hidden");
    setInterval(checkStatus, 4000); // every 4 seconds
  }

  // Observe cards stack to toggle Next Step button
  const stack = document.getElementById("cards-stack");
  const nextBtnWrapper = document.getElementById("next-step-wrapper");

  const observer = new MutationObserver(() => {
    const hasCards = stack.children.length > 0;
    nextBtnWrapper.classList.toggle("hidden", hasCards);
  });
  observer.observe(stack, { childList: true });


  // Animate score
  const scoreText = document.getElementById("score-value");
  const circle = document.querySelector(".score-circle .progress");
  if (circle && scoreText) {
    const score = parseFloat(scoreText.textContent.trim()) || 0;
    const radius = 45, circumference = 2 * Math.PI * radius;
    circle.style.strokeDasharray = `${circumference}`;
    circle.style.strokeDashoffset = `${circumference}`;
    requestAnimationFrame(() => {
      const target = circumference * (1 - score / 100);
      circle.style.strokeDashoffset = target;
    });
  }

  // Animate subscore bars
  document.querySelectorAll(".fill").forEach((bar, i) =>
    setTimeout(() => (bar.style.width = `${bar.dataset.target}%`), i * 400)
  );

  // Toggle reasons
  document.querySelectorAll(".toggle-btn").forEach(btn =>
    btn.addEventListener("click", () => {
      const reason = btn.closest("li").querySelector(".reason");
      const open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", !open);
      reason.classList.toggle("visible");
    })
  );
});
