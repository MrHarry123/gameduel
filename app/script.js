const STORAGE_KEY = "quizDuelState";

const state = {
  games: [],
  saved: {
    players: ["Speler 1", "Speler 2"],
    games: {},
    namesConfirmed: false,
  },
  currentGame: null,
  turn: {
    hintsUsed: 0,
  },
};

const screens = {
  start: document.getElementById("start-screen"),
  select: document.getElementById("select-screen"),
  pass: document.getElementById("pass-screen"),
  quiz: document.getElementById("quiz-screen"),
  end: document.getElementById("end-screen"),
};

function showScreen(name) {
  Object.values(screens).forEach((s) => s.classList.remove("active"));
  screens[name].classList.add("active");
}

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function loadSaved() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      state.saved = {
        players: parsed.players || ["Speler 1", "Speler 2"],
        games: parsed.games || {},
        namesConfirmed: parsed.namesConfirmed === true,
      };
    }
  } catch (e) {
    console.warn("Kon opgeslagen status niet laden:", e);
  }
}

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.saved));
}

async function loadGames() {
  const indexResp = await fetch("games/index.json");
  const files = await indexResp.json();
  state.games = await Promise.all(
    files.map((file) => fetch(`games/${file}`).then((r) => r.json()))
  );
}

function ensureGameState(game) {
  let gs = state.saved.games[game.id];
  if (!gs) {
    const indices = game.questions.map((_, i) => i);
    gs = {
      shuffledOrder: shuffle(indices),
      currentIndex: 0,
      scores: [0, 0],
      askerIndex: Math.random() < 0.5 ? 0 : 1,
      completed: false,
      winner: null,
    };
    state.saved.games[game.id] = gs;
    persist();
  }
  return gs;
}

function resetGameState(game) {
  delete state.saved.games[game.id];
  persist();
  return ensureGameState(game);
}

function gameStatus(game) {
  const gs = state.saved.games[game.id];
  if (!gs) return { label: "Nog niet gestart", state: "new" };
  if (gs.completed) {
    if (gs.winner === "tie") {
      return { label: "Voltooid · gelijkspel", state: "tie" };
    }
    return { label: `Voltooid · ${gs.winner} wint`, state: "won" };
  }
  return {
    label: `Bezig · vraag ${gs.currentIndex + 1} / ${game.questions.length}`,
    state: "progress",
  };
}

/* ====== Startscherm ====== */
function initStartScreen() {
  const p1 = document.getElementById("player1");
  const p2 = document.getElementById("player2");
  if (state.saved.namesConfirmed) {
    p1.value = state.saved.players[0];
    p2.value = state.saved.players[1];
  } else {
    p1.value = "";
    p2.value = "";
  }
}

function submitNames() {
  const p1 = document.getElementById("player1").value.trim() || "Speler 1";
  const p2 = document.getElementById("player2").value.trim() || "Speler 2";
  state.saved.players = [p1, p2];
  state.saved.namesConfirmed = true;
  persist();
  renderSelectScreen();
  showScreen("select");
}

/* ====== Selectiescherm ====== */
function renderSelectScreen() {
  const [p1, p2] = state.saved.players;
  document.getElementById("select-subtitle").textContent = `${p1} vs ${p2}`;

  const gridClassic = document.getElementById("games-grid-classic");
  const gridStatements = document.getElementById("games-grid-statements");
  gridClassic.innerHTML = "";
  gridStatements.innerHTML = "";

  state.games.forEach((game) => {
    const status = gameStatus(game);
    const gs = state.saved.games[game.id];
    const scoreLine = gs
      ? `${state.saved.players[0]} ${gs.scores[0]} — ${gs.scores[1]} ${state.saved.players[1]}`
      : "";

    const mode = game.mode || "classic";
    const itemLabel = mode === "statements" ? "stellingen" : "vragen";
    const newBadge = game.locked ? "" : `<span class="game-new-badge">Nieuw</span>`;

    const card = document.createElement("button");
    card.className = `game-card status-${status.state}`;
    card.innerHTML = `
      <div class="game-emoji">${game.emoji || "❓"}</div>
      <div class="game-info">
        <div class="game-title">${game.title}${newBadge}</div>
        <div class="game-meta">${game.questions.length} ${itemLabel}</div>
        ${scoreLine ? `<div class="game-score">${scoreLine}</div>` : ""}
      </div>
      <div class="game-status">${status.label}</div>
    `;
    card.addEventListener("click", () => selectGame(game));
    (mode === "statements" ? gridStatements : gridClassic).appendChild(card);
  });

  document.getElementById("games-section-classic").hidden = gridClassic.children.length === 0;
  document.getElementById("games-section-statements").hidden = gridStatements.children.length === 0;
}

function selectGame(game) {
  const gs = ensureGameState(game);
  state.currentGame = game;

  if (gs.completed) {
    showEndScreen();
    return;
  }
  showPassScreen();
}

/* ====== Doorgeven ====== */
function showPassScreen() {
  const game = state.currentGame;
  const gs = state.saved.games[game.id];

  if (gs.currentIndex >= gs.shuffledOrder.length) {
    finishGame();
    return;
  }
  const askerName = state.saved.players[gs.askerIndex];
  document.getElementById("pass-name").textContent = askerName;
  showScreen("pass");
}

function startTurn() {
  state.turn.hintsUsed = 0;
  const game = state.currentGame;
  const gs = state.saved.games[game.id];
  const questionIndex = gs.shuffledOrder[gs.currentIndex];
  const item = game.questions[questionIndex];
  const mode = game.mode || "classic";

  const [p1, p2] = state.saved.players;
  const askerIndex = gs.askerIndex;

  document.getElementById("asker-name").textContent = state.saved.players[askerIndex];
  document.getElementById("answerer-name").textContent = state.saved.players[1 - askerIndex];
  document.getElementById("asker-label").textContent = p1;
  document.getElementById("answerer-label").textContent = p2;
  document.getElementById("asker-score").textContent = gs.scores[0];
  document.getElementById("answerer-score").textContent = gs.scores[1];

  const counterLabel = mode === "statements" ? "Ronde" : "Vraag";
  document.getElementById("question-counter").textContent =
    `${counterLabel} ${gs.currentIndex + 1} / ${gs.shuffledOrder.length}`;

  const quizScreen = document.getElementById("quiz-screen");
  quizScreen.setAttribute("data-mode", mode);

  if (mode === "statements") {
    document.getElementById("statements-prompt-text").textContent = item.prompt;
    renderStatements(item);
  } else {
    document.getElementById("question-text").textContent = item.question;
    document.getElementById("fullscreen-question-text").textContent = item.question;
    document.getElementById("answer-text").textContent = item.answer;
    renderHints(item.hints);
    updatePossiblePoints();
  }

  showScreen("quiz");
}

function renderStatements(item) {
  const list = document.getElementById("statements-list");
  list.innerHTML = "";
  state.turn.statementJudged = false;
  state.turn.statementCorrect = false;
  document.getElementById("statements-next-btn").hidden = true;
  item.statements.forEach((text, idx) => {
    const btn = document.createElement("button");
    btn.className = "statement-btn";
    btn.innerHTML = `<span class="statement-number">${idx + 1}</span><span class="statement-text">${text}</span>`;
    btn.addEventListener("click", () => handleStatementTap(idx, item.correctIndex));
    list.appendChild(btn);
  });
}

function handleStatementTap(tappedIndex, correctIndex) {
  if (state.turn.statementJudged) return;
  state.turn.statementJudged = true;
  state.turn.statementCorrect = tappedIndex === correctIndex;

  const buttons = document.querySelectorAll(".statement-btn");
  buttons.forEach((b, i) => {
    b.setAttribute("disabled", "");
    if (i === correctIndex) b.classList.add("correct");
    else if (i === tappedIndex) b.classList.add("wrong");
    else b.classList.add("dimmed");
  });

  document.getElementById("statements-next-btn").hidden = false;
}

function judgeStatement(correct) {
  const gs = state.saved.games[state.currentGame.id];
  const answererIndex = 1 - gs.askerIndex;
  if (correct) gs.scores[answererIndex] += 1;
  gs.currentIndex++;
  gs.askerIndex = 1 - gs.askerIndex;
  persist();
  showPassScreen();
}

function renderHints(hints) {
  const grid = document.getElementById("hints-grid");
  grid.innerHTML = "";
  hints.forEach((hint, idx) => {
    const btn = document.createElement("button");
    btn.className = "hint-btn";
    btn.innerHTML = `<span class="hint-number">${idx + 1}</span><span class="hint-text">${hint}</span>`;
    btn.addEventListener("click", () => revealHint(btn));
    grid.appendChild(btn);
  });
}

function revealHint(btn) {
  if (btn.classList.contains("revealed")) return;
  btn.classList.add("revealed");
  state.turn.hintsUsed++;
  updatePossiblePoints();
}

function updatePossiblePoints() {
  const points = Math.max(0, 5 - state.turn.hintsUsed);
  document.getElementById("possible-points").textContent = points;
}

function judgeAnswer(correct) {
  const game = state.currentGame;
  const gs = state.saved.games[game.id];
  const answererIndex = 1 - gs.askerIndex;

  if (correct) {
    const points = Math.max(0, 5 - state.turn.hintsUsed);
    gs.scores[answererIndex] += points;
  }
  gs.currentIndex++;
  gs.askerIndex = 1 - gs.askerIndex;
  persist();
  showPassScreen();
}

function finishGame() {
  const game = state.currentGame;
  const gs = state.saved.games[game.id];
  const [s1, s2] = gs.scores;
  const [p1, p2] = state.saved.players;

  gs.completed = true;
  if (s1 > s2) gs.winner = p1;
  else if (s2 > s1) gs.winner = p2;
  else gs.winner = "tie";

  persist();
  showEndScreen();
}

function showEndScreen() {
  const game = state.currentGame;
  const gs = state.saved.games[game.id];
  const [s1, s2] = gs.scores;
  const [p1, p2] = state.saved.players;

  document.getElementById("end-game-badge").textContent = `${game.emoji || ""} ${game.title}`;
  document.getElementById("final-name-1").textContent = p1;
  document.getElementById("final-points-1").textContent = s1;
  document.getElementById("final-name-2").textContent = p2;
  document.getElementById("final-points-2").textContent = s2;

  const card1 = document.getElementById("final-card-1");
  const card2 = document.getElementById("final-card-2");
  card1.classList.remove("winner");
  card2.classList.remove("winner");

  const winnerEl = document.getElementById("winner-text");
  if (s1 > s2) {
    card1.classList.add("winner");
    winnerEl.textContent = `🏆 ${p1} wint!`;
  } else if (s2 > s1) {
    card2.classList.add("winner");
    winnerEl.textContent = `🏆 ${p2} wint!`;
  } else {
    winnerEl.textContent = "Het is gelijkspel!";
  }

  showScreen("end");
}

function replayGame() {
  if (!state.currentGame) return;
  if (!confirm(`Spel "${state.currentGame.title}" opnieuw starten? Huidige punten worden gewist.`)) return;
  resetGameState(state.currentGame);
  showPassScreen();
}

function backToSelect() {
  state.currentGame = null;
  renderSelectScreen();
  showScreen("select");
}

function resetAll() {
  if (!confirm("Weet je zeker dat je alles opnieuw wilt starten? Alle punten en namen worden gewist.")) return;
  state.saved = {
    players: ["Speler 1", "Speler 2"],
    games: {},
    namesConfirmed: false,
  };
  persist();
  initStartScreen();
  showScreen("start");
}

function changePlayers() {
  initStartScreen();
  showScreen("start");
}

/* ====== Event handlers ====== */
document.getElementById("start-btn").addEventListener("click", submitNames);
document.getElementById("change-players-btn").addEventListener("click", changePlayers);
document.getElementById("reset-all-btn").addEventListener("click", resetAll);
document.getElementById("pass-btn").addEventListener("click", startTurn);
document.getElementById("correct-btn").addEventListener("click", () => judgeAnswer(true));
document.getElementById("wrong-btn").addEventListener("click", () => judgeAnswer(false));
document.getElementById("back-to-select-btn").addEventListener("click", backToSelect);
document.getElementById("replay-btn").addEventListener("click", replayGame);
document.getElementById("back-from-end-btn").addEventListener("click", backToSelect);
document.getElementById("statements-next-btn").addEventListener("click", () => {
  judgeStatement(state.turn.statementCorrect === true);
});

/* ====== Fullscreen vraag-overlay ====== */
const fullscreenEl = document.getElementById("question-fullscreen");
function openQuestionFullscreen() {
  fullscreenEl.classList.add("active");
  fullscreenEl.setAttribute("aria-hidden", "false");
}
function closeQuestionFullscreen() {
  fullscreenEl.classList.remove("active");
  fullscreenEl.setAttribute("aria-hidden", "true");
}
document.getElementById("question-card").addEventListener("click", openQuestionFullscreen);
document.getElementById("question-card").addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openQuestionFullscreen();
  }
});
fullscreenEl.addEventListener("click", closeQuestionFullscreen);

/* ====== Service worker ====== */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch((err) => {
      console.warn("Service worker registration failed:", err);
    });
  });
}

/* ====== Init ====== */
loadSaved();
initStartScreen();
loadGames()
  .then(() => {
    if (state.saved.namesConfirmed) {
      renderSelectScreen();
      showScreen("select");
    } else {
      showScreen("start");
    }
  })
  .catch((err) => {
    console.error("Kon spellen niet laden:", err);
    alert("Kon de spellen niet laden. Zorg dat je de app via een lokale server draait (bijv. 'python3 -m http.server').");
  });
