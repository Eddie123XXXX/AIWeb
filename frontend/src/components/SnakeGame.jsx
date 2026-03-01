import React, { useState, useRef, useEffect, useCallback } from 'react';

const COLS = 24;
const ROWS = 18;
const CELL_PX = 14;
const TICK_MS = 120;
const W = COLS * CELL_PX;
const H = ROWS * CELL_PX;

const DIR = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };

function randomCell() {
  return { x: Math.floor(Math.random() * COLS), y: Math.floor(Math.random() * ROWS) };
}

function initState() {
  const head = { x: Math.floor(COLS / 2), y: Math.floor(ROWS / 2) };
  const snake = [head, { x: head.x - 1, y: head.y }, { x: head.x - 2, y: head.y }];
  let food = randomCell();
  while (snake.some((s) => s.x === food.x && s.y === food.y)) food = randomCell();
  return { snake, food, dir: 'right', nextDir: 'right', score: 0, gameOver: false };
}

export function SnakeGame({ onClose, t }) {
  const [state, setState] = useState(initState);
  const tickRef = useRef(null);
  const canvasRef = useRef(null);
  const nextDirRef = useRef('right');

  const runTick = useCallback(() => {
    setState((prev) => {
      if (prev.gameOver) return prev;
      const dir = nextDirRef.current;
      const [dx, dy] = DIR[dir];
      const head = { x: prev.snake[0].x + dx, y: prev.snake[0].y + dy };
      if (head.x < 0 || head.x >= COLS || head.y < 0 || head.y >= ROWS) return { ...prev, gameOver: true };
      if (prev.snake.some((s) => s.x === head.x && s.y === head.y)) return { ...prev, gameOver: true };
      const newSnake = [head, ...prev.snake];
      let newFood = prev.food;
      let newScore = prev.score;
      if (head.x === prev.food.x && head.y === prev.food.y) {
        newScore += 1;
        newFood = randomCell();
        while (newSnake.some((s) => s.x === newFood.x && s.y === newFood.y)) newFood = randomCell();
      } else {
        newSnake.pop();
      }
      return { ...prev, snake: newSnake, food: newFood, dir, score: newScore };
    });
  }, []);

  useEffect(() => {
    tickRef.current = setInterval(runTick, TICK_MS);
    return () => clearInterval(tickRef.current);
  }, [runTick]);

  useEffect(() => {
    const onKey = (e) => {
      const k = e.key.toLowerCase();
      const isArrow = ['arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k);
      const isWASD = ['w', 'a', 's', 'd'].includes(k);
      if (!isArrow && !isWASD) return;
      e.preventDefault();
      setState((prev) => {
        if (prev.gameOver) return prev;
        if (k === 'arrowup' || k === 'w') { if (prev.dir !== 'down') nextDirRef.current = 'up'; }
        else if (k === 'arrowdown' || k === 's') { if (prev.dir !== 'up') nextDirRef.current = 'down'; }
        else if (k === 'arrowleft' || k === 'a') { if (prev.dir !== 'right') nextDirRef.current = 'left'; }
        else if (k === 'arrowright' || k === 'd') { if (prev.dir !== 'left') nextDirRef.current = 'right'; }
        return prev;
      });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#2d2d2d';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#444';
    ctx.lineWidth = 1;
    ctx.strokeRect(0, 0, W, H);
    state.snake.forEach((seg, i) => {
      ctx.fillStyle = i === 0 ? '#6366f1' : '#818cf8';
      ctx.fillRect(seg.x * CELL_PX + 1, seg.y * CELL_PX + 1, CELL_PX - 2, CELL_PX - 2);
    });
    ctx.fillStyle = '#22c55e';
    ctx.fillRect(state.food.x * CELL_PX + 2, state.food.y * CELL_PX + 2, CELL_PX - 4, CELL_PX - 4);
  }, [state.snake, state.food]);

  const restart = () => {
    nextDirRef.current = 'right';
    setState(initState());
  };

  return (
    <div className="snake-game" tabIndex={0}>
      <div className="snake-game__header">
        <span className="snake-game__score">{t?.('snakeScore') ?? '得分'}: {state.score}</span>
        {state.gameOver && (
          <span className="snake-game__over">{t?.('snakeGameOver') ?? '游戏结束'}</span>
        )}
      </div>
      <canvas ref={canvasRef} className="snake-game__canvas" width={W} height={H} style={{ width: W, height: H }} />
      <p className="snake-game__hint">{t?.('snakeHint') ?? '方向键或 WASD 控制'}</p>
      <div className="snake-game__actions">
        {state.gameOver ? (
          <button type="button" className="snake-game__btn" onClick={restart}>
            {t?.('snakeRestart') ?? '再来一局'}
          </button>
        ) : null}
        <button type="button" className="snake-game__btn snake-game__btn--primary" onClick={onClose}>
          {t?.('snakeClose') ?? '关闭'}
        </button>
      </div>
    </div>
  );
}
