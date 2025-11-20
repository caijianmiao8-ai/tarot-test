// blueprints/games/tic_tac_toe/static/games/tic_tac_toe/main.js

let board = ['', '', '', '', '', '', '', '', ''];
let currentPlayer = 'X';
let gameActive = true;
let difficulty = 'medium';
let scores = { player: 0, ai: 0, draw: 0 };

const winningConditions = [
  [0,1,2],[3,4,5],[6,7,8],
  [0,3,6],[1,4,7],[2,5,8],
  [0,4,8],[2,4,6]
];

const cells = document.querySelectorAll('.cell');
const statusDisplay = document.getElementById('status');
const difficultyBtns = document.querySelectorAll('.difficulty-btn');
const btnRestart = document.getElementById('btn-restart');

difficultyBtns.forEach(btn => {
  btn.addEventListener('click', function () {
    difficultyBtns.forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    difficulty = this.dataset.level;
    resetGame();
  });
});

cells.forEach(cell => cell.addEventListener('click', handleCellClick));
btnRestart.addEventListener('click', resetGame);

function handleCellClick(e){
  const cell = e.target;
  const index = parseInt(cell.dataset.index, 10);
  if (board[index] !== '' || !gameActive || currentPlayer !== 'X') return;

  makeMove(index, 'X');

  if (gameActive) {
    currentPlayer = 'O';
    statusDisplay.textContent = 'AI思考中...';
    setTimeout(aiMove, 500);
  }
}

function makeMove(index, player){
  board[index] = player;
  const cell = cells[index];
  cell.textContent = player;
  cell.classList.add(player.toLowerCase());
  cell.disabled = true;
  checkResult();
}

function aiMove(){
  if (!gameActive) return;

  let move;
  if (difficulty === 'easy') {
    move = (Math.random() < 0.3) ? getBestMove() : getRandomMove();
  } else if (difficulty === 'medium') {
    move = (Math.random() < 0.7) ? getBestMove() : getRandomMove();
  } else {
    move = getBestMove();
  }

  if (move !== -1) {
    makeMove(move, 'O');
    if (gameActive) {
      currentPlayer = 'X';
      statusDisplay.textContent = '你的回合';
    }
  }
}

function getRandomMove(){
  const available = [];
  for (let i=0;i<board.length;i++){
    if (board[i] === '') available.push(i);
  }
  return available.length ? available[Math.floor(Math.random()*available.length)] : -1;
}

function getBestMove(){
  let bestScore = -Infinity;
  let bestMove = -1;
  for (let i=0;i<board.length;i++){
    if (board[i] === '') {
      board[i] = 'O';
      const score = minimax(board, 0, false);
      board[i] = '';
      if (score > bestScore){
        bestScore = score;
        bestMove = i;
      }
    }
  }
  return bestMove;
}

function minimax(b, depth, isMaximizing){
  const result = checkWinner();
  if (result === 'O') return 10 - depth;
  if (result === 'X') return depth - 10;
  if (result === 'draw') return 0;

  if (isMaximizing){
    let bestScore = -Infinity;
    for (let i=0;i<b.length;i++){
      if (b[i] === ''){
        b[i] = 'O';
        const score = minimax(b, depth+1, false);
        b[i] = '';
        bestScore = Math.max(score, bestScore);
      }
    }
    return bestScore;
  } else {
    let bestScore = Infinity;
    for (let i=0;i<b.length;i++){
      if (b[i] === ''){
        b[i] = 'X';
        const score = minimax(b, depth+1, true);
        b[i] = '';
        bestScore = Math.min(score, bestScore);
      }
    }
    return bestScore;
  }
}

function checkWinner(){
  for (const [a,b,c] of winningConditions){
    if (board[a] && board[a] === board[b] && board[a] === board[c]){
      return board[a];
    }
  }
  if (!board.includes('')) return 'draw';
  return null;
}

function checkResult(){
  const winner = checkWinner();
  if (!winner) return;

  gameActive = false;

  if (winner === 'draw'){
    statusDisplay.textContent = '平局！';
    scores.draw++;
    document.getElementById('draw-score').textContent = scores.draw;
    return;
  }

  const isPlayer = (winner === 'X');
  statusDisplay.textContent = isPlayer ? '🎉 你赢了！' : 'AI获胜！';

  // 高亮胜利线
  for (const [a,b,c] of winningConditions){
    if (board[a] && board[a] === board[b] && board[a] === board[c]){
      cells[a].classList.add('winning');
      cells[b].classList.add('winning');
      cells[c].classList.add('winning');
      break;
    }
  }

  if (isPlayer){
    scores.player++;
    document.getElementById('player-score').textContent = scores.player;
  } else {
    scores.ai++;
    document.getElementById('ai-score').textContent = scores.ai;
  }
}

function resetGame(){
  board = ['', '', '', '', '', '', '', '', ''];
  currentPlayer = 'X';
  gameActive = true;
  statusDisplay.textContent = '你的回合';
  cells.forEach(cell => {
    cell.textContent = '';
    cell.className = 'cell';
    cell.disabled = false;
  });
}
