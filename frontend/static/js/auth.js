// === AUTH FORM TOGGLE WITH SLIDE ANIMATION ===
const loginForm = document.getElementById('login-form');
const signupForm = document.getElementById('signup-form');
const formTitle = document.getElementById('form-title');
const toSignup = document.getElementById('to-signup');
const toLogin = document.getElementById('to-login');

function switchForm(showLogin) {
  if (!loginForm || !signupForm) return;

  // Add direction classes for slide animation
  if (showLogin) {
    signupForm.classList.add('slide-out-right');
    loginForm.classList.add('slide-in-left');
  } else {
    loginForm.classList.add('slide-out-left');
    signupForm.classList.add('slide-in-right');
  }

  // Wait for animation to finish before toggling visibility
  setTimeout(() => {
    loginForm.classList.toggle('active', showLogin);
    signupForm.classList.toggle('active', !showLogin);

    // Reset animation classes
    loginForm.classList.remove('slide-in-left', 'slide-out-left');
    signupForm.classList.remove('slide-in-right', 'slide-out-right');

    formTitle.textContent = showLogin ? 'Welcome back' : 'Create Account';
  }, 400); // match CSS animation duration
}

toSignup?.addEventListener('click', () => switchForm(false));
toLogin?.addEventListener('click', () => switchForm(true));

// === INLINE SVG PASSWORD TOGGLE ===
document.querySelectorAll('.toggle-visibility').forEach(btn => {
  const targetId = btn.getAttribute('data-target');
  const input = document.getElementById(targetId);
  const eye = btn.querySelector('.eye');
  const eyeOff = btn.querySelector('.eye-off');

  if (!input) return;

  btn.addEventListener('click', () => {
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.setAttribute('aria-pressed', String(show));
    // swap icons
    eye.style.display = show ? 'none' : 'block';
    eyeOff.style.display = show ? 'block' : 'none';
    // keep focus on the field for decent UX
    input.focus({ preventScroll: true });
    // put cursor at end
    const val = input.value;
    input.value = '';
    input.value = val;
  });
});

// === PASSWORD MATCH CHECK ===
const password = document.querySelector('#signup-form input[name="password"]');
const confirm = document.querySelector('#signup-form input[name="confirm_password"]');
const message = document.getElementById('password-match-message');

if (password && confirm && message) {
  confirm.addEventListener('input', () => {
    message.classList.add('visible');
    if (confirm.value === '') {
      message.textContent = '';
      message.style.color = '';
      message.classList.remove('visible');
    } else if (confirm.value === password.value) {
      message.textContent = 'Passwords Match';
      message.style.color = 'green';
    } else {
      message.textContent = 'Passwords do not Match';
      message.style.color = 'red';
    }
  });
}

// === CLEAR FEEDBACK MESSAGES AFTER 5 SECONDS ===
window.addEventListener('load', () => {
  const params = new URLSearchParams(window.location.search);
  const error = params.get("error");

  if (error) {
    const alertBox = document.createElement("div");
    alertBox.className = "feedback error";
    let messageText = "";

    switch (error) {
      case "invalid_credentials":
        messageText = "Invalid email or password. Please try again.";
        break;
      case "email_exists":
        messageText = "This email is already registered. Try logging in.";
        break;
      case "missing_fields":
        messageText = "Please fill in all required fields.";
        break;
      case "login_required":
        messageText = "Log in required to access that page.";
        break;
      default:
        messageText = "Something went wrong. Please try again.";
    }

    alertBox.textContent = messageText;
    document.body.appendChild(alertBox);

    // Fade away after 5s
    setTimeout(() => {
      alertBox.classList.add('fade-out');
      setTimeout(() => alertBox.remove(), 600);
    }, 5000);
  }
});
