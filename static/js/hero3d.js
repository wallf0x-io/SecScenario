/* Hero 3D scene — wireframe icosahedron + particle field, matches hacker theme.
   Pure Three.js, no extras. Lazy-inits only if THREE is loaded and
   #hero3d div exists. Respects prefers-reduced-motion.
*/
(function () {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var mount = document.getElementById('hero3d');
  if (!mount || typeof THREE === 'undefined') return;

  var width = mount.clientWidth;
  var height = mount.clientHeight;

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 100);
  camera.position.z = 5.2;

  var renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  renderer.setClearColor(0x000000, 0);
  mount.appendChild(renderer.domElement);

  function themeColors() {
    var isLight = document.documentElement.getAttribute('data-theme') === 'light';
    return isLight
      ? { primary: 0x0072c6, secondary: 0x008f59, accent: 0x6845ff }
      : { primary: 0x00d9ff, secondary: 0x00ff9d, accent: 0x7c5cff };
  }

  var col = themeColors();

  // Core wireframe icosahedron (hacker / tech feel)
  var coreGeom = new THREE.IcosahedronGeometry(1.55, 1);
  var coreMat = new THREE.MeshBasicMaterial({
    color: col.primary, wireframe: true, transparent: true, opacity: 0.85,
  });
  var core = new THREE.Mesh(coreGeom, coreMat);
  scene.add(core);

  // Glowy inner solid (low opacity) — gives depth
  var inner = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.15, 0),
    new THREE.MeshBasicMaterial({ color: col.accent, transparent: true, opacity: 0.08 })
  );
  scene.add(inner);

  // Orbiting torus ring
  var ringGeom = new THREE.TorusGeometry(2.4, 0.012, 6, 120);
  var ringMat = new THREE.MeshBasicMaterial({
    color: col.secondary, transparent: true, opacity: 0.55,
  });
  var ring = new THREE.Mesh(ringGeom, ringMat);
  ring.rotation.x = Math.PI / 2.4;
  scene.add(ring);

  var ring2 = new THREE.Mesh(
    new THREE.TorusGeometry(2.9, 0.006, 6, 120),
    new THREE.MeshBasicMaterial({ color: col.primary, transparent: true, opacity: 0.35 })
  );
  ring2.rotation.x = Math.PI / 3;
  ring2.rotation.z = Math.PI / 5;
  scene.add(ring2);

  // Starfield particles
  var starCount = 380;
  var starGeom = new THREE.BufferGeometry();
  var positions = new Float32Array(starCount * 3);
  for (var i = 0; i < starCount; i++) {
    positions[i * 3] = (Math.random() - 0.5) * 14;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 8;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 10 - 2;
  }
  starGeom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  var starMat = new THREE.PointsMaterial({
    color: col.secondary, size: 0.025, transparent: true, opacity: 0.75,
  });
  var stars = new THREE.Points(starGeom, starMat);
  scene.add(stars);

  // Cursor-driven rotation. Track normalized pointer, drive core spin toward it.
  var mx = 0, my = 0;       // normalized [-1, 1] for camera parallax
  var targetRX = 0, targetRY = 0;  // target rotation for core (radians)
  window.addEventListener('pointermove', function (e) {
    mx = (e.clientX / window.innerWidth) * 2 - 1;
    my = (e.clientY / window.innerHeight) * 2 - 1;
    // Map cursor → target rotation. Horizontal cursor = yaw, vertical = pitch.
    targetRY = mx * Math.PI;        // full left↔right = ±180°
    targetRX = my * (Math.PI * 0.6); // vertical = ±108°
  }, { passive: true });

  // Resize
  function resize() {
    var w = mount.clientWidth, h = mount.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', resize);

  // Theme change — swap colors live
  var observer = new MutationObserver(function () {
    var c = themeColors();
    coreMat.color.setHex(c.primary);
    inner.material.color.setHex(c.accent);
    ringMat.color.setHex(c.secondary);
    ring2.material.color.setHex(c.primary);
    starMat.color.setHex(c.secondary);
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  // Animate
  var running = true;
  document.addEventListener('visibilitychange', function () {
    running = !document.hidden;
    if (running) tick();
  });

  // Idle ambient drift when cursor sits still, so it's never frozen.
  var idleSpin = 0;
  function tick() {
    if (!running) return;
    idleSpin += 0.0025;

    // Lerp core + inner toward cursor-driven target, plus gentle idle wobble.
    core.rotation.y += (targetRY - core.rotation.y) * 0.08 + 0.0015;
    core.rotation.x += (targetRX - core.rotation.x) * 0.08;
    inner.rotation.y += (targetRY - inner.rotation.y) * 0.06 - 0.0010;
    inner.rotation.x += (targetRX * 0.7 - inner.rotation.x) * 0.06;

    // Rings + stars stay ambient so scene never fully freezes.
    ring.rotation.z += 0.003;
    ring.rotation.x += Math.sin(idleSpin) * 0.0006;
    ring2.rotation.z -= 0.002;
    stars.rotation.y += 0.0006;

    // Camera parallax (subtle, keeps perspective shift)
    camera.position.x += (mx * 0.6 - camera.position.x) * 0.04;
    camera.position.y += (-my * 0.4 - camera.position.y) * 0.04;
    camera.lookAt(0, 0, 0);

    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }
  tick();
})();
