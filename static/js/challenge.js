// SecScenario — challenge launcher (launch / stop / poll status)
(function () {
  const root = document.getElementById('launcher');
  if (!root) return;

  const id = root.dataset.id;
  const port = root.dataset.port;
  const launchBtn = document.getElementById('launch-btn');
  const stopBtn = document.getElementById('stop-btn');
  const openBtn = document.getElementById('open-btn');
  const statusDot = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');
  const logWrap = document.getElementById('runtime-log-wrap');
  const logBox = document.getElementById('runtime-log');
  const link = document.getElementById('challenge-link');

  let pollTimer = null;

  function setState(state, opts = {}) {
    statusDot.className = 'status-dot status-' + state;
    const labels = {
      running: 'Running',
      starting: 'Starting…',
      installing: 'Installing dependencies…',
      stopped: 'Stopped',
      crashed: 'Crashed — check log below',
      error: 'Error',
      unknown: 'Unknown',
    };
    statusText.textContent = labels[state] || state;

    if (state === 'running') {
      launchBtn.hidden = true;
      stopBtn.hidden = false;
      openBtn.hidden = false;
      link.classList.add('live');
    } else if (state === 'starting' || state === 'installing') {
      launchBtn.hidden = true;
      stopBtn.hidden = false;
      openBtn.hidden = true;
      link.classList.remove('live');
    } else {
      launchBtn.hidden = false;
      stopBtn.hidden = true;
      openBtn.hidden = true;
      link.classList.remove('live');
      launchBtn.disabled = false;
      launchBtn.innerHTML = '🚀 Launch Challenge';
    }

    if (opts.log) {
      logWrap.hidden = false;
      logBox.textContent = opts.log;
    }
  }

  async function refresh() {
    try {
      const res = await fetch(`/challenge/${id}/status`);
      const data = await res.json();
      if (!data.ok) { setState('error'); return data; }
      setState(data.state, { log: data.log });
      return data;
    } catch (e) {
      setState('error');
      return null;
    }
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(async () => {
      const data = await refresh();
      if (!data) return;
      if (data.state === 'running' || data.state === 'stopped' || data.state === 'crashed') {
        stopPolling();
      }
    }, 1500);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  launchBtn.addEventListener('click', async () => {
    launchBtn.disabled = true;
    launchBtn.innerHTML = '<span class="spinner"></span> Launching…';
    setState('installing');
    try {
      const res = await fetch(`/challenge/${id}/launch`, { method: 'POST' });
      const data = await res.json();
      if (!data.ok) {
        setState('error', { log: data.log || data.error });
        launchBtn.disabled = false;
        launchBtn.innerHTML = '🚀 Launch Challenge';
        return;
      }
      setState(data.state, { log: data.log });
      if (data.state === 'running') {
        // auto-open
        window.open(data.url, '_blank', 'noopener');
      } else {
        startPolling();
      }
    } catch (e) {
      setState('error');
      launchBtn.disabled = false;
      launchBtn.innerHTML = '🚀 Launch Challenge';
    }
  });

  stopBtn.addEventListener('click', async () => {
    stopBtn.disabled = true;
    try {
      await fetch(`/challenge/${id}/stop`, { method: 'POST' });
    } catch (_) {}
    stopBtn.disabled = false;
    await refresh();
  });

  openBtn.addEventListener('click', () => {
    window.open(link.href, '_blank', 'noopener');
  });

  // initial status
  refresh();
})();
