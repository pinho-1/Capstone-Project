// === HERO SEQUENCE ===
window.addEventListener('DOMContentLoaded', () => {
  const hero = document.querySelector('.upload-header.hero');
  if (hero) {
    const micro = hero.querySelector('.microtag');
    const title = hero.querySelector('.hero-title');
    const tag   = hero.querySelector('.hero-tagline');
    const line  = hero.querySelector('.hero-divider');

    const steps = [
      [micro, 100],
      [title, 600],
      [tag,   850],
      [line,  1200],
    ];

    steps.forEach(([el, delay]) => {
      if (!el) return;
      setTimeout(() => el.classList.add('show'), delay);
    });
  }

  // === UPLOAD FUNCTIONALITY ===
  const uploadWrapper = document.querySelector('.upload-area');
  const fileInput = document.getElementById('cv-file');
  const form = document.getElementById('upload-form');
  const feedback = document.getElementById('upload-feedback');

  if (!uploadWrapper || !fileInput || !form) return;

  // --- Drag and Drop ---
  ['dragenter', 'dragover'].forEach(evt => {
    uploadWrapper.addEventListener(evt, e => {
      e.preventDefault();
      uploadWrapper.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    uploadWrapper.addEventListener(evt, e => {
      e.preventDefault();
      uploadWrapper.classList.remove('dragover');
    });
  });

  uploadWrapper.addEventListener('drop', e => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      fileInput.files = files;
      submitUpload(form, feedback);
    }
  });

  // --- Regular Click Upload ---
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      submitUpload(form, feedback);
    }
  });
});

// === SUBMIT FUNCTION ===
function submitUpload(form, feedback) {
  if (feedback) {
    feedback.innerHTML = `
      <div class="uploading">
        Uploading<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
      </div>`;
  }

  setTimeout(() => {
    document.body.classList.add('fade-out');
    setTimeout(() => form.submit(), 800);
  }, 1000);
}

// === FADE CSS INJECTION ===
document.body.insertAdjacentHTML('beforeend', `
  <style>
    body.fade-out { opacity: 0; transition: opacity 0.6s ease; }
  </style>
`);
