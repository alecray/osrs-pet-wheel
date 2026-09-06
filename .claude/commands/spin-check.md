---
description: Drive one full wheel spin of pet-wheel.html under Node with stubbed DOM/audio; fails if the spin loop throws or never finalizes
allowed-tools: Bash(node spin_harness.js*)
---

Run the spin harness and report the result:

```
node spin_harness.js
```

It loads the page's inline script with a fake DOM, Web Audio and requestAnimationFrame, forces
eight hunted pets, calls `spin()`, and steps frames until the animation ends. It exits 1 and prints
`FAIL ...` lines when the page script throws on load, a frame throws, `onSpinComplete` is never
called, or the pointer flapper does not settle.

Run it after any edit to `spin()`, `drawWheel()`, the flapper physics, or the sound code. If it
fails, the first `FAIL` line names the thrown error and the frame time. Fix the cause in
`pet-wheel.html`, re-run until it prints `OK`, and include the `OK` line in your report.
