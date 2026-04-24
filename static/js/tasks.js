// SecScenario — CTF task submission + scoring
(function () {
  const panel = document.getElementById('tasks-panel');
  if (!panel) return;

  const id = panel.dataset.id;
  const tasks = panel.querySelectorAll('.task');
  const scoreDone = document.getElementById('score-done');
  const scoreFill = document.getElementById('score-fill');
  const total = tasks.length;

  function recomputeScore() {
    const solved = panel.querySelectorAll('.task[data-solved="1"]').length;
    scoreDone.textContent = solved;
    scoreFill.style.width = (100 * solved / total).toFixed(1) + '%';
  }

  tasks.forEach((task) => {
    const input = task.querySelector('.task-answer');
    const btn = task.querySelector('.task-submit');
    const state = task.querySelector('.task-state');

    async function submit() {
      const n = task.dataset.n;
      const answer = input.value.trim();
      if (!answer) return;
      btn.disabled = true;
      const origBtnText = btn.textContent;
      btn.innerHTML = '<span class="spinner"></span>';
      try {
        const res = await fetch(`/challenge/${id}/submit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_n: n, answer: answer }),
        });
        const data = await res.json();
        if (data.ok && data.correct) {
          task.dataset.solved = '1';
          state.dataset.state = 'solved';
          state.textContent = '✓ Solved';
          input.disabled = true;
          btn.hidden = true;
          task.classList.add('solved');
          recomputeScore();
          // celebrate flag task
          if (n === '999' || task.querySelector('.task-q').textContent.toLowerCase().includes('flag')) {
            confettiBurst();
          }
        } else {
          state.dataset.state = 'wrong';
          state.textContent = '✗ Try again';
          task.classList.add('shake');
          setTimeout(() => task.classList.remove('shake'), 400);
          btn.disabled = false;
          btn.textContent = origBtnText;
        }
      } catch (e) {
        state.dataset.state = 'wrong';
        state.textContent = 'Error';
        btn.disabled = false;
        btn.textContent = origBtnText;
      }
    }

    btn.addEventListener('click', submit);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') submit();
    });
  });

  function confettiBurst() {
    const host = document.createElement('div');
    host.className = 'confetti-host';
    document.body.appendChild(host);
    const colors = ['#7c5cff', '#5fa8ff', '#2ecc71', '#f39c12', '#ff3860'];
    for (let i = 0; i < 80; i++) {
      const p = document.createElement('span');
      p.className = 'confetti-piece';
      p.style.background = colors[i % colors.length];
      p.style.left = (Math.random() * 100) + 'vw';
      p.style.animationDelay = (Math.random() * 0.4) + 's';
      p.style.animationDuration = (1.2 + Math.random() * 1.5) + 's';
      host.appendChild(p);
    }
    setTimeout(() => host.remove(), 3200);
  }
})();
