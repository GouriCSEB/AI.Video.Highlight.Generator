'use strict';

// ── 3D Card Tilt ─────────────────────────────────────────────────────────
function init3DTilt() {
  document.querySelectorAll('.card-3d').forEach(card => {
    card.addEventListener('mousemove', e => {
      const rect   = card.getBoundingClientRect();
      const cx     = rect.left + rect.width  / 2;
      const cy     = rect.top  + rect.height / 2;
      const dx     = (e.clientX - cx) / (rect.width  / 2);
      const dy     = (e.clientY - cy) / (rect.height / 2);
      const tiltX  = dy * -6;
      const tiltY  = dx *  6;
      const shine  = `radial-gradient(circle at ${e.clientX - rect.left}px ${e.clientY - rect.top}px, rgba(255,255,255,0.05) 0%, transparent 60%)`;
      card.style.transform = `perspective(900px) rotateX(${tiltX}deg) rotateY(${tiltY}deg) translateZ(4px)`;
      card.style.backgroundImage = shine;
    });
    card.addEventListener('mouseleave', () => {
      card.style.transform = '';
      card.style.backgroundImage = '';
    });
  });
}
// Re-run tilt whenever new cards appear
const _tiltObserver = new MutationObserver(init3DTilt);
_tiltObserver.observe(document.body, { childList: true, subtree: true });
init3DTilt();

// ── Button Ripple ─────────────────────────────────────────────────────────
document.addEventListener('click', e => {
  const btn = e.target.closest('.btn-go, .btn-hero-signup, .btn-submit, .btn-download');
  if (!btn) return;
  const rect    = btn.getBoundingClientRect();
  const ripple  = document.createElement('span');
  const size    = Math.max(rect.width, rect.height);
  ripple.className = 'ripple';
  ripple.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX-rect.left-size/2}px;top:${e.clientY-rect.top-size/2}px`;
  btn.appendChild(ripple);
  setTimeout(() => ripple.remove(), 700);
});

// ── Stat Row Flash ────────────────────────────────────────────────────────
function flashStats() {
  document.querySelectorAll('.stat-row').forEach((el, i) => {
    setTimeout(() => {
      el.classList.add('flash');
      setTimeout(() => el.classList.remove('flash'), 500);
    }, i * 120);
  });
}

// ── DOM refs ──────────────────────────────────────────────────────────────
const dropZone        = document.getElementById('dropZone');
const fileInput       = document.getElementById('fileInput');
const btnBrowse       = document.getElementById('btnBrowse');
const fileInfo        = document.getElementById('fileInfo');
const fiName          = document.getElementById('fiName');
const fiSize          = document.getElementById('fiSize');
const btnUpload       = document.getElementById('btnUpload');
const uploadProgress  = document.getElementById('uploadProgress');
const uploadBar       = document.getElementById('uploadBar');
const uploadPct       = document.getElementById('uploadPct');
const cardProcess     = document.getElementById('cardProcess');
const cardResults     = document.getElementById('cardResults');
const processBar      = document.getElementById('processBar');
const processPct      = document.getElementById('processPct');
const hlVideo         = document.getElementById('hlVideo');
const btnDownload     = document.getElementById('btnDownload');
const btnReport       = document.getElementById('btnReport');
const btnReset        = document.getElementById('btnReset');
const highlightSlider = document.getElementById('highlightSlider');
const sliderVal       = document.getElementById('sliderVal');
const timelineCanvas  = document.getElementById('timelineCanvas');
const timelineCursor  = document.getElementById('timelineCursor');
const segmentList     = document.getElementById('segmentList');
const metricsModal    = document.getElementById('metricsModal');
const historyModal    = document.getElementById('historyModal');
const historyList     = document.getElementById('historyList');

// ── state ─────────────────────────────────────────────────────────────────
let selectedFile = null, videoId = null, pollTimer = null;
let lastTimeline = [], lastSegments = [], lastKeywordHits = [];

// ── Capabilities check ────────────────────────────────────────────────────
async function checkCapabilities() {
  try {
    const caps = await fetch('/capabilities').then(r => r.json());
    if (!caps.whisper) {
      document.getElementById('badgeWhisper').textContent = 'Not installed';
      document.getElementById('badgeWhisper').style.color = '#f59e0b';
      document.getElementById('toggleWhisper').checked = false;
    }
  } catch(e) {}
}
checkCapabilities();

// ── Slider ────────────────────────────────────────────────────────────────
highlightSlider.addEventListener('input', () => {
  sliderVal.textContent = `${highlightSlider.value}% of video`;
});

// ── File selection ────────────────────────────────────────────────────────
btnBrowse.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => handleFile(fileInput.files[0]));
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
});
dropZone.addEventListener('click', e => { if (e.target !== btnBrowse) fileInput.click(); });

function handleFile(file) {
  if (!file) return;
  selectedFile = file;
  fiName.textContent = file.name;
  fiSize.textContent = formatBytes(file.size);
  fileInfo.classList.remove('hidden');
}

// ── Upload ────────────────────────────────────────────────────────────────
btnUpload.addEventListener('click', startUpload);
async function startUpload() {
  if (!selectedFile) return;
  fileInfo.classList.add('hidden');
  uploadProgress.classList.remove('hidden');
  setBar(uploadBar, uploadPct, 0);
  const fd = new FormData();
  fd.append('video', selectedFile);
  try {
    const res  = await fetchWithProgress('/upload', fd, p => setBar(uploadBar, uploadPct, p));
    if (!res.ok) { const e = await res.json(); throw new Error(e.error); }
    const data = await res.json();
    videoId = data.video_id;
    setBar(uploadBar, uploadPct, 100);
    await delay(400);
    cardProcess.classList.remove('hidden');
    cardProcess.scrollIntoView({ behavior:'smooth', block:'center' });
    await startProcessing(videoId);
  } catch(err) {
    uploadProgress.classList.add('hidden'); fileInfo.classList.remove('hidden');
    alert('Upload error: ' + err.message);
  }
}

function fetchWithProgress(url, fd, onP) {
  return new Promise((res, rej) => {
    const x = new XMLHttpRequest();
    x.open('POST', url);
    x.upload.onprogress = e => { if (e.lengthComputable) onP(Math.round(e.loaded/e.total*100)); };
    x.onload  = () => res({ ok: x.status < 300, json: () => Promise.resolve(JSON.parse(x.responseText)) });
    x.onerror = () => rej(new Error('Network error'));
    x.send(fd);
  });
}

// ── Processing ───────────────────────────────────────────────────────────
async function startProcessing(id) {
  const body = {
    highlight_fraction: parseInt(highlightSlider.value) / 100,
    keywords:           document.getElementById('keywordInput').value,
    enable_whisper:     document.getElementById('toggleWhisper').checked,
    enable_face:        document.getElementById('toggleFace').checked,
    enable_emotion:     document.getElementById('toggleEmotion').checked,
    enable_report:      document.getElementById('toggleReport').checked,
  };
  try {
    const res = await fetch(`/process/${id}`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error('Failed to start processing');
    pollStatus(id);
  } catch(err) { alert('Error: ' + err.message); }
}

// ── Pipeline polling ──────────────────────────────────────────────────────
const STEP_ORDER = ['extracting','scoring','detecting_faces','detecting_emotions',
                    'transcribing','selecting_segments','generating','generating_report','done'];

function pollStatus(id) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const data = await fetch(`/status/${id}`).then(r => r.json());
      updatePipelineUI(data);
      if (data.status === 'done')  {
          clearInterval(pollTimer);
          await delay(600);
          showResults(data);
          // Show saved-to-library toast if logged in
          try {
            const me = await fetch('/api/me').then(r=>r.json());
            if (me.logged_in) {
              showToast('✅ Highlight saved to your Library!');
              document.getElementById('btnLibrary').style.display = 'inline-block';
            }
          } catch(e) {}
        }
      if (data.status === 'error') { clearInterval(pollTimer); alert('Failed: ' + data.error); }
    } catch(e) { console.error(e); }
  }, 1800);
}

function updatePipelineUI(data) {
  setBar(processBar, processPct, data.progress || 0);
  document.querySelectorAll('.pipe-step').forEach(step => {
    const s = step.dataset.step, statusEl = step.querySelector('.pipe-status');
    step.classList.remove('active','done','error');
    const ci = STEP_ORDER.indexOf(data.status), si = STEP_ORDER.indexOf(s);
    if (data.status === 'error')                              { step.classList.add('error');  statusEl.textContent = 'error'; }
    else if (si < ci || (data.status==='done' && s==='done')) { step.classList.add('done');   statusEl.textContent = 'done ✓'; }
    else if (si === ci)                                       { step.classList.add('active'); statusEl.innerHTML = '<span class="spinner"></span>'; }
    else                                                      { statusEl.textContent = 'waiting'; }
  });
}

// ── Results ───────────────────────────────────────────────────────────────
function showResults(data) {
  cardResults.classList.remove('hidden');
  cardResults.scrollIntoView({ behavior:'smooth', block:'start' });

  const info = data.video_info    || {};
  const meta = data.highlight_meta|| {};

  document.getElementById('statOrigLen').textContent  = formatTime(info.duration || 0);
  document.getElementById('statHlLen').textContent    = formatTime(meta.highlight_duration || 0);
  document.getElementById('statSegs').textContent     = (data.segments || []).length;

  // Face summary
  const fs = data.face_summary;
  document.getElementById('statFace').textContent =
    fs ? `${fs.pct}% of frames` : 'N/A';

  // Emotion summary
  const es = data.emotion_summary;
  document.getElementById('statEmotion').textContent =
    es ? Object.entries(es).sort((a,b)=>b[1]-a[1])[0]?.[0] || '—' : 'N/A';

  // Keyword hits
  const kh = data.keyword_hits || [];
  document.getElementById('statKeywords').textContent = kh.length ? `${kh.length} hits` : 'None';

  // Video player
  hlVideo.src = ''; hlVideo.load();
  hlVideo.src = `/highlight/${videoId}?t=${Date.now()}`; hlVideo.load();
  btnDownload.href = `/download/${videoId}`;

  // PDF report
  if (data.has_report) {
    btnReport.href = `/report/${videoId}`;
    btnReport.classList.remove('hidden');
  }

  lastTimeline    = data.timeline      || [];
  lastSegments    = data.segments      || [];
  lastKeywordHits = data.keyword_hits  || [];

  if (lastTimeline.length) drawTimeline(lastTimeline, lastSegments, lastKeywordHits);
  setupTimelineSeek(lastTimeline);
  hlVideo.addEventListener('timeupdate', updateTimelineCursor);

  if (data.segments?.length) {
    drawSegmentCards(data.segments, data.seg_scores || [], data.thumbnails || []);
  }

  // Transcript — show results OR helpful error
  const tx = data.transcript;
  const txSection = document.getElementById('transcriptSection');
  txSection.classList.remove('hidden');

  if (tx?.error) {
    // Whisper failed or not installed
    document.getElementById('transcriptMeta').textContent = '⚠️ Transcription issue';
    document.getElementById('transcriptText').textContent = tx.error;
    document.getElementById('transcriptBox').classList.remove('hidden');
  } else if (tx?.text) {
    // Success
    document.getElementById('transcriptMeta').textContent =
      `✅ Language: ${(tx.language||'?').toUpperCase()} · ${tx.segments?.length||0} segments detected`;
    document.getElementById('transcriptText').textContent = tx.text;
    document.getElementById('btnToggleTranscript').addEventListener('click', () => {
      document.getElementById('transcriptBox').classList.toggle('hidden');
    });
  } else {
    document.getElementById('transcriptMeta').textContent = 'ℹ️ No speech detected or Whisper not enabled';
    document.getElementById('transcriptBox').classList.remove('hidden');
    document.getElementById('transcriptText').textContent =
      'Enable the Speech-to-Text toggle and re-process, or install Whisper: pip install openai-whisper torch';
  }

  // Face + Emotion
  if (fs || es) {
    document.getElementById('faceSection').classList.remove('hidden');
    renderFaceEmotionPanel(fs, es);
  }

  // Keyword hits list
  if (kh.length) {
    document.getElementById('keywordsSection').classList.remove('hidden');
    renderKeywordHits(kh);
  }
}

// ── Timeline ──────────────────────────────────────────────────────────────
function drawTimeline(timeline, segments, kwHits) {
  const W = timelineCanvas.offsetWidth || 800;
  timelineCanvas.width = W; const H = 100;
  const ctx = timelineCanvas.getContext('2d');
  ctx.clearRect(0, 0, W, H);

  const maxTime  = Math.max(...timeline.map(t=>t.time), 1);
  const maxScore = Math.max(...timeline.map(t=>t.score), 1);

  // Segment backgrounds
  ctx.fillStyle = 'rgba(245,158,11,0.12)';
  for (const [s,e] of segments) ctx.fillRect((s/maxTime)*W, 0, ((e-s)/maxTime)*W, H);

  // Score bars
  const bw = Math.max(2, W/timeline.length-1);
  for (const t of timeline) {
    const x = (t.time/maxTime)*W, h = (t.score/maxScore)*(H-16);
    ctx.fillStyle = t.is_highlight ? 'rgba(245,158,11,0.85)' : 'rgba(139,92,246,0.45)';
    ctx.fillRect(x-bw/2, H-h-8, bw, h);
  }

  // Keyword hit markers
  ctx.fillStyle = '#f43f5e';
  for (const kw of (kwHits||[])) {
    const x = (kw.time / maxTime) * W;
    ctx.fillRect(x-1, 0, 3, H);
  }

  // Time labels
  ctx.fillStyle='rgba(107,100,143,0.8)'; ctx.font='10px DM Mono,monospace';
  for (let s=0; s<=maxTime; s+=Math.max(1,Math.floor(maxTime/6)))
    ctx.fillText(formatTime(s), (s/maxTime)*W+3, H-2);
}

function setupTimelineSeek(timeline) {
  timelineCanvas.onclick = function(e) {
    if (!timeline.length) return;
    const rect  = timelineCanvas.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / timelineCanvas.offsetWidth;
    const maxT  = Math.max(...timeline.map(t=>t.time), 1);
    showToast(`⏱ Jumped to ${formatTime(ratio * maxT)} in original video`);
    if (hlVideo.duration) { hlVideo.currentTime = ratio * hlVideo.duration; hlVideo.play(); }
    moveCursor(e.clientX - rect.left);
  };
}

function updateTimelineCursor() {
  if (!hlVideo.duration || !lastTimeline.length) return;
  moveCursor((hlVideo.currentTime / hlVideo.duration) * timelineCanvas.offsetWidth);
}
function moveCursor(x) {
  timelineCursor.classList.remove('hidden');
  timelineCursor.style.left = x + 'px';
}

// ── Segment cards ─────────────────────────────────────────────────────────
function drawSegmentCards(segments, segScores, thumbnails) {
  segmentList.innerHTML = '';
  segments.forEach(([s,e], idx) => {
    const conf  = segScores[idx] || 0;
    const thumb = thumbnails[idx] || '';
    let tier = 'low', tierLabel = 'Low';
    if (conf >= 60) { tier='high'; tierLabel='High'; }
    else if (conf >= 35) { tier='medium'; tierLabel='Med'; }

    const card = document.createElement('div');
    card.className = 'segment-card';
    card.innerHTML = `
      ${thumb ? `<img class="seg-thumb" src="data:image/jpeg;base64,${thumb}" alt="Seg ${idx+1}"/>`
               : `<div class="seg-thumb-placeholder">🎬</div>`}
      <div class="seg-info">
        <span class="seg-title">Segment #${idx+1}</span>
        <span class="seg-time-detail">${formatTime(s)} → ${formatTime(e)} · ${formatTime(e-s)}</span>
        <span class="seg-jump-hint">▶ Click to jump</span>
      </div>
      <div class="confidence-badge">
        <div class="conf-ring ${tier}">${conf.toFixed(0)}%</div>
        <div class="conf-label">${tierLabel} conf.</div>
      </div>`;
    card.addEventListener('click', () => {
      if (!hlVideo.duration || !lastTimeline.length) return;
      const maxT = Math.max(...lastTimeline.map(t=>t.time), 1);
      hlVideo.currentTime = (s / maxT) * hlVideo.duration;
      hlVideo.play();
      hlVideo.scrollIntoView({ behavior:'smooth', block:'center' });
      card.style.borderColor = 'var(--accent)';
      setTimeout(() => card.style.borderColor = '', 1500);
    });
    segmentList.appendChild(card);
  });
}

// ── Face + Emotion panel ──────────────────────────────────────────────────
function renderFaceEmotionPanel(faceSummary, emotionSummary) {
  const grid = document.getElementById('faceGrid');
  grid.innerHTML = '';

  if (faceSummary) {
    grid.innerHTML += `
      <div class="face-card">
        <div class="face-card-icon">😊</div>
        <div class="face-card-val">${faceSummary.pct}%</div>
        <div class="face-card-label">Frames with face</div>
      </div>
      <div class="face-card">
        <div class="face-card-icon">🎥</div>
        <div class="face-card-val">${faceSummary.frames_with_face}</div>
        <div class="face-card-label">Face detections</div>
      </div>`;
  }

  if (emotionSummary && Object.keys(emotionSummary).length) {
    const total = Object.values(emotionSummary).reduce((a,b)=>a+b, 0);
    const bars  = Object.entries(emotionSummary)
      .sort((a,b)=>b[1]-a[1])
      .map(([em,cnt]) => `
        <div class="em-row">
          <span class="em-name">${em}</span>
          <div class="em-track"><div class="em-fill" style="width:${Math.round(cnt/total*100)}%"></div></div>
          <span class="em-count">${cnt}</span>
        </div>`).join('');
    grid.innerHTML += `
      <div class="face-card" style="grid-column:span 2;text-align:left">
        <div class="face-card-icon" style="margin-bottom:8px">🧠 Emotion Distribution</div>
        <div class="emotion-bars">${bars}</div>
      </div>`;
  } else if (!emotionSummary || !Object.keys(emotionSummary||{}).length) {
    grid.innerHTML += `
      <div class="face-card">
        <div class="face-card-icon">🧠</div>
        <div class="face-card-val" style="font-size:13px">Install DeepFace</div>
        <div class="face-card-label">for emotion data</div>
      </div>`;
  }
}

// ── Keyword hits list ─────────────────────────────────────────────────────
function renderKeywordHits(hits) {
  const list = document.getElementById('keywordHitsList');
  list.innerHTML = hits.slice(0, 15).map(h => `
    <div class="kw-item">
      <span class="kw-time">${formatTime(h.time)}</span>
      <span class="kw-keyword">${h.keyword}</span>
      <span class="kw-text">${h.text}</span>
    </div>`).join('');
}

// ── History panel ─────────────────────────────────────────────────────────
document.getElementById('btnShowHistory').addEventListener('click', async () => {
  historyModal.classList.remove('hidden'); await loadHistory();
});
document.getElementById('btnCloseHistory').addEventListener('click', () => historyModal.classList.add('hidden'));
historyModal.addEventListener('click', e => { if (e.target===historyModal) historyModal.classList.add('hidden'); });

async function loadHistory() {
  try {
    const data = await fetch('/history').then(r=>r.json());
    historyList.innerHTML = '';
    if (!data.length) { historyList.innerHTML = '<p class="muted-msg">No videos yet.</p>'; return; }
    data.forEach(item => {
      const el = document.createElement('div');
      el.className = 'history-item';
      el.innerHTML = `
        <span class="history-icon">🎬</span>
        <div class="history-info">
          <div class="history-name">${item.filename}</div>
          <div class="history-meta">
            ${formatTime(item.original_duration)} → ${formatTime(item.highlight_duration)} ·
            ${item.segments_count} segs ·
            ${item.has_transcript ? '🎤 transcript' : ''} ·
            ${item.has_report ? '📄 report' : ''} ·
            ${item.finished_at}
          </div>
        </div>
        <span class="history-action">⬇ Download</span>`;
      el.addEventListener('click', () => window.location.href = `/download/${item.video_id}`);
      historyList.appendChild(el);
    });
  } catch(e) { historyList.innerHTML = '<p class="muted-msg">Could not load.</p>'; }
}

// ── Metrics modal ─────────────────────────────────────────────────────────
document.getElementById('btnShowMetrics').addEventListener('click', async () => {
  metricsModal.classList.remove('hidden'); await loadMetrics();
});
document.getElementById('btnCloseMetrics').addEventListener('click', () => metricsModal.classList.add('hidden'));
metricsModal.addEventListener('click', e => { if (e.target===metricsModal) metricsModal.classList.add('hidden'); });

async function loadMetrics() {
  try {
    const d = await fetch('/metrics').then(r=>r.json());
    document.getElementById('mAccuracy').textContent  = pct(d.accuracy);
    document.getElementById('mPrecision').textContent = pct(d.precision);
    document.getElementById('mRecall').textContent    = pct(d.recall);
    document.getElementById('mF1').textContent        = pct(d.f1_score);
    if (d.confusion_matrix)    drawCM(d.confusion_matrix);
    if (d.feature_importances) drawFI(d.feature_importances);
  } catch(e) {}
}
function pct(v) { return v!=null ? (v*100).toFixed(1)+'%' : '—'; }

function drawCM(cm) {
  const c=document.getElementById('cmCanvas').getContext('2d'),W=260,H=260,cw=130,ch=130;
  c.clearRect(0,0,W,H);
  const mx=Math.max(...cm.flat(),1);
  const cols=[['rgba(139,92,246,0.75)','rgba(255,92,92,0.4)'],['rgba(255,92,92,0.4)','rgba(139,92,246,0.75)']];
  for(let r=0;r<2;r++) for(let cc2=0;cc2<2;cc2++) {
    const a=0.2+0.8*(cm[r][cc2]/mx);
    c.fillStyle=cols[r][cc2].replace('0.7',a.toFixed(2)).replace('0.4',(a*.5).toFixed(2));
    c.fillRect(cc2*cw+1,r*ch+1,cw-2,ch-2);
    c.fillStyle='#e8eaf0'; c.font='bold 18px Syne,sans-serif';
    c.textAlign='center'; c.textBaseline='middle'; c.fillText(cm[r][cc2],cc2*cw+65,r*ch+65);
  }
}
function drawFI(fi) {
  const canvas=document.getElementById('fiCanvas'), W=canvas.offsetWidth||560;
  canvas.width=W;
  const ent=Object.entries(fi).sort((a,b)=>b[1]-a[1]), BH=16, G=5;
  canvas.height=ent.length*(BH+G)+20;
  const ctx=canvas.getContext('2d'); ctx.clearRect(0,0,W,canvas.height);
  const mv=ent[0][1], LW=140;
  ent.forEach(([n,v],i)=>{
    const y=i*(BH+G), bw=(v/mv)*(W-LW-20);
    ctx.fillStyle='rgba(107,113,128,0.5)'; ctx.fillRect(LW,y,W-LW-10,BH);
    const g=ctx.createLinearGradient(LW,0,LW+bw,0);
    g.addColorStop(0,'#8b5cf6'); g.addColorStop(1,'#f59e0b');
    ctx.fillStyle=g; ctx.fillRect(LW,y,bw,BH);
    ctx.fillStyle='#e8eaf0'; ctx.font='11px DM Mono,monospace';
    ctx.textAlign='right'; ctx.textBaseline='middle'; ctx.fillText(n,LW-6,y+BH/2);
    ctx.fillStyle='rgba(107,100,143,0.8)'; ctx.textAlign='left';
    ctx.fillText((v*100).toFixed(1)+'%',LW+bw+5,y+BH/2);
  });
}

// ── Reset ─────────────────────────────────────────────────────────────────
btnReset.addEventListener('click', () => {
  selectedFile=null; videoId=null;
  if (pollTimer) clearInterval(pollTimer);
  fileInput.value=''; fileInfo.classList.add('hidden');
  uploadProgress.classList.add('hidden');
  setBar(uploadBar,uploadPct,0); setBar(processBar,processPct,0);
  document.querySelectorAll('.pipe-step').forEach(s=>{
    s.classList.remove('active','done','error');
    s.querySelector('.pipe-status').textContent='waiting';
  });
  cardProcess.classList.add('hidden'); cardResults.classList.add('hidden');
  hlVideo.src=''; timelineCursor.classList.add('hidden');
  btnReport.classList.add('hidden');
  ['transcriptSection','faceSection','keywordsSection'].forEach(id=>
    document.getElementById(id).classList.add('hidden'));
  hlVideo.removeEventListener('timeupdate', updateTimelineCursor);
  window.scrollTo({top:0, behavior:'smooth'});
});

// ── Toast ─────────────────────────────────────────────────────────────────
function showToast(msg) {
  let t=document.getElementById('toast');
  if (!t) { t=document.createElement('div'); t.id='toast';
    t.style.cssText=`position:fixed;bottom:32px;left:50%;transform:translateX(-50%);
    background:var(--surface2);border:1px solid var(--border);color:var(--text);
    padding:10px 20px;border-radius:8px;font-size:13px;z-index:9999;
    transition:opacity .3s;font-family:var(--font-mono)`;
    document.body.appendChild(t); }
  t.textContent=msg; t.style.opacity='1';
  clearTimeout(t._t); t._t=setTimeout(()=>t.style.opacity='0', 2500);
}

// ── Helpers ───────────────────────────────────────────────────────────────
function setBar(el,pe,v){el.style.width=v+'%';pe.textContent=v+'%';}
function delay(ms){return new Promise(r=>setTimeout(r,ms));}
function formatBytes(b){
  if(b<1024) return b+' B';
  if(b<1024**2) return (b/1024).toFixed(1)+' KB';
  if(b<1024**3) return (b/1024**2).toFixed(1)+' MB';
  return (b/1024**3).toFixed(2)+' GB';
}
function formatTime(sec){
  const s=Math.round(sec||0),m=Math.floor(s/60),h=Math.floor(m/60);
  if(h>0) return `${h}h ${m%60}m ${s%60}s`;
  if(m>0) return `${m}m ${s%60}s`;
  return `${s}s`;
}
