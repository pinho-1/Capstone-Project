// === HERO SECTION ANIMATION ===
function animateHero() {
  const hero = document.querySelector(".hero");
  if (!hero) return;
  const position = hero.getBoundingClientRect().top;
  if (position < window.innerHeight / 1.2) {
    hero.classList.add("animate");
  }
}

window.addEventListener("load", () => {
  if (performance.getEntriesByType("navigation")[0]?.type !== "reload") {
    window.scrollTo(0, 0);
  }
  animateHero();
});

window.addEventListener("scroll", animateHero);

// === FEATURES FADE-IN ===
const features = document.querySelectorAll('.feature');
function revealFeatures() {
  features.forEach(feature => {
    const top = feature.getBoundingClientRect().top;
    if (top < window.innerHeight - 200) feature.classList.add('visible');
  });
}
window.addEventListener('scroll', revealFeatures);
window.addEventListener('load', revealFeatures);

// === HOW IT WORKS FADE-IN ===
const steps = document.querySelectorAll('.step, .wave-connector, .how-title, .how-subtitle');
function revealSteps() {
  steps.forEach((el, i) => {
    const top = el.getBoundingClientRect().top;
    if (top < window.innerHeight - 200) {
      el.classList.add('visible');
      el.style.transitionDelay = `${i * 0.15}s`;
    }
  });
}
window.addEventListener('scroll', revealSteps);
window.addEventListener('load', revealSteps);

// Remove ?welcome or ?goodbye from the URL after showing flash message
window.addEventListener("DOMContentLoaded", () => {
  const flash = document.querySelector(".flash");

  if (flash) {
    // Let it live for 4 seconds (matches CSS animation)
    setTimeout(() => {
      try {
        const url = new URL(window.location);
        if (url.searchParams.has("welcome") || url.searchParams.has("goodbye")) {
          url.searchParams.delete("welcome");
          url.searchParams.delete("goodbye");
          window.history.replaceState({}, document.title, url.pathname + url.search);
        }
      } catch (err) {
        console.warn("URL cleanup failed:", err);
      }
    }, 2000);
  }
});

// Word Switcher in Hero Section
document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("journey-btn");
  if (!btn) return;

  const params = new URLSearchParams(window.location.search);
  const justLoggedIn = params.has("welcome"); // your existing convention

  // Only run the morph if user is logged in AND we just came from login
  // Heuristic: on this render href should already be /dashboard (user state)
  if (!justLoggedIn || btn.getAttribute("href") !== "/dashboard") return;

  const prevWord = "Start";
  const nextWord = "Continue";

  // Figure out the suffix (everything after the first word)
  // We expect either "Start Your Journey" or "Continue Your Journey"
  const full = btn.textContent.trim();
  const suffix = full.replace(/^(Start|Continue)\s*/i, " "); // keeps the leading space
  // Force the starting state visually to "Start ..." so we can animate the swap
  btn.textContent = prevWord + suffix;

  // Optional: prevent layout jitter by fixing min-width to the longer text
  const measure = document.createElement("span");
  measure.style.visibility = "hidden";
  measure.style.position = "fixed";
  measure.style.whiteSpace = "nowrap";
  measure.textContent = nextWord + suffix;
  document.body.appendChild(measure);
  const targetWidth = measure.getBoundingClientRect().width;
  document.body.removeChild(measure);
  btn.style.minWidth = Math.ceil(targetWidth) + "px";

  // Typewriter timing
  const ERASE_MS = 200;
  const TYPE_MS  = 200;

  // Erase "Start"
  let i = prevWord.length;
  const erase = () => {
    if (i > 0) {
      // Replace the first i chars with one fewer, keep suffix intact
      btn.textContent = prevWord.slice(0, i - 1) + suffix;
      i--;
      setTimeout(erase, ERASE_MS);
    } else {
      type();
    }
  };

  // Type "Continue"
  let j = 0;
  const type = () => {
    if (j < nextWord.length) {
      btn.textContent = nextWord.slice(0, j + 1) + suffix;
      j++;
      setTimeout(type, TYPE_MS);
    } else {
      // Done typing: ensure the link points to dashboard (it already should)
      btn.setAttribute("href", "/dashboard");

      // Remove ?welcome=... so it doesn't run again on refresh
      const url = new URL(window.location.href);
      url.searchParams.delete("welcome");
      window.history.replaceState({}, "", url.toString());
    }
  };

  setTimeout(erase, 2500); // adjust timing to match your hero slide duration
});

// Scroll Indicator Click Handler
document.querySelector(".scroll-indicator")?.addEventListener("click", () => {
  window.scrollTo({ top: window.innerHeight, behavior: "smooth" });
});

