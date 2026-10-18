/**
 * main.js — Shared utilities for EngageAI
 * Sidebar toggle, flash auto-dismiss, loading overlay
 */

'use strict';

// ── Sidebar Toggle ────────────────────────────────────────────────────────────
(function initSidebar() {
  const toggle  = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');

  if (!toggle || !sidebar) return;

  toggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    overlay.classList.toggle('open');
  });

  overlay.addEventListener('click', () => {
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
  });

  // Close sidebar on nav click (mobile)
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('open');
    });
  });
})();

// ── Flash Toast Auto-dismiss ──────────────────────────────────────────────────
(function autoFlash() {
  const toasts = document.querySelectorAll('.flash-toast');
  toasts.forEach((toast, i) => {
    setTimeout(() => {
      toast.style.transition = 'opacity 0.5s, transform 0.5s';
      toast.style.opacity    = '0';
      toast.style.transform  = 'translateY(-10px)';
      setTimeout(() => toast.remove(), 500);
    }, 4000 + i * 500);
  });
})();

// ── Loading Overlay ───────────────────────────────────────────────────────────
function showLoader(text = 'Processing…') {
  const overlay = document.getElementById('loadingOverlay');
  const label   = document.getElementById('loadingText');
  if (overlay) {
    overlay.style.display = 'flex';
    if (label) label.textContent = text;
  }
}

function hideLoader() {
  const overlay = document.getElementById('loadingOverlay');
  if (overlay) overlay.style.display = 'none';
}

// ── Notification Toast (programmatic) ────────────────────────────────────────
function showNotification(message, type = 'info') {
  const icons = {
    success: 'fa-check-circle',
    danger:  'fa-times-circle',
    warning: 'fa-exclamation-triangle',
    info:    'fa-info-circle',
  };

  const container = document.getElementById('flashContainer') || (() => {
    const c = document.createElement('div');
    c.className = 'flash-container';
    c.id = 'flashContainer';
    document.querySelector('.page-content')?.prepend(c);
    return c;
  })();

  const toast = document.createElement('div');
  toast.className = `flash-toast flash-${type}`;
  toast.innerHTML = `
    <i class="fas ${icons[type] || icons.info}"></i>
    <span>${message}</span>
    <button class="flash-close" onclick="this.parentElement.remove()">&times;</button>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.transition = 'opacity 0.5s, transform 0.5s';
    toast.style.opacity    = '0';
    toast.style.transform  = 'translateY(-10px)';
    setTimeout(() => toast.remove(), 500);
  }, 4500);
}

// ── Format file size ──────────────────────────────────────────────────────────
function formatBytes(bytes) {
  if (bytes < 1024)             return bytes + ' B';
  if (bytes < 1024 * 1024)      return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
}

// ── Animate number counter ────────────────────────────────────────────────────
function animateCounter(el, target, duration = 800, suffix = '') {
  const start = Date.now();
  const from  = parseFloat(el.textContent) || 0;

  function update() {
    const elapsed  = Date.now() - start;
    const progress = Math.min(elapsed / duration, 1);
    const ease     = 1 - Math.pow(1 - progress, 3); // cubic ease-out
    const value    = from + (target - from) * ease;
    el.textContent = (Number.isInteger(target) ? Math.round(value) : value.toFixed(1)) + suffix;
    if (progress < 1) requestAnimationFrame(update);
  }

  requestAnimationFrame(update);
}
