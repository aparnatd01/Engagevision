/**
 * dashboard.js — Academic EdTech Dashboard Charts
 * Chart.js integration for engagement visualization
 */

'use strict';

function initDashboard(data) {
  renderEngagementDonut(data);
  animateStatValues();
}

// ── Engagement Donut Chart ────────────────────────────────────────────────────
function renderEngagementDonut(data) {
  const canvas = document.getElementById('engagementDonut');
  if (!canvas) return;

  const sessions = data.sessions || [];
  let high = 0, medium = 0, low = 0;

  sessions.forEach(pct => {
    if (pct >= 70)      high++;
    else if (pct >= 40) medium++;
    else                low++;
  });

  // Fallback from overall if no sessions
  if (sessions.length === 0 && data.overall) {
    if (data.overall >= 70)      high = 1;
    else if (data.overall >= 40) medium = 1;
    else                         low = 1;
  }

  // Empty placeholder
  if (high + medium + low === 0) {
    high = 1; medium = 1; low = 1;
  }

  const COLORS = {
    high:   '#38a169',
    medium: '#dd6b20',
    low:    '#e53e3e',
  };

  const chart = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: ['High Engagement', 'Medium Engagement', 'Low Engagement'],
      datasets: [{
        data:                  [high, medium, low],
        backgroundColor:       [COLORS.high, COLORS.medium, COLORS.low],
        borderColor:           ['#276749',   '#975a16',     '#9b2c2c'],
        borderWidth: 1,
        hoverBackgroundColor:  ['#48bb78',   '#ed8936',     '#f56565'],
        hoverOffset: 6,
      }],
    },
    options: {
      cutout: '72%',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1a202c',
          titleColor:      '#f7fafc',
          bodyColor:       '#e2e8f0',
          borderColor:     '#2d3748',
          borderWidth: 1,
          padding: 10,
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed} session${ctx.parsed !== 1 ? 's' : ''}`,
          },
        },
      },
      animation: { animateRotate: true, animateScale: false, duration: 700, easing: 'easeOutQuart' },
    },
    plugins: [{
      id: 'centerText',
      afterDraw(chart) {
        const { ctx, chartArea: { left, top, right, bottom } } = chart;
        const cx = (left + right)  / 2;
        const cy = (top  + bottom) / 2;

        ctx.save();
        ctx.fillStyle = '#1e3a5f';
        ctx.font      = `bold 1.4rem Inter, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${data.overall || 0}%`, cx, cy - 8);

        ctx.fillStyle = '#718096';
        ctx.font      = `0.65rem Inter, sans-serif`;
        ctx.fillText('Overall', cx, cy + 12);
        ctx.restore();
      },
    }],
  });

  // Populate custom legend
  const legendEl = document.getElementById('chartLegend');
  if (legendEl) {
    const items = [
      { label: 'High Engagement',   color: COLORS.high,   count: high   },
      { label: 'Medium Engagement', color: COLORS.medium, count: medium },
      { label: 'Low Engagement',    color: COLORS.low,    count: low    },
    ];
    legendEl.innerHTML = items.map(item => `
      <div class="chart-legend-item">
        <span class="legend-dot" style="background:${item.color};"></span>
        <span>${item.label}</span>
        <span class="legend-count">${item.count} session${item.count !== 1 ? 's' : ''}</span>
      </div>
    `).join('');
  }
}

// ── Stat value counter animation ─────────────────────────────────────────────
function animateStatValues() {
  document.querySelectorAll('.stat-value').forEach(el => {
    const raw = el.textContent.trim();
    const num = parseFloat(raw.replace('%', ''));
    const hasPct = raw.includes('%');
    if (!isNaN(num) && num > 0) {
      animateCounter(el, num, 700, hasPct ? '%' : '');
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  // No additional init needed — charts are started from inline script
});
