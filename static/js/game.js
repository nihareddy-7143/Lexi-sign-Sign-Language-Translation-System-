const GAME_LEVELS = [
  { type: "alphabets", label: "A-Z" },
  { type: "numbers", label: "1-9" },
  { type: "test", label: "Test" }
];

let gameState = {
  unlocked: 1,
  completed: []
};

// Start game
function startGame() {
  document.getElementById("gameMap").style.display = "flex";
  document.getElementById("gamePlay").style.display = "none";
  renderMap();
}

// Render map
function renderMap() {
  const map = document.getElementById('gameMap');
  map.innerHTML = "";

  GAME_LEVELS.forEach((lvl, index) => {
    const node = document.createElement('div');
    node.className = "level-node";
    node.textContent = lvl.label;

    if (index + 1 > gameState.unlocked) {
      node.classList.add("locked");
    } else {
      node.onclick = () => startLevel(index);
    }

    if (gameState.completed.includes(index)) {
      node.classList.add("completed");
    }

    map.appendChild(node);
  });
}

// Start level → delegate to tutor
function startLevel(index) {
  document.getElementById('gameMap').style.display = 'none';
  document.getElementById('gamePlay').style.display = 'block';

  startLessonFlow(index); // 🔥 comes from tutor.js
}