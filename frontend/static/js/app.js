// === NAVBAR SLIDE-IN ON LOAD + SHOW ONLY AT TOP ===
const navbar = document.querySelector(".navbar");

// Wait until the page is ready to reveal the navbar
window.addEventListener("DOMContentLoaded", () => {
  setTimeout(() => {
    navbar.classList.add("visible");
  }, 0); // short delay for smooth entry
});

// Hide/show based on scroll position
window.addEventListener("scroll", () => {
  if (window.scrollY > 50) {
    navbar?.classList.remove("visible");
  } else {
    navbar?.classList.add("visible");
  }
});

// === FOOTER FADE-IN ===
const footerContent = document.querySelector('.footer-content');

function revealFooterContent() {
  if (!footerContent) return;
  const top = footerContent.getBoundingClientRect().top;
  if (top < window.innerHeight - 100) {
    footerContent.classList.add('visible');
  }
}

window.addEventListener('scroll', revealFooterContent);
window.addEventListener('load', revealFooterContent);

// Logget Out Nav Links 
document.querySelectorAll('a[href^="/#"]').forEach(link => {
  link.addEventListener('click', function(e) {
    if (window.location.pathname !== "/") return; // if not on home, let it reload
    e.preventDefault();
    const target = document.querySelector(this.getAttribute('href').replace('/', ''));
    if (target) {
      window.scrollTo({
        top: target.offsetTop - 100, // adjust for navbar height
        behavior: 'smooth'
      });
    }
  });
});


