document.addEventListener("DOMContentLoaded", () => {

  // Loading overlay
  const overlay = document.getElementById("loading-overlay");
  const statusUrl = window.location.pathname.replace("/view/", "/status/");

  // --- Page load reveal (skip if overlay is showing) ---
  const dash = document.querySelector(".cv-dashboard");
  if (!overlay || overlay.classList.contains("hidden")) {
    requestAnimationFrame(() => dash?.classList.add("is-loaded"));
  }

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

  // Topic card animation
  document.body.addEventListener("htmx:afterSwap", (e) => {
    // Only when we append into the stack
    if (e.target && e.target.id === "cards-stack") {
      const cards = e.target.querySelectorAll(".topic-card");
      const newest = cards[cards.length - 1];
      if (newest) {
        newest.classList.add("pop");
        setTimeout(() => newest.classList.remove("pop"), 300);
        newest.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  });

  // Keep maximum of 3 cards
  (function () {
    const MAX_CARDS = 3;

    function stack() {
      return document.querySelector("#cards-stack");
    }

    function activeCardCount() {
      const s = document.querySelector("#cards-stack");
      if (!s) return 0;
      return s.querySelectorAll('.topic-card[data-status="active"]').length;
    }


    function getHtmxUrl(el) {
      if (!el) return "";

      // HTMX can use hx-* or data-hx-* attributes
      const hxPost = el.getAttribute("hx-post") || el.getAttribute("data-hx-post");
      const hxGet  = el.getAttribute("hx-get")  || el.getAttribute("data-hx-get");

      // If click is on a child (icon/span), walk up
      if (!hxPost && !hxGet) {
        const owner = el.closest("[hx-post],[data-hx-post],[hx-get],[data-hx-get]");
        if (!owner) return "";
        return (
          owner.getAttribute("hx-post") || owner.getAttribute("data-hx-post") ||
          owner.getAttribute("hx-get")  || owner.getAttribute("data-hx-get")  ||
          ""
        );
      }

      return hxPost || hxGet || "";
    }

    function isAddCardRequest(url) {
      // handle possible querystrings
      return url.startsWith("/cv/intent") || url.startsWith("/cv/next-action");
    }

    function showLimitWarning() {
      const el = document.querySelector("#cards-limit-warning");
      if (!el) return;

      el.hidden = false;
      el.classList.remove("pop");
      void el.offsetWidth; // replay animation
      el.classList.add("pop");

      clearTimeout(showLimitWarning._t);
      showLimitWarning._t = setTimeout(() => (el.hidden = true), 5000);
    }

    // Block before request is sent
    document.body.addEventListener("htmx:beforeRequest", (e) => {
      const triggerEl = e.detail.elt;            // usually form/button
      const url = getHtmxUrl(triggerEl);

      if (!url) return;
      if (!isAddCardRequest(url)) return;

      if (activeCardCount() >= MAX_CARDS) {
        e.preventDefault();
        showLimitWarning();
      }
    });

    // Hide warning when cards drop below max (dismissed)
    document.body.addEventListener("htmx:afterSwap", () => {
      const el = document.querySelector("#cards-limit-warning");
      if (!el) return;
      if (activeCardCount() < MAX_CARDS) el.hidden = true;
    });
  })();

});
