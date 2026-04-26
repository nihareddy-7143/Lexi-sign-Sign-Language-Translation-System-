// ── GAME FLOW ─────────────────────────────────────
const GAME_LEVELS = [
  { name: "Alphabets", type: "alphabets", color: "#6C63FF" },
  { name: "Numbers", type: "numbers", color: "#00C9A7" },
  { name: "Words", type: "words", color: "#FF8C42" },     // ✅ added
  { name: "Final Test", type: "test", color: "#FF3D6E" }   // ✅ added
];

let gameState = {
  currentLevel: 0,
  items: [],
  index: 0,
  correctAnswers: 0,
  unlockedLevels: [true, false, false, false] // match levels
};





let playerStats = {
  xp: 0,
  streak: 0
};

// 🎵 MUSIC
const bgMusic = new Audio('/static/sounds/bg-music.mp3');
bgMusic.loop = true;
bgMusic.volume = 0.3;

// 🔊 SOUND
const sounds = {
  correct: new Audio('/static/sounds/correct.mp3')
};

// ── START GAME ────────────────────────────────────
function startGame() {
  loadProgress();
  renderMap();
  bgMusic.play().catch(() => {});
}

// ── MAP ───────────────────────────────────────────
function renderMap() {
  const map = document.getElementById("gameMap");

  map.innerHTML = `

  <div class="center-section">

    <div class="quote-section">
  <img src="/static/images/hero-lexisign.jpg" class="quote-img" />

  <div class="big-quote">
    “Learning never exhausts the mind — it only ignites it.” ✨
  </div>
</div>

    <div class="score-card">
      <div class="xp-box">
        <span>⚡ XP</span>
        <h1>${playerStats.xp}</h1>
      </div>
      <div class="streak-box">
        <span>🔥 Streak</span>
        <h1>${playerStats.streak}</h1>
      </div>
    </div>

    <div class="map-center">
      <h1 id="dynamicText"></h1>
    </div>

  </div>

  <div class="map-path"></div>
`;

  startTypingEffect(); 

  const path = map.querySelector(".map-path");

  GAME_LEVELS.forEach((lvl, i) => {

  const isUnlocked = gameState.unlockedLevels[i]; // ✅ correct source

  const node = document.createElement("div");

  node.className = `map-node ${isUnlocked ? "active" : "locked"}`;

  node.innerHTML = `
    <div class="bubble" style="background:${isUnlocked ? lvl.color : "#444"}">
      ${i + 1}
    </div>
    <span>${lvl.name}</span>
  `;

  node.style.marginLeft = (i % 2 === 0) ? "0px" : "120px";

  if (isUnlocked) {
    node.onclick = () => startLevel(i); // ✅ clickable ONLY if unlocked
  }

  path.appendChild(node);
});
}

function startTypingEffect() {
  const messages = [
    "Every sign you learn is a voice you give 🤟",
    "Small steps → Fluent conversations 🚀",
    "Consistency beats talent 🔥",
    "Learn. Practice. Express."
  ];

  let msgIndex = 0;
  let charIndex = 0;
  const speed = 50;

  const textEl = document.getElementById("dynamicText");

  function type() {
    if (!textEl) return;

    if (charIndex < messages[msgIndex].length) {
      textEl.innerHTML += messages[msgIndex].charAt(charIndex);
      charIndex++;
      setTimeout(type, speed);
    } else {
      setTimeout(() => {
        textEl.innerHTML = "";
        charIndex = 0;
        msgIndex = (msgIndex + 1) % messages.length;
        type();
      }, 1500);
    }
  }

  textEl.innerHTML = "";
  type();
}
// ── START LEVEL ───────────────────────────────────
function startLevel(levelIndex) {
  gameState.currentLevel = levelIndex;
  gameState.index = 0;
  gameState.correctAnswers = 0;

  document.getElementById("gameMap").style.display = "none";
  document.getElementById("gamePlay").style.display = "block";

  fetch('/api/camera', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({action:'start'})
  });

  const level = GAME_LEVELS[levelIndex];

  if (level.type === "test") {
    startTestLevel();
    return;
  }

  fetch(`/api/tutor/lesson/${level.type}`)
    .then(r => r.json())
    .then(data => {
      gameState.items = data.items;
      renderLevel();
    });
}

// ── LEVEL UI ──────────────────────────────────────
function renderLevel() {
  const item = gameState.items[gameState.index];

  if (!item) {
    console.error("Invalid item");
    return;
  }

  window.answered = false;

  // ✅ MOVE LOGIC HERE (outside HTML)
  const isWordLevel = GAME_LEVELS[gameState.currentLevel].type === "words";

  const mediaHTML = isWordLevel
    ? `
      <video class="target-sign" autoplay loop muted playsinline>
        <source src="/static/signs/videos/${item.toLowerCase()}.mp4" type="video/mp4">
      </video>
    `
    : `
      <img 
        src="/static/signs/${GAME_LEVELS[gameState.currentLevel].type}/${item}.png" 
        class="target-sign"
        onerror="this.src='/static/fallback.png'"
      >
    `;

  // ✅ ONLY HTML BELOW
  document.getElementById("gamePlay").innerHTML = `
  <div class="game-container">

    <div class="left-panel">
      <h1 class="target-letter">${item.toUpperCase()}</h1>

      ${mediaHTML}

      <p class="hint-text">Match this sign using your hand</p>
    </div>

    <div class="right-panel">

      <div class="camera-box">
        <img src="/video_feed" class="camera-feed"/>
      </div>

      <div class="prediction-box">
        <p>Detected: <span id="predictedLetter">-</span></p>
        <p>Accuracy: <span id="predictedAccuracy">0%</span></p>
      </div>

      <div class="accuracy-bar">
        <div id="accuracyFill"></div>
      </div>

      <button class="back-btn" onclick="backToMap()">⬅ Back</button>

    </div>

  </div>
  `;

  startDetection(item);
}
// ── DETECTION ─────────────────────────────────────
function startDetection(target) {
  if (window.detectInterval) clearInterval(window.detectInterval);

  window.answered = false; // ✅ reset for new question

  window.detectInterval = setInterval(() => {
    fetch('/api/state')
      .then(res => res.json())
      .then(s => {

        const detectedRaw = s.detected || "";
        const detected = detectedRaw.toUpperCase();
        const accuracy = s.confidence || 0;

        // UI updates
        document.getElementById("predictedLetter").textContent = detected;
        document.getElementById("predictedAccuracy").textContent = accuracy + "%";
        document.getElementById("accuracyFill").style.width = accuracy + "%";

        // ✅ NORMALIZATION (VERY IMPORTANT)
        const normalize = (str) =>
          (str || "").replace(/[_\s]+/g, '').toLowerCase();

        const isWordLevel =
          GAME_LEVELS[gameState.currentLevel].type === "words";

        const targetMatch = isWordLevel
          ? normalize(detectedRaw) === normalize(target)
          : detected === target.toUpperCase();

        console.log("Detected:", detectedRaw);
        console.log("Target:", target);
        console.log("Match:", targetMatch);

        // ✅ PREVENT MULTIPLE TRIGGERS
        if (!window.answered && targetMatch && accuracy >= 90) {
  window.answered = true;

  gameState.correctAnswers++;

  // ✅ NEW: Unlock Final Test after 1 correct word
  const isWordLevel =
    GAME_LEVELS[gameState.currentLevel].type === "words";

  if (isWordLevel && gameState.correctAnswers === 1) {
    const finalTestIndex = GAME_LEVELS.findIndex(l => l.type === "test");

    if (finalTestIndex !== -1) {
      gameState.unlockedLevels[finalTestIndex] = true;
      saveProgress();
      console.log("🔥 Final Test Unlocked!");
    }
  }

  clearInterval(window.detectInterval);

  showCorrectAnimation();
  sounds.correct.play();

  playerStats.xp += 10;
  playerStats.streak++;

  setTimeout(() => {
    nextLevelItem();
  }, 700);
}

      })
      .catch(() => console.log("Error fetching state"));
  }, 300);
}
// ── NEXT ITEM ─────────────────────────────────────
function nextLevelItem() {
  if (gameState.index < gameState.items.length - 1) {
    gameState.index++;
    renderLevel();
  } else {
    finishLevel();
  }
}

// ── LEVEL COMPLETE ────────────────────────────────
function finishLevel() {

  const passed = gameState.correctAnswers >= 3;

  // ✅ unlock ONLY after level ends
  if (passed && gameState.currentLevel + 1 < GAME_LEVELS.length) {
    gameState.unlockedLevels[gameState.currentLevel + 1] = true;
    saveProgress();
  }

  document.getElementById("gamePlay").innerHTML = `
    <div class="game-card">
      <h2>${passed ? "🎉 Level Passed!" : "😅 Try Again"}</h2>
      <p>Correct: ${gameState.correctAnswers}</p>

      ${
        passed
          ? `<button onclick="goNextLevel()">Next Level →</button>`
          : `<button onclick="startLevel(${gameState.currentLevel})">Retry</button>`
      }

      <button onclick="backToMap()">Back</button>
    </div>
  `;
  
}

function goNextLevel() {

  if (gameState.currentLevel + 1 < GAME_LEVELS.length) {
  gameState.unlockedLevels[gameState.currentLevel + 1] = true;
}

  gameState.currentLevel++;

  saveProgress();

  startLevel(gameState.currentLevel);
}

// ── BACK ─────────────────────────────────────────
function backToMap() {
  clearInterval(window.detectInterval);

  saveProgress(); // 🔥 ADD THIS

  bgMusic.pause();

  fetch('/api/camera', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({action:'stop'})
  });

  document.getElementById("gamePlay").style.display = "none";
  document.getElementById("gameMap").style.display = "flex";

  renderMap();
}




// ── TEST MODE ─────────────────────────────────────
function startTestLevel() {
  // 🎲 Combine all data
  const allItems = [
    ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ..."123456789",
    ..."No water yes THANK_YOU I_Love_You my_name".split(" ")
  ];

  // 🎲 Shuffle
  gameState.items = shuffleArray(allItems);

  gameState.index = 0;
  gameState.score = 0;
  gameState.totalQuestions = 15; // 🔥 control difficulty
  gameState.timeLeft = 60; // seconds

  startTestTimer();
  renderTest();
}


function shuffleArray(arr) {
  return arr.sort(() => Math.random() - 0.5);
}


function startTestTimer() {
  clearInterval(window.testTimer);

  window.testTimer = setInterval(() => {
    gameState.timeLeft--;

    const timerEl = document.getElementById("timer");
    if (timerEl) timerEl.textContent = gameState.timeLeft;

    if (gameState.timeLeft <= 0) {
      clearInterval(window.testTimer);
      showFinalScore();
    }
  }, 1000);
}

function renderTest() {
  const item = gameState.items[gameState.index];

  const isWord = item.length > 1;
  const isNumber = !isNaN(item);

  // 🎥 MEDIA HANDLING
  let mediaHTML = "";

  if (isWord) {
    mediaHTML = `
      <video class="test-media" autoplay loop muted playsinline>
        <source src="/static/signs/videos/${item.toLowerCase()}.mp4" type="video/mp4">
      </video>
    `;
  } else {
    mediaHTML = `
      <img 
        src="/static/signs/${isNumber ? 'numbers' : 'alphabets'}/${item}.png"
        class="test-media"
      >
    `;
  }

  const options = generateOptions(item);

  document.getElementById("gamePlay").innerHTML = `
    <div class="test-container">

      <div class="test-header">
        <div>⏱ ${gameState.timeLeft}s</div>
        <div>🎯 ${gameState.score}</div>
      </div>

      <div class="test-media-box">
        ${mediaHTML}
      </div>

      <div class="options-grid">
        ${options.map(opt => `
          <button class="option-btn" onclick="submitMCQ('${opt}', '${item}')">
            ${opt}
          </button>
        `).join('')}
      </div>

    </div>
  `;
}

function generateOptions(correct) {
  const pool = [
    ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ..."123456789"
  ];

  let options = [correct];

  while (options.length < 4) {
    const rand = pool[Math.floor(Math.random() * pool.length)];
    if (!options.includes(rand)) options.push(rand);
  }

  return shuffleArray(options);
}

function submitMCQ(selected, correct) {
  const buttons = document.querySelectorAll(".option-btn");

  buttons.forEach(btn => {
    if (btn.innerText === correct) {
      btn.style.background = "green";
    } else if (btn.innerText === selected) {
      btn.style.background = "red";
    }
    btn.disabled = true;
  });

  if (selected === correct) {
    gameState.score++;
    showCorrectAnimation();
  }

  setTimeout(() => {
    nextTestQuestion();
  }, 600);
}

function nextTestQuestion() {
  if (gameState.index < gameState.totalQuestions - 1) {
    gameState.index++;
    renderTest();
  } else {
    showFinalScore();
  }
}

function submitTest() {
  const ans = document.getElementById("testInput").value.toUpperCase();
  if (ans === gameState.items[gameState.index]) gameState.score++;

  if (gameState.index < gameState.items.length - 1) {
    gameState.index++;
    renderTest();
  } else {
    showFinalScore();
  }
}

function showFinalScore() {
  clearInterval(window.testTimer);

  const percentage = Math.round(
    (gameState.score / gameState.totalQuestions) * 100
  );

  document.getElementById("gamePlay").innerHTML = `
    <div class="game-card">
      <h2>🎉 Test Complete!</h2>
      <p>Score: ${gameState.score}/${gameState.totalQuestions}</p>
      <p>Accuracy: ${percentage}%</p>

      <button onclick="startTestLevel()">🔄 Retry</button>
      <button onclick="backToMap()">🏠 Back</button>
    </div>
  `;
}

// ── ANIMATION ─────────────────────────────────────
function showCorrectAnimation() {
  const el = document.createElement("div");
  el.className = "correct-popup";
  el.innerText = "✅ Correct!";
  document.body.appendChild(el);

  setTimeout(() => el.remove(), 1000);
}

// ── STORAGE ───────────────────────────────────────
function saveProgress() {
  localStorage.setItem("isl_progress", JSON.stringify({
    unlockedLevels: gameState.unlockedLevels,
    xp: playerStats.xp,
    streak: playerStats.streak
  }));
}

function loadProgress() {
  const data = JSON.parse(localStorage.getItem("isl_progress"));

  if (data) {
    gameState.unlockedLevels = data.unlockedLevels || [true, false, false, false];
    playerStats.xp = data.xp || 0;
    playerStats.streak = data.streak || 0;
  }
}

// ── INIT ──────────────────────────────────────────
window.onload = () => {
  loadProgress();
  renderMap();
};