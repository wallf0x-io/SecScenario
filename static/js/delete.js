// SecScenario — delete buttons for reports & challenges
(function () {
  async function doDelete(btn, url, itemLabel) {
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>';
    try {
      const res = await fetch(url, { method: 'POST' });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Delete failed');
      if (data.redirect) {
        window.location.href = data.redirect;
        return;
      }
      const row = btn.closest('.list-row');
      if (row) row.remove();
    } catch (e) {
      alert(`Couldn't delete ${itemLabel}: ${e.message}`);
      btn.disabled = false;
      btn.innerHTML = orig;
    }
  }

  document.addEventListener('click', (e) => {
    const reportBtn = e.target.closest('[data-del-report]');
    if (reportBtn) {
      e.preventDefault(); e.stopPropagation();
      if (!confirm('Delete this report and ALL challenges built from it?\nThis cannot be undone.')) return;
      doDelete(reportBtn, `/report/${reportBtn.dataset.delReport}/delete`, 'report');
      return;
    }
    const challengeBtn = e.target.closest('[data-del-challenge]');
    if (challengeBtn) {
      e.preventDefault(); e.stopPropagation();
      if (!confirm('Delete this challenge? The running process will be stopped and files removed.')) return;
      doDelete(challengeBtn, `/challenge/${challengeBtn.dataset.delChallenge}/delete`, 'challenge');
      return;
    }
  });
})();
