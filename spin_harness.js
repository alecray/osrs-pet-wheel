#!/usr/bin/env node
/* spin_harness.js: drive one full wheel spin of pet-wheel.html under Node
 * with stubbed DOM / Web Audio, so a broken spin loop fails here instead of
 * in the browser. Exits 1 if the page scripts throw, if the spin never calls
 * onSpinComplete, or if the pointer flapper does not settle.
 *
 *   node spin_harness.js            # uses ./pet-wheel.html
 *   node spin_harness.js other.html
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const htmlPath = process.argv[2] || path.join(__dirname, "pet-wheel.html");
const html = fs.readFileSync(htmlPath, "utf8");
const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)];
const petData = scripts.find(m => /id="pet-data"/.test(m[1]));
const mainScript = scripts.find(m => !/type=/.test(m[1]));
if (!petData || !mainScript) { console.error("could not find pet-data or main script"); process.exit(1); }

let failures = 0;
function fail(msg) { failures++; console.error("FAIL " + msg); }

/* ---- minimal DOM / browser stubs ---------------------------------- */
let nowMs = 0;
const rafQueue = [];
const noop = () => {};
function makeEl(id) {
  return {
    id, style: {}, children: [], textContent: "", innerHTML: "", value: "", checked: false, disabled: false,
    classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
    addEventListener: noop, removeEventListener: noop,
    appendChild(c) { this.children.push(c); return c; }, append(...c) { this.children.push(...c); },
    removeChild: noop, insertBefore: noop, remove: noop, setAttribute: noop, getAttribute: () => null,
    querySelector: sel => makeEl(sel), querySelectorAll: () => [], focus: noop,
    getContext() {
      return new Proxy({}, { get: (_, k) =>
        k === "measureText" ? () => ({ width: 10 })
        : (k === "createRadialGradient" || k === "createLinearGradient") ? () => ({ addColorStop: noop })
        : noop });
    },
    width: 380, height: 380, offsetWidth: 380,
  };
}
const els = {};
els["pet-data"] = makeEl("pet-data");
els["pet-data"].textContent = petData[2];
const g = {
  document: {
    getElementById: id => (els[id] = els[id] || makeEl(id)),
    querySelector: sel => (els[sel] = els[sel] || makeEl(sel)),
    querySelectorAll: () => [],
    createElement: tag => makeEl(tag),
    createTextNode: t => ({ textContent: t }),
    addEventListener: noop,
    body: makeEl("body"),
  },
  localStorage: { _d: {}, getItem(k) { return k in this._d ? this._d[k] : null; }, setItem(k, v) { this._d[k] = String(v); }, removeItem(k) { delete this._d[k]; } },
  performance: { now: () => nowMs },
  requestAnimationFrame: fn => { rafQueue.push(fn); return rafQueue.length; },
  alert: m => fail("alert(): " + m),
  fetch: () => new Promise(noop),
  Image: function () { return makeEl("img"); },
  console, Math, JSON, Date, Set, Map, Promise, Number, String, Array, Object, parseInt, parseFloat, isNaN, isFinite, Float32Array, setTimeout, clearTimeout, encodeURIComponent, decodeURIComponent, escape: s => s,
};
class Param { setValueAtTime() {} linearRampToValueAtTime() {} exponentialRampToValueAtTime() {} }
class ANode { constructor() { this.gain = new Param(); this.frequency = new Param(); this.Q = new Param(); } connect(n) { return n; } start() {} stop() {} }
g.AudioContext = class {
  constructor() { this.currentTime = 0; this.sampleRate = 44100; this.state = "running"; this.destination = new ANode(); }
  resume() {} createGain() { return new ANode(); } createOscillator() { return new ANode(); } createBiquadFilter() { return new ANode(); }
  createBufferSource() { return new ANode(); } createBuffer(c, n) { return { getChannelData: () => new Float32Array(n) }; }
};
g.window = g;
g.globalThis = g;
const ctx = vm.createContext(g);

/* ---- load page script --------------------------------------------- */
try { vm.runInContext(mainScript[2], ctx, { filename: "pet-wheel.html<script>" }); }
catch (e) { fail("page script threw on load: " + e.message); }

/* ---- drive one spin ----------------------------------------------- */
vm.runInContext(`
  recomputePets();
  huntingSet = new Set(pets.filter(p => !p.owned).slice(0, 8).map(p => p.name));
  __completed = null;
  const __orig = onSpinComplete;
  onSpinComplete = function (pet) { __completed = pet.name; __orig(pet); };
  spin();
`, ctx);

let frames = 0;
while (rafQueue.length && frames < 2000) {
  const batch = rafQueue.splice(0);
  nowMs += 16;
  for (const fn of batch) {
    try { fn(nowMs); }
    catch (e) { fail("frame threw at " + nowMs + " ms: " + (e.stack || e.message).split("\n").slice(0, 2).join(" | ")); rafQueue.length = 0; break; }
  }
  frames++;
}

const completed = vm.runInContext("__completed", ctx);
const spinning = vm.runInContext("isSpinning", ctx);
const flap = vm.runInContext("typeof flapAngle === 'number' ? flapAngle : 0", ctx);
if (!completed) fail("onSpinComplete was never called");
if (spinning) fail("isSpinning still true after " + frames + " frames");
if (Math.abs(flap) > 0.01) fail("flapper did not settle (angle " + flap.toFixed(3) + ")");
if (frames >= 2000) fail("animation never ended");

console.log((failures ? "FAILED" : "OK") + ": " + frames + " frames, winner=" + completed + ", flapper=" + flap.toFixed(4));
process.exit(failures ? 1 : 0);
