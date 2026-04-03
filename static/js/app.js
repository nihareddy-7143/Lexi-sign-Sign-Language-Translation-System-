// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
  });
});

// ── Camera ────────────────────────────────────────────────────────────────────
let cameraOn = false;

function toggleCamera() {
  const btn  = document.getElementById('btnCamera');
  const feed = document.getElementById('videoFeed');
  const placeholder = document.getElementById('cameraPlaceholder');
  const overlay     = document.getElementById('camOverlay');
  const spellBar    = document.getElementById('spellBar');
  const controlsCard = document.getElementById('controlsCard');

  if (!cameraOn) {
    fetch('/api/camera', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({action:'start'})
    }).then(() => {
      cameraOn = true;
      feed.src = '/video_feed';
      feed.style.display = 'block';
      placeholder.style.display = 'none';
      overlay.style.display = 'flex';
      spellBar.style.display = 'flex';
      controlsCard.style.display = 'flex';
      btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="3" y="3" width="8" height="8" rx="1"/></svg> Stop Camera`;
      btn.classList.add('stop');
      startPolling();
    });
  } else {
    fetch('/api/camera', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({action:'stop'})
    }).then(() => {
      cameraOn = false;
      feed.style.display = 'none';
      feed.src = '';
      placeholder.style.display = 'flex';
      overlay.style.display = 'none';
      btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M6 4l6 4-6 4V4z"/></svg> Start Camera`;
      btn.classList.remove('stop');
      stopPolling();
    });
  }
}

// ── State polling ─────────────────────────────────────────────────────────────
let pollInterval = null;

function startPolling() {
  pollInterval = setInterval(fetchState, 200);
}

function stopPolling() {
  if (pollInterval) clearInterval(pollInterval);
}

function fetchState() {
  fetch('/api/state')
    .then(r => r.json())
    .then(s => {
      updateUI(s);
    }).catch(() => {});
}

function updateUI(s) {
  // Detection badge
  const badge = document.getElementById('detectionBadge');
  if (s.detected) {
    badge.textContent = `${s.detected}  ${s.confidence}%`;
    badge.style.display = 'block';
  } else {
    badge.style.display = 'none';
  }

  // Hold progress bar
  const holdWrap = document.getElementById('holdBarWrap');
  const holdFill = document.getElementById('holdFill');
  if (s.mode === 'LETTER' && s.hold > 0) {
    holdWrap.style.display = 'flex';
    holdFill.style.width   = `${s.hold}%`;
  } else {
    holdWrap.style.display = 'none';
  }

  // Sentence
  const sentEl = document.getElementById('sentenceText');
  sentEl.textContent = s.sentence || '—';

  // Spelling
  const spellEl = document.getElementById('spellWord');
  spellEl.textContent = (s.word_buffer || '') + '_';

  // Suggestions
  const sugEl = document.getElementById('suggestions');
  sugEl.innerHTML = '';
  if (s.suggestions && s.suggestions.length) {
    s.suggestions.forEach((sug, i) => {
      const btn = document.createElement('button');
      btn.className = 'sug-btn';
      btn.textContent = `${i+1}. ${sug}`;
      btn.onclick = () => sendActionWithData('autocomplete', {idx: i});
      sugEl.appendChild(btn);
    });
  }

  // Final sentence
  const finalDiv = document.getElementById('finalDisplay');
  const finalTxt = document.getElementById('finalText');
  if (s.final) {
    finalTxt.textContent = s.final;
    finalDiv.style.display = 'flex';
  } else {
    finalDiv.style.display = 'none';
  }

  // Translated
  const transDiv = document.getElementById('translatedDisplay');
  const transTxt = document.getElementById('translatedText');
  const transLbl = document.getElementById('translatedLang');
  if (s.translated && s.language !== 'English') {
    transTxt.textContent = s.translated;
    transLbl.textContent = s.language.substring(0,3).toUpperCase();
    transDiv.style.display = 'flex';
  } else {
    transDiv.style.display = 'none';
  }

  // Mode buttons
  document.getElementById('btnLetter').classList.toggle('active', s.mode === 'LETTER');
  document.getElementById('btnWord').classList.toggle('active',   s.mode === 'WORD');

  // Recent signs
  const recentEl = document.getElementById('recentList');
  if (s.recent && s.recent.length) {
    recentEl.innerHTML = s.recent.map(w =>
      `<div class="recent-tag"><span>${w}</span><span style="color:var(--text3);font-size:10px">✓</span></div>`
    ).join('');
  }
}

// ── Actions ───────────────────────────────────────────────────────────────────
function sendAction(cmd) {
  fetch('/api/action', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({cmd})
  });
}

function sendActionWithData(cmd, extra) {
  fetch('/api/action', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({cmd, ...extra})
  });
}

function setMode(m) {
  fetch('/api/action', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({cmd:'mode'})
  });
}

function setLanguage(lang) {
  fetch('/api/action', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({cmd:'language', lang})
  });
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (!cameraOn) return;
  if (e.code === 'Space')  { e.preventDefault(); sendAction('confirm_word'); }
  if (e.code === 'Enter')  { e.preventDefault(); sendAction('generate'); }
  if (e.code === 'Backspace') { sendAction('backspace'); }
  if (e.code === 'KeyC' && !e.ctrlKey) { sendAction('clear'); }
  if (e.code === 'KeyM')   { sendAction('mode'); }
  if (e.key === '1') sendActionWithData('autocomplete', {idx:0});
  if (e.key === '2') sendActionWithData('autocomplete', {idx:1});
  if (e.key === '3') sendActionWithData('autocomplete', {idx:2});
  if (e.key === '4') sendActionWithData('autocomplete', {idx:3});
});

// ── Load collect data ─────────────────────────────────────────────────────────
function loadCollectData() {
  fetch('/api/collect/words')
    .then(r => r.json())
    .then(groups => {
      const container = document.getElementById('wordGroups');
      container.innerHTML = '';
      container.className = 'word-groups';

      groups.forEach(g => {
        const label = document.createElement('div');
        label.className = 'group-label';
        label.textContent = g.group.toUpperCase();
        container.appendChild(label);

        g.words.forEach(w => {
          const row = document.createElement('div');
          const done = w.count >= 240;
          row.className = `word-row ${done ? 'done' : ''}`;
          row.innerHTML = `
            <span class="word-name">${w.word}</span>
            <span class="word-count">
              ${w.count}
              ${done
                ? '<span class="check">✓</span>'
                : '<span class="circle">○</span>'}
            </span>`;
          container.appendChild(row);
        });
      });
    }).catch(() => {});
}

// ── Load train data ───────────────────────────────────────────────────────────
function loadTrainData() {
  fetch('/api/model/stats')
    .then(r => r.json())
    .then(d => {
      document.getElementById('statLetters').textContent = d.letter_classes;
      document.getElementById('statWords').textContent   = d.word_classes;

      const lc = document.getElementById('letterChips');
      lc.innerHTML = d.letter_words.map(w =>
        `<span class="chip">${w}</span>`).join('');

      const wc = document.getElementById('wordChips');
      wc.innerHTML = d.word_words.map(w =>
        `<span class="chip">${w}</span>`).join('');
    }).catch(() => {});
}

function runScript(type) {
  alert(`Run this in your terminal:\n\npython src/train_own_${type}_model.py`);
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadCollectData();
loadTrainData();