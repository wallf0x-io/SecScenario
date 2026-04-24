// SecScenario — report page: analyze + generate actions
(function () {
  const analyzeBtn = document.getElementById('analyze-btn');
  const generateBtn = document.getElementById('generate-btn');
  const analysisBody = document.getElementById('analysis-body');
  const challengePanel = document.getElementById('challenge-panel');
  const generateStatus = document.getElementById('generate-status');

  function spinnerHTML(label) {
    return `<span class="spinner"></span> ${label}`;
  }

  if (analyzeBtn) {
    analyzeBtn.addEventListener('click', async () => {
      const id = analyzeBtn.dataset.id;
      analyzeBtn.disabled = true;
      const orig = analyzeBtn.innerHTML;
      analyzeBtn.innerHTML = spinnerHTML('Analyzing…');
      analysisBody.innerHTML = '<p class="muted">Claude is reading the report and extracting vulnerability details… this usually takes 10–30 seconds.</p>';
      try {
        const res = await fetch(`/report/${id}/analyze`, { method: 'POST' });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Analysis failed');
        window.location.reload();
      } catch (e) {
        analysisBody.innerHTML = `<div class="flash flash-error">Analysis failed: ${e.message}</div>`;
        analyzeBtn.disabled = false;
        analyzeBtn.innerHTML = orig;
      }
    });
  }

  if (generateBtn) {
    generateBtn.addEventListener('click', async () => {
      const id = generateBtn.dataset.id;
      generateBtn.disabled = true;
      const orig = generateBtn.innerHTML;
      generateBtn.innerHTML = spinnerHTML('Building…');
      generateStatus.innerHTML = '<span class="spinner"></span> Claude is designing and writing the challenge files… 20–60 seconds.';
      try {
        const res = await fetch(`/report/${id}/generate`, { method: 'POST' });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Generation failed');
        generateStatus.innerHTML = `✅ Challenge built! <a href="/challenge/${data.challenge_id}">Open challenge →</a>`;
        setTimeout(() => { window.location.href = `/challenge/${data.challenge_id}`; }, 800);
      } catch (e) {
        generateStatus.innerHTML = `<span style="color:var(--err)">Generation failed: ${e.message}</span>`;
        generateBtn.disabled = false;
        generateBtn.innerHTML = orig;
      }
    });
  }
})();
