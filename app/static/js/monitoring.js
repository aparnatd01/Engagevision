/**
 * monitoring.js — Academic EdTech Monitoring Page
 * Handles upload, SSE progress, face results rendering
 */

'use strict';

let currentSessionId = null;
let eventSource      = null;

// ── Upload Zone ───────────────────────────────────────────────────────────────
(function initUploadZone() {
  const zone  = document.getElementById('uploadZone');
  const input = document.getElementById('videoFile');
  if (!zone || !input) return;

  zone.addEventListener('click', e => {
    if (!e.target.closest('#removeFile')) input.click();
  });

  zone.addEventListener('keypress', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
  });

  input.addEventListener('change', () => {
    if (input.files.length) handleFile(input.files[0]);
  });

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-active'); });
  zone.addEventListener('dragleave', ()  => zone.classList.remove('drag-active'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-active');
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });

  document.getElementById('removeFile')?.addEventListener('click', e => {
    e.stopPropagation();
    clearFile();
  });
})();

function handleFile(file) {
  const errEl = document.getElementById('videoErrorMsg');
  errEl.textContent = '';

  const validExt = /\.(mp4|avi|mov|mkv|webm)$/i.test(file.name);
  if (!validExt) {
    errEl.textContent = 'Invalid file type. Please upload MP4, AVI, MOV, MKV, or WEBM.';
    return;
  }
  if (file.size > 500 * 1024 * 1024) {
    errEl.textContent = 'File is too large. Maximum allowed size is 500 MB.';
    return;
  }

  // Show preview
  document.getElementById('dropInner').style.display = 'none';
  const preview = document.getElementById('filePreview');
  preview.style.display = 'flex';
  document.getElementById('previewName').textContent = file.name;
  document.getElementById('previewSize').textContent = formatBytes(file.size);

  // Attach to input
  const dt = new DataTransfer();
  dt.items.add(file);
  document.getElementById('videoFile').files = dt.files;
}

function clearFile() {
  document.getElementById('videoFile').value = '';
  document.getElementById('filePreview').style.display = 'none';
  document.getElementById('dropInner').style.display   = '';
  document.getElementById('videoErrorMsg').textContent = '';
}

// ── Upload Form ───────────────────────────────────────────────────────────────
document.getElementById('uploadForm')?.addEventListener('submit', async function (e) {
  e.preventDefault();

  const fileInput = document.getElementById('videoFile');
  const errEl     = document.getElementById('videoErrorMsg');

  if (!fileInput.files.length) {
    errEl.textContent = 'Please select a classroom video file.';
    return;
  }

  const btn = document.getElementById('uploadBtn');
  btn.disabled  = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading…';

  // Show upload progress
  const progressWrap = document.getElementById('uploadProgressWrap');
  progressWrap.style.display = 'block';
  simulateUpload();

  const form = new FormData();
  form.append('video',        fileInput.files[0]);
  form.append('session_name', document.getElementById('session_name').value.trim());

  try {
    const resp = await fetch('/monitoring/upload', { method: 'POST', body: form });
    if (!resp.ok) throw new Error(await resp.text() || 'Upload failed.');

    const data = await resp.json();
    currentSessionId = data.session_id;

    // Transition: upload → analysis
    document.getElementById('uploadCard').style.display   = 'none';
    document.getElementById('analysisCard').style.display = 'block';
    document.getElementById('analysisFileName').textContent = data.filename;
    showNotification('Video uploaded successfully. Ready to analyse.', 'success');

  } catch (err) {
    showNotification('Upload failed: ' + err.message, 'danger');
    btn.disabled  = false;
    btn.innerHTML = '<i class="fas fa-upload"></i> Upload Video';
    progressWrap.style.display = 'none';
  }
});

function simulateUpload() {
  const fill  = document.getElementById('uploadFill');
  const pctEl = document.getElementById('uploadPct');
  let pct = 0;
  const iv = setInterval(() => {
    pct = Math.min(pct + Math.random() * 18, 95);
    fill.style.width    = pct + '%';
    pctEl.textContent   = Math.round(pct) + '%';
    if (pct >= 95) clearInterval(iv);
  }, 250);
}

// ── Start Analysis ────────────────────────────────────────────────────────────
function startAnalysis() {
  if (!currentSessionId) return;

  const btn = document.getElementById('startBtn');
  btn.disabled  = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analysing…';

  document.getElementById('analysisProgressWrap').style.display = 'block';
  document.getElementById('analysisBadge').textContent          = 'Processing';

  setStep('step-detect', 'active');

  fetch(`/monitoring/analyze/${currentSessionId}`, { method: 'POST' })
    .then(r => {
      if (!r.ok) throw new Error('Could not start analysis.');
      openSSE(currentSessionId);
    })
    .catch(err => {
      showNotification(err.message, 'danger');
      btn.disabled  = false;
      btn.innerHTML = '<i class="fas fa-play-circle"></i> Start AI Analysis';
    });
}

// ── Server-Sent Events ────────────────────────────────────────────────────────
function openSSE(sessionId) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/monitoring/progress/${sessionId}`);

  eventSource.onmessage = function (evt) {
    const payload = JSON.parse(evt.data);
    const pct     = payload.progress || 0;

    document.getElementById('analysisFill').style.width = pct + '%';
    document.getElementById('analysisPct').textContent  = Math.round(pct) + '%';

    // Step progression
    if (pct >= 25)  { setStep('step-detect',  'done'); setStep('step-analyze', 'active'); setLine('line-1', true); }
    if (pct >= 60)  { setStep('step-analyze', 'done'); setStep('step-report',  'active'); setLine('line-2', true); }
    if (pct >= 90)  { setStep('step-report',  'done'); setLine('line-3', true); }

    const labels = ['Initialising…', 'Detecting faces (YOLOv8)…', 'Analysing engagement (MediaPipe)…', 'Generating report…', 'Complete!'];
    const idx    = Math.floor(pct / 25);
    document.getElementById('progressStatusText').textContent = labels[Math.min(idx, 4)];

    if (payload.result) {
      eventSource.close();
      document.getElementById('analysisBadge').textContent = 'Complete ✓';

      if (payload.result.error) {
        showNotification('Analysis failed: ' + payload.result.error, 'danger');
        document.getElementById('startBtn').disabled  = false;
        document.getElementById('startBtn').innerHTML = '<i class="fas fa-play-circle"></i> Retry Analysis';
        return;
      }

      renderResults(payload.result);
    }
  };

  eventSource.onerror = () => {
    eventSource.close();
    showNotification('Connection lost. Please check the Reports page for results.', 'warning');
  };
}

function setStep(id, state) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('active', 'done');
  if (state) el.classList.add(state);
}

function setLine(id, done) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('done', done);
}

// ── Render Results ────────────────────────────────────────────────────────────
function renderResults(result) {
  const summary = result.summary || {};
  const faces   = result.faces   || [];

  document.getElementById('analysisCard').style.display   = 'none';
  document.getElementById('resultsSection').style.display = 'block';
  document.getElementById('viewReportLink').href     = `/reports/${currentSessionId}`;
  document.getElementById('downloadReportLink').href = `/reports/download/${currentSessionId}`;

  // Summary bar
  const bar = document.getElementById('summaryBar');
  const statItems = [
    { label: 'Overall Engagement', value: `${summary.overall_percentage || 0}%`, cls: 'result-summary-item--overall' },
    { label: 'Faces Detected',     value: summary.total_faces || 0,              cls: 'result-summary-item--total'   },
    { label: 'High Engagement',    value: summary.high_count  || 0,              cls: 'result-summary-item--high'    },
    { label: 'Medium Engagement',  value: summary.medium_count || 0,             cls: 'result-summary-item--medium'  },
    { label: 'Low Engagement',     value: summary.low_count   || 0,              cls: 'result-summary-item--low'     },
  ];

  bar.innerHTML = statItems.map(s => `
    <div class="result-summary-item ${s.cls}">
      <span class="rsi-value">${s.value}</span>
      <span class="rsi-label">${s.label}</span>
    </div>
  `).join('');

  // Face count badge
  document.getElementById('faceCountTag').textContent =
    `${faces.length} face${faces.length !== 1 ? 's' : ''} detected`;

  // Face grid
  const grid = document.getElementById('faceGrid');
  if (faces.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="empty-state-icon"><i class="fas fa-user-slash"></i></div>
        <h3>No Faces Detected</h3>
        <p>No student faces were found in this video. Try a video with clearly visible students.</p>
      </div>`;
    return;
  }

  const statusIcons = { High: 'fa-smile', Medium: 'fa-meh', Low: 'fa-frown' };

  grid.innerHTML = faces.map(f => {
    const statusCls = (f.status || 'low').toLowerCase();
    const icon      = statusIcons[f.status] || 'fa-meh';
    const imgSrc    = f.crop_path ? `/${f.crop_path.replace(/^\//, '')}` : '';

    return `
      <div class="face-card face-card--${statusCls}" role="listitem"
           aria-label="Face ${f.face_id}: ${f.engagement_score}% ${f.status} engagement">
        <div class="face-img-box">
          ${imgSrc ? `<img src="${imgSrc}" alt="Detected student face ${f.face_id}"
              onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">` : ''}
          <div class="face-placeholder" ${imgSrc ? 'style="display:none"' : ''} aria-hidden="true">
            <i class="fas fa-user"></i>
          </div>
          <div class="face-id-tag">Face ${f.face_id}</div>
        </div>
        <div class="face-info">
          <span class="face-score">${f.engagement_score}%</span>
          <span class="badge badge-${statusCls}">
            <i class="fas ${icon}" aria-hidden="true"></i> ${f.status}
          </span>
        </div>
      </div>
    `;
  }).join('');

  showNotification('Analysis complete! Engagement results are ready.', 'success');
}
