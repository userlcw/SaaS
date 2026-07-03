/**
 * 登录页交互逻辑（P0 增强版）：
 * - 实时输入校验（blur / 提交前）
 * - Caps Lock 提示
 * - loading + 防重复提交
 * - 失败抖动 + 自动聚焦
 * - 记住我：仅保存账号（明文密码不落地）
 * - 首次访问：优先用 refresh_token cookie 静默续登
 */
(function () {
  const $ = (id) => document.getElementById(id);

  const form = $("loginForm");
  const usernameInput = $("username");
  const passwordInput = $("password");
  const rememberInput = $("remember");
  const submitBtn = $("submitBtn");
  const tips = $("tips");
  const togglePwd = $("togglePwd");
  const eyeOpen = $("eyeOpen");
  const eyeClose = $("eyeClose");
  const capsHint = $("capsHint");
  const card = document.querySelector(".login-card");

  const usernameError = $("usernameError");
  const passwordError = $("passwordError");

  const REMEMBER_KEY = "remember_username_v2";
  let inflight = false;

  $("year").textContent = new Date().getFullYear();

  // ---------- 提示与错误 ----------
  function setTip(msg, type) {
    tips.textContent = msg || "";
    tips.classList.toggle("success", type === "success");
  }

  function setFieldError(input, errorEl, msg) {
    if (!input || !errorEl) return;
    if (msg) {
      input.setAttribute("aria-invalid", "true");
      errorEl.textContent = msg;
    } else {
      input.setAttribute("aria-invalid", "false");
      errorEl.textContent = "";
    }
  }

  function clearAllErrors() {
    setFieldError(usernameInput, usernameError, "");
    setFieldError(passwordInput, passwordError, "");
    setTip("");
  }

  // ---------- 校验 ----------
  // 说明：
  // - blur 时：字段为空则视为“未开始输入”，不显示红色错误（保持无扰体验）
  // - blur 时：字段有内容但不合规，才显示错误
  // - 提交时：强制全量校验（含空值），失败态自动聚焦
  function validateUsername(showError, opts) {
    opts = opts || {};
    const v = (usernameInput.value || "").trim();
    if (!v) {
      if (opts.allowEmpty) {
        // 未输入内容，不打错误标记
        setFieldError(usernameInput, usernameError, "");
        return false;
      }
      if (showError) setFieldError(usernameInput, usernameError, "请输入账号");
      return false;
    }
    if (v.length < 3) {
      if (showError) setFieldError(usernameInput, usernameError, "账号至少 3 个字符");
      return false;
    }
    if (v.length > 64) {
      if (showError) setFieldError(usernameInput, usernameError, "账号长度不能超过 64");
      return false;
    }
    setFieldError(usernameInput, usernameError, "");
    return true;
  }

  function validatePassword(showError, opts) {
    opts = opts || {};
    const v = passwordInput.value || "";
    if (!v) {
      if (opts.allowEmpty) {
        setFieldError(passwordInput, passwordError, "");
        return false;
      }
      if (showError) setFieldError(passwordInput, passwordError, "请输入密码");
      return false;
    }
    if (v.length < 6) {
      if (showError) setFieldError(passwordInput, passwordError, "密码至少 6 位");
      return false;
    }
    setFieldError(passwordInput, passwordError, "");
    return true;
  }

  // blur：字段为空视为“未触碰完成”，跳过错误提示
  usernameInput.addEventListener("blur", () => validateUsername(true, { allowEmpty: true }));
  passwordInput.addEventListener("blur", () => validatePassword(true, { allowEmpty: true }));

  // input：只在已经处于错误态时同步校验，避免主动输入过程中反复变红
  usernameInput.addEventListener("input", () => {
    if (usernameInput.getAttribute("aria-invalid") === "true") {
      validateUsername(true, { allowEmpty: true });
    }
  });
  passwordInput.addEventListener("input", () => {
    refreshEyeVisibility();
    if (passwordInput.getAttribute("aria-invalid") === "true") {
      validatePassword(true, { allowEmpty: true });
    }
  });

  // ---------- Caps Lock 提示 ----------
  function updateCaps(e) {
    if (!e || typeof e.getModifierState !== "function") return;
    const on = e.getModifierState("CapsLock");
    if (on) capsHint.removeAttribute("hidden");
    else capsHint.setAttribute("hidden", "");
  }
  passwordInput.addEventListener("keydown", updateCaps);
  passwordInput.addEventListener("keyup", updateCaps);
  passwordInput.addEventListener("blur", () => capsHint.setAttribute("hidden", ""));

  // ---------- 眼睛切换 ----------
  function refreshEyeVisibility() {
    if (passwordInput.value.length > 0) {
      togglePwd.classList.add("visible");
    } else {
      togglePwd.classList.remove("visible");
      passwordInput.type = "password";
      eyeOpen.style.display = "";
      eyeClose.style.display = "none";
      togglePwd.setAttribute("aria-pressed", "false");
      togglePwd.setAttribute("aria-label", "显示密码");
    }
  }
  togglePwd.addEventListener("click", () => {
    const showing = passwordInput.type === "text";
    passwordInput.type = showing ? "password" : "text";
    eyeOpen.style.display  = showing ? "" : "none";
    eyeClose.style.display = showing ? "none" : "";
    togglePwd.setAttribute("aria-pressed", showing ? "false" : "true");
    togglePwd.setAttribute("aria-label", showing ? "显示密码" : "隐藏密码");
  });

  // ---------- Loading & 抖动 ----------
  function toggleLoading(loading) {
    submitBtn.disabled = loading;
    submitBtn.classList.toggle("is-loading", loading);
    submitBtn.setAttribute("aria-busy", loading ? "true" : "false");
    submitBtn.querySelector(".btn-label").textContent = loading ? "登录中…" : "登 录";
  }

  function shakeCard() {
    if (!card) return;
    card.classList.remove("is-shake");
    // 触发重排后重新添加类
    void card.offsetWidth;
    card.classList.add("is-shake");
  }

  // ---------- 记住我：仅账号 ----------
  function saveRememberedUsername(u) {
    if (!u) { localStorage.removeItem(REMEMBER_KEY); return; }
    localStorage.setItem(REMEMBER_KEY, u);
  }
  function readRememberedUsername() {
    return localStorage.getItem(REMEMBER_KEY) || "";
  }
  function clearRemembered() {
    localStorage.removeItem(REMEMBER_KEY);
  }

  // ---------- 提交 ----------
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (inflight) return;

    const okU = validateUsername(true);
    const okP = validatePassword(true);
    if (!okU) { usernameInput.focus(); return; }
    if (!okP) { passwordInput.focus(); return; }

    inflight = true;
    toggleLoading(true);
    setTip("");
    try {
      const username = usernameInput.value.trim();
      const password = passwordInput.value;
      const resp = await Api.login(username, password);

      // 记住账号
      if (rememberInput.checked) saveRememberedUsername(username);
      else clearRemembered();

      setTip(resp.message || "登录成功，正在进入…", "success");
      // 登录成功后直接跳转到主页（容器管理）
      window.location.replace("/console");
      return;
    } catch (err) {
      const detail = (err && err.detail) || err || {};
      const msg = detail.message || err.message || "登录失败，请稍后再试";
      setTip(msg);
      shakeCard();
      // 焦点回到密码框
      passwordInput.focus();
      passwordInput.select && passwordInput.select();
    } finally {
      toggleLoading(false);
      inflight = false;
    }
  });

  // ---------- 初始化 ----------
  (async function bootstrap() {
    // 优先使用 URL 中的 email 参数（注册成功跳转过来的场景）
    let prefill = "";
    try {
      const params = new URLSearchParams(window.location.search);
      prefill = (params.get("email") || "").trim();
    } catch (_) {}

    // 回填已记住的账号
    const rememberedU = readRememberedUsername();
    if (prefill) {
      usernameInput.value = prefill;
      passwordInput.focus();
      setTip("账号已注册，请输入密码登录", "success");
    } else if (rememberedU) {
      usernameInput.value = rememberedU;
      rememberInput.checked = true;
      passwordInput.focus();
    } else {
      usernameInput.focus();
    }

    // 尝试用 refresh_token cookie 静默恢复登录
    const ok = await Api.refresh();
    if (!ok) return;
    try {
      await Api.me();
      // 已恢复会话：直接进入主页，不在登录页停留
      window.location.replace("/console");
    } catch (_) {
      Api.clearAccessToken();
    }
  })();
})();
