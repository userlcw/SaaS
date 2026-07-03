/**
 * 背景动画引擎（Canvas）
 * - 时间基准：epoch 存于 localStorage，t = (Date.now() - epoch) / 1000
 *   所有绘制均为 f(t)，刷新后 t 连续，画面自动"接着放"
 * - 模式：constellation / ribbons / mesh，按钮切换（0.6s crossfade）
 * - 性能：
 *   · DPR 上限 2，防止 4K 屏消耗过大
 *   · 页面 hidden 时暂停 RAF；visible 时按最新 t 无缝续帧
 *   · prefers-reduced-motion 时只画静态首帧
 * - 兼容：Canvas 2D，全部主流浏览器（含 IE11 之后所有版本）
 */
(function () {
  var EPOCH_KEY = "bg_anim_epoch_v1";
  var MODE_KEY = "bg_anim_mode_v1";

  function readEpoch() {
    var raw = localStorage.getItem(EPOCH_KEY);
    var n = raw ? parseInt(raw, 10) : NaN;
    if (!isFinite(n) || n <= 0 || n > Date.now()) {
      n = Date.now();
      try { localStorage.setItem(EPOCH_KEY, String(n)); } catch (_) {}
    }
    return n;
  }

  function readMode() {
    // 已下线主题切换，固定使用星云
    return "constellation";
  }
  function writeMode(m) { try { localStorage.setItem(MODE_KEY, m); } catch (_) {} }

  // ---------- 数学工具 ----------
  var PI2 = Math.PI * 2;
  // 简单的确定性伪随机（同一 idx 恒等），用于稳定的粒子/丝带布局
  function rnd(seed) {
    var x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
    return x - Math.floor(x);
  }

  // ================== 模式：星云网格（Constellation） ==================
  function renderConstellation(ctx, w, h, t, opts) {
    var accent = opts.accent;
    var count = Math.min(90, Math.round((w * h) / 22000)); // 密度随屏幕自适应
    var pts = new Array(count);
    for (var i = 0; i < count; i++) {
      var r1 = rnd(i + 1) * PI2;
      var r2 = rnd(i + 101);
      var r3 = rnd(i + 201);
      // 每个粒子有独立轨道半径 + 相位 + 速度
      var cx = (0.1 + r2 * 0.8) * w;
      var cy = (0.08 + r3 * 0.84) * h;
      var orbit = 30 + rnd(i + 301) * 60;
      var speed = 0.15 + rnd(i + 401) * 0.25;
      var phase = r1;
      pts[i] = {
        x: cx + Math.cos(t * speed + phase) * orbit,
        y: cy + Math.sin(t * speed * 1.1 + phase) * orbit,
        r: 0.6 + rnd(i + 501) * 1.4,
        a: 0.35 + rnd(i + 601) * 0.55
      };
    }
    // 连线：邻近点之间
    ctx.lineWidth = 1;
    var maxDist = Math.min(w, h) * 0.11;
    for (var a = 0; a < pts.length; a++) {
      for (var b = a + 1; b < pts.length; b++) {
        var dx = pts[a].x - pts[b].x, dy = pts[a].y - pts[b].y;
        var d2 = dx * dx + dy * dy;
        if (d2 > maxDist * maxDist) continue;
        var alpha = 1 - Math.sqrt(d2) / maxDist;
        ctx.strokeStyle = "rgba(" + accent + "," + (alpha * 0.28).toFixed(3) + ")";
        ctx.beginPath();
        ctx.moveTo(pts[a].x, pts[a].y);
        ctx.lineTo(pts[b].x, pts[b].y);
        ctx.stroke();
      }
    }
    // 粒子
    for (var k = 0; k < pts.length; k++) {
      var p = pts[k];
      ctx.fillStyle = "rgba(" + accent + "," + (p.a * 0.9).toFixed(3) + ")";
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, PI2);
      ctx.fill();
    }
  }

  // ================== 模式：流光丝带（Ribbons） ==================
  function renderRibbons(ctx, w, h, t, opts) {
    var accent = opts.accent, accent2 = opts.accent2;
    ctx.lineCap = "round";
    var strands = 5;
    for (var s = 0; s < strands; s++) {
      var phase = s * 0.7;
      var speed = 0.25 + s * 0.05;
      var yBase = h * (0.18 + s * 0.16);
      var amp = 40 + s * 8;
      var g = ctx.createLinearGradient(0, 0, w, 0);
      var mix = s % 2 === 0 ? accent : accent2;
      g.addColorStop(0.0, "rgba(" + mix + ",0)");
      g.addColorStop(0.5, "rgba(" + mix + ",0.55)");
      g.addColorStop(1.0, "rgba(" + mix + ",0)");
      ctx.strokeStyle = g;
      ctx.lineWidth = 1.4 + rnd(s + 11) * 1.6;
      ctx.beginPath();
      for (var x = 0; x <= w; x += 12) {
        var y = yBase
              + Math.sin(x * 0.006 + t * speed + phase) * amp
              + Math.sin(x * 0.02 + t * speed * 0.6 + phase) * (amp * 0.35);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }

  // ================== 模式：渐变液态（Mesh Blobs） ==================
  function renderMesh(ctx, w, h, t, opts) {
    var accent = opts.accent, accent2 = opts.accent2;
    var blobs = [
      { cx: w * 0.28, cy: h * 0.35, r: Math.min(w, h) * 0.42, speed: 0.06, phase: 0.0, color: accent },
      { cx: w * 0.72, cy: h * 0.65, r: Math.min(w, h) * 0.46, speed: 0.05, phase: 1.6, color: accent2 },
      { cx: w * 0.55, cy: h * 0.20, r: Math.min(w, h) * 0.36, speed: 0.07, phase: 3.1, color: accent }
    ];
    for (var i = 0; i < blobs.length; i++) {
      var b = blobs[i];
      var dx = Math.cos(t * b.speed + b.phase) * (w * 0.08);
      var dy = Math.sin(t * b.speed * 0.9 + b.phase) * (h * 0.08);
      var g = ctx.createRadialGradient(b.cx + dx, b.cy + dy, 0, b.cx + dx, b.cy + dy, b.r);
      g.addColorStop(0, "rgba(" + b.color + ",0.28)");
      g.addColorStop(1, "rgba(" + b.color + ",0)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(b.cx + dx, b.cy + dy, b.r, 0, PI2);
      ctx.fill();
    }
    // 顶层细粒噪点（低强度）
    ctx.globalAlpha = 0.06;
    for (var n = 0; n < 60; n++) {
      var px = rnd(n + 1) * w, py = rnd(n + 101) * h;
      ctx.fillStyle = "rgba(" + accent + ",0.5)";
      ctx.beginPath();
      ctx.arc(px, py, 0.6, 0, PI2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  var MODES = {
    constellation: renderConstellation,
    ribbons: renderRibbons,
    mesh: renderMesh
  };

  // ---------- 引擎 ----------
  function BgEngine(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.mode = readMode();
    this.prevMode = null;         // 用于淡入淡出
    this.transitionStart = 0;     // 秒
    this.transitionDur = 0.6;
    this.epoch = readEpoch();
    this.running = false;
    this.reducedMotion = window.matchMedia
      ? window.matchMedia("(prefers-color-scheme: dark) and (prefers-reduced-motion: reduce)").matches
      : false;
    // 读取主色（RGB 分量）
    var s = getComputedStyle(document.documentElement);
    this.accent = this._rgb(s.getPropertyValue("--accent")) || "94,184,240";
    this.accent2 = this._rgb(s.getPropertyValue("--accent-2")) || "63,208,212";

    this._resize = this._resize.bind(this);
    this._tick = this._tick.bind(this);
  }

  BgEngine.prototype._rgb = function (v) {
    // 支持 #RRGGBB / #RGB / rgb() 已有变量
    v = (v || "").trim();
    if (!v) return null;
    if (v.charAt(0) === "#") {
      if (v.length === 4) v = "#" + v[1] + v[1] + v[2] + v[2] + v[3] + v[3];
      var num = parseInt(v.slice(1), 16);
      return ((num >> 16) & 255) + "," + ((num >> 8) & 255) + "," + (num & 255);
    }
    var m = v.match(/rgba?\(([^)]+)\)/i);
    if (m) return m[1].split(",").slice(0, 3).map(function (x) { return x.trim(); }).join(",");
    return null;
  };

  BgEngine.prototype._resize = function () {
    var c = this.canvas;
    var w = c.clientWidth = window.innerWidth;
    var h = c.clientHeight = window.innerHeight;
    var dpr = this.dpr;
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };

  BgEngine.prototype._now = function () {
    return (Date.now() - this.epoch) / 1000;
  };

  BgEngine.prototype._render = function (t) {
    var ctx = this.ctx;
    var c = this.canvas;
    var w = c.clientWidth, h = c.clientHeight;
    ctx.clearRect(0, 0, w, h);

    var opts = { accent: this.accent, accent2: this.accent2 };
    var fn = MODES[this.mode] || MODES.constellation;

    // 过渡：绘制 prev + current，按 alpha 插值
    if (this.prevMode) {
      var elapsed = t - this.transitionStart;
      var p = Math.max(0, Math.min(1, elapsed / this.transitionDur));
      // ease-in-out
      p = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;

      ctx.globalAlpha = 1 - p;
      (MODES[this.prevMode] || fn)(ctx, w, h, t, opts);
      ctx.globalAlpha = p;
      fn(ctx, w, h, t, opts);
      ctx.globalAlpha = 1;

      if (p >= 1) this.prevMode = null;
    } else {
      fn(ctx, w, h, t, opts);
    }
  };

  BgEngine.prototype._tick = function () {
    if (!this.running) return;
    this._render(this._now());
    this._raf = requestAnimationFrame(this._tick);
  };

  BgEngine.prototype.start = function () {
    if (this.running) return;
    this.running = true;
    this._resize();
    // 首帧
    this._render(this._now());
    this.canvas.classList.add("is-ready");
    if (this.reducedMotion) return; // 只画一帧
    this._raf = requestAnimationFrame(this._tick);
  };

  BgEngine.prototype.stop = function () {
    this.running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
  };

  BgEngine.prototype.setMode = function (m) {
    if (!MODES[m] || m === this.mode) return;
    this.prevMode = this.mode;
    this.transitionStart = this._now();
    this.mode = m;
    writeMode(m);
  };

  // ---------- 启动 ----------
  document.addEventListener("DOMContentLoaded", function () {
    var canvas = document.getElementById("bgCanvas");
    if (!canvas) return;
    var eng = new BgEngine(canvas);
    eng.start();

    window.addEventListener("resize", function () { eng._resize(); }, { passive: true });

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) eng.stop();
      else eng.start();
    });

    // 模式切换按钮
    var btns = document.querySelectorAll(".bg-switch-btn");
    function refreshActive() {
      for (var i = 0; i < btns.length; i++) {
        btns[i].classList.toggle("is-active", btns[i].getAttribute("data-mode") === eng.mode);
        btns[i].setAttribute("aria-pressed", btns[i].getAttribute("data-mode") === eng.mode ? "true" : "false");
      }
    }
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", function () {
        eng.setMode(this.getAttribute("data-mode"));
        refreshActive();
      });
    }
    refreshActive();

    // 暴露 debug 钩子
    window.__bgEngine = eng;
  });
})();
