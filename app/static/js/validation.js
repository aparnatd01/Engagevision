/**
 * validation.js — ENGAGEVISION Sprint 1
 * Client-side form validation for:
 *   - Add / Edit Teacher form (Admin)
 *   - Login form (also inlined in login.html but duplicated here for consistency)
 *
 * Called automatically when DOM is ready if #teacherForm is present.
 */

'use strict';

/* ══════════════════════════════════════════════
   HELPERS
══════════════════════════════════════════════ */

/**
 * Show a field error message and mark the input red.
 * @param {HTMLElement} input
 * @param {string}      message
 */
function showFieldError(input, message) {
  input.classList.add('is-invalid');
  const errEl = document.getElementById(input.id + 'Error');
  if (errEl) {
    errEl.textContent = message;
    errEl.style.display = 'block';
  }
}

/**
 * Clear a field error.
 * @param {HTMLElement} input
 */
function clearFieldError(input) {
  input.classList.remove('is-invalid');
  const errEl = document.getElementById(input.id + 'Error');
  if (errEl) {
    errEl.textContent = '';
    errEl.style.display = 'none';
  }
}

/**
 * Basic email format check.
 * @param {string} email
 * @returns {boolean}
 */
function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Phone: optional but if present must be digits / +/- / spaces / parentheses.
 * @param {string} phone
 * @returns {boolean}
 */
function isValidPhone(phone) {
  return /^[\d\s\+\-\(\)]{7,20}$/.test(phone);
}

/**
 * Password strength: min 8 chars, 1 uppercase, 1 digit.
 * @param {string} pw
 * @returns {{ ok: boolean, message: string }}
 */
function validatePasswordStrength(pw) {
  if (!pw)              return { ok: false, message: 'Password is required.' };
  if (pw.length < 8)   return { ok: false, message: 'Password must be at least 8 characters.' };
  if (!/[A-Z]/.test(pw)) return { ok: false, message: 'Password must contain at least one uppercase letter.' };
  if (!/[0-9]/.test(pw)) return { ok: false, message: 'Password must contain at least one digit.' };
  return { ok: true, message: '' };
}


/* ══════════════════════════════════════════════
   PASSWORD TOGGLE (Teacher Form)
══════════════════════════════════════════════ */

function toggleTeacherPassword(inputId, iconId) {
  const input = document.getElementById(inputId);
  const icon  = document.getElementById(iconId);
  if (!input || !icon) return;
  if (input.type === 'password') {
    input.type = 'text';
    icon.classList.replace('fa-eye', 'fa-eye-slash');
  } else {
    input.type = 'password';
    icon.classList.replace('fa-eye-slash', 'fa-eye');
  }
}


/* ══════════════════════════════════════════════
   TEACHER FORM VALIDATION
══════════════════════════════════════════════ */

function validateTeacherForm(e) {
  const form   = document.getElementById('teacherForm');
  if (!form) return;

  let valid = true;

  /* Helper: validate one field */
  function check(id, testFn, message) {
    const el = document.getElementById(id);
    if (!el) return;
    clearFieldError(el);
    if (!testFn(el.value)) {
      showFieldError(el, message);
      valid = false;
    }
  }

  // First name
  check('first_name', v => v.trim().length > 0, 'First name is required.');

  // Last name
  check('last_name', v => v.trim().length > 0, 'Last name is required.');

  // Username: 3–50 chars, letters/digits/underscores only
  check('username',
    v => /^[A-Za-z0-9_]{3,50}$/.test(v.trim()),
    'Username must be 3–50 characters (letters, digits, underscores only).'
  );

  // Email
  check('email',
    v => isValidEmail(v.trim()),
    'A valid email address is required.'
  );

  // Staff ID: required, alphanumeric
  const staffEl = document.getElementById('staff_id');
  if (staffEl && staffEl.value.trim() !== '') {
    clearFieldError(staffEl);
  } else if (staffEl) {
    // Staff ID is required
    showFieldError(staffEl, 'Staff ID is required.');
    valid = false;
  }

  // Department (optional — skip if empty)
  // Phone (optional — validate format if provided)
  const phoneEl = document.getElementById('phone');
  if (phoneEl && phoneEl.value.trim() !== '') {
    clearFieldError(phoneEl);
    if (!isValidPhone(phoneEl.value.trim())) {
      showFieldError(phoneEl, 'Please enter a valid phone number.');
      valid = false;
    }
  }

  // Password (only on add form — not on edit form)
  const pwEl = document.getElementById('password');
  if (pwEl) {
    clearFieldError(pwEl);
    const result = validatePasswordStrength(pwEl.value);
    if (!result.ok) {
      showFieldError(pwEl, result.message);
      valid = false;
    }

    // Confirm password
    const confirmEl = document.getElementById('confirm_password');
    if (confirmEl) {
      clearFieldError(confirmEl);
      if (confirmEl.value !== pwEl.value) {
        showFieldError(confirmEl, 'Passwords do not match.');
        valid = false;
      }
    }
  }

  if (!valid) {
    e.preventDefault();
    // Scroll to first error
    const firstErr = form.querySelector('.is-invalid');
    if (firstErr) firstErr.scrollIntoView({ behavior: 'smooth', block: 'center' });
  } else {
    // Show loading state
    const btn = document.getElementById('submitTeacherBtn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…';
    }
  }
}


/* ══════════════════════════════════════════════
   REAL-TIME VALIDATION (blur events)
══════════════════════════════════════════════ */

function attachBlurValidators() {
  const rules = [
    { id: 'first_name',  test: v => v.trim().length > 0,                  msg: 'First name is required.' },
    { id: 'last_name',   test: v => v.trim().length > 0,                  msg: 'Last name is required.' },
    { id: 'username',    test: v => /^[A-Za-z0-9_]{3,50}$/.test(v.trim()), msg: 'Username: 3–50 chars, letters/digits/underscores.' },
    { id: 'email',       test: v => isValidEmail(v.trim()),                msg: 'Valid email is required.' },
    { id: 'staff_id',    test: v => v.trim().length > 0,                   msg: 'Staff ID is required.' },
    { id: 'phone',       test: v => v.trim() === '' || isValidPhone(v.trim()), msg: 'Enter a valid phone number.' },
  ];

  rules.forEach(({ id, test, msg }) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('blur', () => {
      clearFieldError(el);
      if (!test(el.value)) showFieldError(el, msg);
    });
    el.addEventListener('input', () => clearFieldError(el));
  });

  // Password live strength
  const pwEl = document.getElementById('password');
  if (pwEl) {
    pwEl.addEventListener('input', () => {
      clearFieldError(pwEl);
      const result = validatePasswordStrength(pwEl.value);
      if (pwEl.value && !result.ok) showFieldError(pwEl, result.message);
    });
  }

  const confirmEl = document.getElementById('confirm_password');
  if (confirmEl && document.getElementById('password')) {
    confirmEl.addEventListener('input', () => {
      clearFieldError(confirmEl);
      if (confirmEl.value && confirmEl.value !== document.getElementById('password').value) {
        showFieldError(confirmEl, 'Passwords do not match.');
      }
    });
  }
}


/* ══════════════════════════════════════════════
   INIT
══════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', function () {
  const teacherForm = document.getElementById('teacherForm');
  if (teacherForm) {
    teacherForm.addEventListener('submit', validateTeacherForm);
    attachBlurValidators();
  }
});
