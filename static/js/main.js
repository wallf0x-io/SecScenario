// SecScenario — theme toggle (works on every page)
(function () {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('secscenario.theme', next); } catch (_) {}
  });
})();

// SecScenario — upload page interactions
(function () {
  // Source tab switcher (File / Blog URL / Report URL)
  const tabs = document.querySelectorAll('.source-tab');
  const panels = document.querySelectorAll('.source-panel');
  if (tabs.length) {
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const src = tab.dataset.src;
        tabs.forEach(t => t.classList.toggle('active', t === tab));
        panels.forEach(p => {
          const show = p.dataset.panel === src;
          p.hidden = !show;
        });
      });
    });
  }

  // URL form: show spinner on submit
  document.querySelectorAll('.url-form').forEach((form) => {
    form.addEventListener('submit', (e) => {
      const btn = form.querySelector('button[type="submit"]');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Fetching…';
      }
    });
  });

  const dropZone = document.getElementById('drop-zone');
  if (!dropZone) return;

  const form = document.getElementById('upload-form');
  const inputFolder = document.getElementById('file-input');
  const inputFiles = document.getElementById('file-input-files');
  const pickFilesBtn = document.getElementById('pick-files');
  const pickFolderBtn = document.getElementById('pick-folder');
  const fileList = document.getElementById('file-list');
  const submitBtn = document.getElementById('submit-btn');

  const dataTransfer = new DataTransfer();

  function humanSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function render() {
    fileList.innerHTML = '';
    Array.from(dataTransfer.files).forEach((file, idx) => {
      const li = document.createElement('li');
      const name = file.webkitRelativePath || file.name;
      li.innerHTML = `
        <span>📄 ${name}</span>
        <span><span class="size">${humanSize(file.size)}</span>
          <button type="button" class="remove" data-idx="${idx}" title="Remove">×</button>
        </span>`;
      fileList.appendChild(li);
    });
    submitBtn.disabled = dataTransfer.files.length === 0;
    syncInputs();
  }

  function syncInputs() {
    inputFiles.files = dataTransfer.files;
  }

  function addFiles(files) {
    for (const f of files) {
      dataTransfer.items.add(f);
    }
    render();
  }

  fileList.addEventListener('click', (e) => {
    if (e.target.classList.contains('remove')) {
      const idx = parseInt(e.target.dataset.idx, 10);
      dataTransfer.items.remove(idx);
      render();
    }
  });

  pickFilesBtn.addEventListener('click', () => inputFiles.click());
  pickFolderBtn.addEventListener('click', () => inputFolder.click());

  inputFiles.addEventListener('change', (e) => addFiles(e.target.files));
  inputFolder.addEventListener('change', (e) => addFiles(e.target.files));

  dropZone.addEventListener('click', (e) => {
    if (e.target === dropZone || e.target.classList.contains('drop-inner')) {
      inputFiles.click();
    }
  });

  ['dragenter', 'dragover'].forEach(ev =>
    dropZone.addEventListener(ev, (e) => {
      e.preventDefault(); e.stopPropagation();
      dropZone.classList.add('drag-over');
    })
  );
  ['dragleave', 'drop'].forEach(ev =>
    dropZone.addEventListener(ev, (e) => {
      e.preventDefault(); e.stopPropagation();
      dropZone.classList.remove('drag-over');
    })
  );
  dropZone.addEventListener('drop', async (e) => {
    const items = e.dataTransfer.items;
    const collected = [];
    if (items && items.length && items[0].webkitGetAsEntry) {
      for (const it of items) {
        const entry = it.webkitGetAsEntry();
        if (entry) await walkEntry(entry, collected);
      }
    } else {
      for (const f of e.dataTransfer.files) collected.push(f);
    }
    addFiles(collected);
  });

  async function walkEntry(entry, out, path = '') {
    if (entry.isFile) {
      await new Promise((resolve) => {
        entry.file((file) => {
          // preserve relative path
          try {
            Object.defineProperty(file, 'webkitRelativePath', {
              value: path + entry.name, configurable: true,
            });
          } catch (_) {}
          out.push(file); resolve();
        });
      });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      await new Promise((resolve) => {
        reader.readEntries(async (entries) => {
          for (const e of entries) {
            await walkEntry(e, out, path + entry.name + '/');
          }
          resolve();
        });
      });
    }
  }

  form.addEventListener('submit', () => {
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Uploading...';
  });
})();
