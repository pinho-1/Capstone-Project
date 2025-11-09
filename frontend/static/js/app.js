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

// ========= CONFIG =========
const NAV_VAR = 80; // define isto no :root { --nav-h: 88px; }

// Helper: devolve o scroller certo
function getScroller() {
  return document.querySelector('.page') || document.scrollingElement || document.documentElement;
}

// Helper: scroll suave com offset da navbar
function smoothScrollToEl(el) {
  if (!el) return;
  const scroller = getScroller();
  const navOffset = parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue(NAV_VAR)
  ) || 88;

  const rect = el.getBoundingClientRect();
  const y = (scroller.scrollTop || 0) + rect.top - navOffset;

  scroller.scrollTo({ top: y, behavior: 'smooth' });
}

// ========= 1) LINKS DA NAV QUANDO JÁ ESTÁS NA HOME =========
document.querySelectorAll('a[href^="/#"]').forEach(link => {
  link.addEventListener('click', (e) => {
    if (window.location.pathname !== "/") return; // se não for home, deixa navegar
    e.preventDefault();
    const sel = link.getAttribute('href').replace('/', ''); // "/#features" -> "#features"
    smoothScrollToEl(document.querySelector(sel));
  });
});

// ========= 2) VINDO DE OUTRA PÁGINA: LÊ O HASH AO CHEGAR =========
function scrollToHashOnLoad() {
  if (window.location.pathname !== "/") return;
  const hash = window.location.hash;
  if (!hash) return;

  const el = document.querySelector(hash);
  if (!el) return;

  // Evita o “salto seco” padrão e faz o suave com layout já estável
  history.scrollRestoration = 'manual';

  // Espera o layout estabilizar (fonts/imagens) e depois rola suave
  const run = () => smoothScrollToEl(el);
  if (document.readyState === 'complete') {
    // página já carregada
    setTimeout(run, 0);
  } else {
    // espera o load para garantir medidas corretas
    window.addEventListener('load', () => setTimeout(run, 0), { once: true });
  }
}
scrollToHashOnLoad();



