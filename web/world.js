// Low-poly 3D view: the MENDO Cloud floating above three locations,
// each with a MENDO vending machine, connected by lines.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const box = document.getElementById("world");
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
box.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color("#bfe3f5");
scene.fog = new THREE.Fog("#bfe3f5", 55, 110);
const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 300);
camera.position.set(0, 17, 36);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 6, -2);
controls.maxPolarAngle = 1.4;
controls.minDistance = 15;
controls.maxDistance = 70;
controls.enableDamping = true;

scene.add(new THREE.HemisphereLight(0xffffff, 0x7fae5a, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(15, 30, 15);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
Object.assign(sun.shadow.camera, { left: -35, right: 35, top: 35, bottom: -35 });
scene.add(sun);

const mat = c => new THREE.MeshStandardMaterial({ color: c, flatShading: true });
function mesh(geo, color, x = 0, y = 0, z = 0, parent = scene) {
  const m = new THREE.Mesh(geo, mat(color));
  m.position.set(x, y, z);
  m.castShadow = m.receiveShadow = true;
  parent.add(m);
  return m;
}
const B = (w, h, d) => new THREE.BoxGeometry(w, h, d);

// ---------------------------------------------------------------- ground
mesh(new THREE.CylinderGeometry(32, 34, 2, 12), "#7cc26a", 0, -1, 0);
mesh(new THREE.CylinderGeometry(34, 30, 3, 12), "#8a6a4a", 0, -3.5, 0);
mesh(new THREE.CylinderGeometry(4, 4, 0.1, 10), "#b9b9b0", 0, 0.05, 2);     // plaza
function tree(x, z) {
  mesh(new THREE.CylinderGeometry(0.25, 0.35, 1.4, 5), "#7a5432", x, 0.7, z);
  mesh(new THREE.ConeGeometry(1.3, 2.8, 6), "#3f9b4f", x, 2.6, z);
}
[[-24, -8], [-20, -16], [-26, 6], [-8, -18], [8, -18], [22, -14], [26, -4], [24, 12], [-16, 16],
 [4, 18], [16, 18], [-28, -2], [18, -20], [-6, 20]].forEach(([x, z]) => tree(x, z));

// ---------------------------------------------------------------- locations
const SITES = {
  "MENDO-01": { x: -14, z: 4, name: "Campus Clinic" },
  "MENDO-02": { x: 0, z: -9, name: "Barangay Health Center" },
  "MENDO-03": { x: 14, z: 4, name: "Transport Terminal" },
};
function road(x1, z1, x2, z2) {
  const len = Math.hypot(x2 - x1, z2 - z1);
  const r = mesh(B(2.2, 0.08, len), "#5d6670", (x1 + x2) / 2, 0.04, (z1 + z2) / 2);
  r.rotation.y = Math.atan2(x2 - x1, z2 - z1);
}
Object.values(SITES).forEach(s => road(s.x, s.z + 3, 0, 2));

function clinic(g) {
  mesh(B(7, 4, 4.5), "#f4f1ea", 0, 2, 0, g);
  mesh(B(7.4, 0.4, 4.9), "#c9c3b5", 0, 4.2, 0, g);
  mesh(B(0.5, 1.6, 0.2), "#d64545", 0, 3, 2.3, g);
  mesh(B(1.6, 0.5, 0.2), "#d64545", 0, 3, 2.3, g);
  mesh(B(1.4, 2, 0.1), "#5b7a8c", -2, 1, 2.27, g);
}
function healthCenter(g) {
  mesh(B(7, 3.4, 4.5), "#f2dfa6", 0, 1.7, 0, g);
  const roof = mesh(new THREE.ConeGeometry(5.4, 2.4, 4), "#3a7ca5", 0, 4.6, 0, g);
  roof.rotation.y = Math.PI / 4;
  roof.scale.z = 0.7;
  mesh(B(1.4, 2, 0.1), "#7a5432", 1.8, 1, 2.27, g);
  mesh(B(1.4, 1, 0.1), "#9cc9e0", -1.8, 2, 2.27, g);
}
function terminal(g) {
  mesh(B(9, 0.3, 4.5), "#e07a3f", 0, 3.6, 0, g);
  [[-4, -2], [4, -2], [-4, 2], [4, 2]].forEach(([x, z]) => mesh(B(0.3, 3.6, 0.3), "#555", x, 1.8, z, g));
  mesh(B(3, 0.5, 0.8), "#8a6a4a", -2, 0.5, -1, g);
  const bus = new THREE.Group(); bus.position.set(-6.5, 0, -3); bus.rotation.y = Math.PI / 2; g.add(bus);
  mesh(B(5.5, 2.2, 2.2), "#f1c40f", 0, 1.5, 0, bus);
  mesh(B(5.6, 0.7, 2.25), "#2c3e50", 0, 1.9, 0, bus);
  [[-1.8, 1.1], [1.8, 1.1], [-1.8, -1.1], [1.8, -1.1]].forEach(([x, z]) => {
    const w = mesh(new THREE.CylinderGeometry(0.45, 0.45, 0.3, 8), "#222", x, 0.45, z, bus); w.rotation.x = Math.PI / 2;
  });
}
const BUILD = { "MENDO-01": clinic, "MENDO-02": healthCenter, "MENDO-03": terminal };

// ---------------------------------------------------------------- vending machines
const machines = {};
function screenTexture() {
  const c = document.createElement("canvas"); c.width = 320; c.height = 200;
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return { c, t };
}
function drawScreen(m, text) {
  const ctx = m.scr.c.getContext("2d");
  ctx.fillStyle = "#0b1d2a"; ctx.fillRect(0, 0, 320, 200);
  ctx.fillStyle = "#7fffd4"; ctx.font = "bold 22px Consolas, monospace";
  const lines = [];
  for (const raw of text.split("\n")) for (let i = 0; i < Math.max(raw.length, 1); i += 24) lines.push(raw.slice(i, i + 24));
  lines.slice(-7).forEach((l, i) => ctx.fillText(l, 12, 32 + i * 26));
  m.scr.t.needsUpdate = true;
}

for (const [id, s] of Object.entries(SITES)) {
  const site = new THREE.Group(); site.position.set(s.x, 0, s.z); scene.add(site);
  const building = new THREE.Group(); building.position.set(0, 0, -3); site.add(building);
  BUILD[id](building);

  const vm = new THREE.Group(); vm.position.set(0, 0, 1.2); site.add(vm);
  mesh(B(1.6, 2.8, 1.1), "#0f6e64", 0, 1.4, 0, vm);
  const scr = screenTexture();
  const screenMesh = new THREE.Mesh(new THREE.PlaneGeometry(1.3, 0.8), new THREE.MeshBasicMaterial({ map: scr.t }));
  screenMesh.position.set(0, 2.25, 0.56); vm.add(screenMesh);
  mesh(B(1.3, 0.9, 0.05), "#cfe9f5", 0, 1.3, 0.56, vm);                       // glass with medicines
  const colors = ["#e74c3c", "#e67e22", "#9b59b6", "#16a085", "#2980b9", "#8e44ad", "#27ae60", "#d35400", "#2c3e50", "#c0392b"];
  colors.forEach((c, i) => mesh(B(0.18, 0.22, 0.05), c, -0.48 + (i % 5) * 0.24, 1.5 - Math.floor(i / 5) * 0.4, 0.6, vm));
  mesh(B(0.9, 0.25, 0.1), "#08313a", 0, 0.45, 0.56, vm);                      // tray
  const led = new THREE.Mesh(new THREE.SphereGeometry(0.12, 8, 6), new THREE.MeshBasicMaterial({ color: "#2ecc71" }));
  led.position.set(0.6, 2.95, 0.3); vm.add(led);

  const m = { id, site, vm, scr, led, top: new THREE.Vector3(s.x, 3, s.z + 1.2), customer: null };
  drawScreen(m, "Touch the screen\nto start.");
  machines[id] = m;
}

// ---------------------------------------------------------------- cloud
const cloud = new THREE.Group(); cloud.position.set(0, 15, -4); scene.add(cloud);
const cloudMat = new THREE.MeshStandardMaterial({ color: "#ffffff", flatShading: true });
[[0, 0, 0, 2.6], [-2.6, -0.4, 0.3, 1.9], [2.6, -0.3, 0, 2], [-1.2, 1.2, 0, 1.8], [1.3, 1.1, -0.3, 1.7], [0, -0.6, 1.2, 1.7]]
  .forEach(([x, y, z, r]) => { const p = new THREE.Mesh(new THREE.IcosahedronGeometry(r, 0), cloudMat); p.position.set(x, y, z); p.castShadow = true; cloud.add(p); });
const cloudBottom = new THREE.Vector3(0, 13, -4);

// ---------------------------------------------------------------- connection lines
const links = {};
for (const m of Object.values(machines)) {
  const mid = m.top.clone().lerp(cloudBottom, 0.5); mid.y += 3;
  const curve = new THREE.QuadraticBezierCurve3(m.top, mid, cloudBottom);
  const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 48, 0.08, 6), new THREE.MeshBasicMaterial({ color: "#27ae60", transparent: true, opacity: 0.9 }));
  scene.add(tube);
  links[m.id] = { curve, tube };
}

// ---------------------------------------------------------------- moving things
const tweens = [];
function tween(dur, fn) {
  return new Promise(resolve => tweens.push({ start: performance.now(), dur, fn, resolve }));
}
function packet(id, color = "#2ecc71", down = false) {   // a record travelling along the line
  const p = new THREE.Mesh(new THREE.SphereGeometry(0.32, 10, 8), new THREE.MeshBasicMaterial({ color }));
  scene.add(p);
  tween(1300, t => p.position.copy(links[id].curve.getPoint(down ? 1 - t : t))).then(() => scene.remove(p));
}

function person() {
  const g = new THREE.Group();
  const shirt = ["#3d7ab8", "#c0392b", "#8e44ad", "#16a085", "#d35400", "#2c3e50"][Math.floor(Math.random() * 6)];
  mesh(new THREE.CylinderGeometry(0.32, 0.38, 1.1, 6), shirt, 0, 1.05, 0, g);
  mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.55, 6), "#33475b", 0, 0.28, 0, g);
  mesh(new THREE.IcosahedronGeometry(0.3, 0), "#f0c9a0", 0, 1.9, 0, g);
  return g;
}
async function walk(g, from, to, ms) {
  g.lookAt(to.x, g.position.y, to.z);
  await tween(ms, t => { g.position.lerpVectors(from, to, t); g.position.y = Math.abs(Math.sin(t * 14)) * 0.12; });
}
async function arrive(id) {
  const m = machines[id], s = SITES[id];
  const g = person(); scene.add(g);
  const start = new THREE.Vector3(s.x + (Math.random() < 0.5 ? -6 : 6), 0, s.z + 7);
  const spot = new THREE.Vector3(s.x, 0, s.z + 2.6);
  g.position.copy(start);
  m.customer = g;
  await walk(g, start, spot, 1600);
  g.lookAt(s.x, 0, s.z);
}
async function leave(id) {
  const m = machines[id], g = m.customer; if (!g) return;
  const s = SITES[id];
  const end = new THREE.Vector3(s.x + (Math.random() < 0.5 ? -7 : 7), 0, s.z + 9);
  await walk(g, g.position.clone(), end, 1600);
  scene.remove(g); m.customer = null;
}
function dispense(id, color) {   // the customer receives the medicine box
  const g = machines[id].customer; if (!g) return;
  mesh(B(0.35, 0.22, 0.25), color, 0.45, 1.1, 0.2, g);
}

// ---------------------------------------------------------------- labels (HTML over the 3D view)
const labels = {};
function label(key, html) {
  if (!labels[key]) { const d = document.createElement("div"); d.className = "tag"; box.appendChild(d); labels[key] = d; }
  labels[key].innerHTML = html;
}
label("cloud", "<b>MENDO Cloud</b>");
for (const [id, s] of Object.entries(SITES)) label(id, `<b>${id}</b><br>${s.name}`);
function placeLabels() {
  const w = box.clientWidth, h = box.clientHeight;
  const put = (key, pos) => {
    const v = pos.clone().project(camera);
    Object.assign(labels[key].style, { left: (v.x + 1) / 2 * w + "px", top: (1 - v.y) / 2 * h + "px", display: v.z < 1 ? "" : "none" });
  };
  put("cloud", new THREE.Vector3(0, 19, -4));
  for (const [id, s] of Object.entries(SITES)) put(id, new THREE.Vector3(s.x, 4.2, s.z + 1.2));
}

// ---------------------------------------------------------------- status from the servers
function update(states, cloudDown) {
  cloudMat.color.set(cloudDown ? "#e2a3a3" : "#ffffff");
  label("cloud", `<b>MENDO Cloud</b>${cloudDown ? '<br><span class="bad">DOWN</span>' : ""}`);
  for (const [id, s] of Object.entries(SITES)) {
    const st = states[id], link = links[id];
    if (performance.now() < (link.flashUntil || 0)) continue;   // being highlighted by an info button
    let color = "#27ae60", text = "online";
    if (!st) { color = "#8a96a3"; text = "not running"; }
    else if (!st.online) { color = "#c0392b"; text = "internet off"; }
    else if (cloudDown) { color = "#8a96a3"; text = "cloud down"; }
    link.tube.material.color.set(color);
    link.tube.material.opacity = color === "#27ae60" ? 0.9 : 0.45;
    machines[id].led.material.color.set(st && st.online ? "#2ecc71" : "#e74c3c");
    const q = st && st.queued ? ` · <span class="bad">${st.queued} queued</span>` : "";
    label(id, `<b>${id}</b> · ${s.name}<br><span class="${color === "#27ae60" ? "ok" : "bad"}">${text}</span>${q}`);
  }
}

// ---------------------------------------------------------------- render loop
function resize() {
  const w = box.clientWidth, h = box.clientHeight;
  renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(box);
resize();
renderer.setAnimationLoop(now => {
  for (let i = tweens.length - 1; i >= 0; i--) {
    const tw = tweens[i], t = Math.min((now - tw.start) / tw.dur, 1);
    tw.fn(t);
    if (t >= 1) { tweens.splice(i, 1); tw.resolve(); }
  }
  cloud.position.y = 15 + Math.sin(now / 900) * 0.3;
  controls.update();
  renderer.render(scene, camera);
  placeLabels();
});

// ---------------------------------------------------------------- highlight (used by the info buttons)
function highlight(what) {
  const tubes = what === "lines" ? Object.values(links) : links[what] ? [links[what]] : [];
  const objs = what === "cloud" ? [cloud] : what === "machines" ? Object.values(machines).map(m => m.vm)
             : machines[what] ? [machines[what].vm] : [];
  tubes.forEach(l => l.flashUntil = performance.now() + 3000);
  tween(3000, t => {
    const on = Math.sin(t * Math.PI * 10) > 0;
    tubes.forEach(l => l.tube.material.color.set(on ? "#f1c40f" : "#27ae60"));
    objs.forEach(o => o.scale.setScalar(1 + 0.3 * Math.abs(Math.sin(t * Math.PI * 5))));
  }).then(() => objs.forEach(o => o.scale.setScalar(1)));
}

window.World = { arrive, leave, dispense, packet, update, highlight, setScreen: (id, text) => drawScreen(machines[id], text) };
