/**
 * reports.js — Academic EdTech Reports page
 * Table search filtering and interactions
 */

'use strict';

// ── Table row click navigation ────────────────────────────────────────────────
function rowClick(event, url) {
  if (event.target.closest('.tbl-actions')) return;
  window.location.href = url;
}

// ── Table search filter ───────────────────────────────────────────────────────
function filterTable(query) {
  const rows = document.querySelectorAll('#tableBody tr[data-name]');
  const q    = query.toLowerCase().trim();
  let visible = 0;

  rows.forEach(row => {
    const match = row.dataset.name.includes(q);
    row.style.display = match ? '' : 'none';
    if (match) visible++;
  });

  // Toggle no-results row
  let noRow = document.getElementById('noResultsRow');
  if (visible === 0 && rows.length > 0) {
    if (!noRow) {
      noRow = document.createElement('tr');
      noRow.id = 'noResultsRow';
      noRow.innerHTML = `
        <td colspan="8" style="text-align:center;padding:2rem;color:var(--c-text-3);">
          <i class="fas fa-search" aria-hidden="true" style="margin-right:6px;opacity:0.5;"></i>
          No sessions found matching <strong>"${q}"</strong>
        </td>`;
      document.getElementById('tableBody').appendChild(noRow);
    }
  } else if (noRow) {
    noRow.remove();
  }
}

// ── Progress bar animation on load ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.mini-bar-fill').forEach(fill => {
    const target = fill.style.width;
    fill.style.width      = '0';
    fill.style.transition = 'width 0.7s ease';
    requestAnimationFrame(() => {
      setTimeout(() => { fill.style.width = target; }, 100);
    });
  });
});
