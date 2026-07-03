/**
 * 注册页交互逻辑：
 * - 邮箱格式校验
 * - 邮箱验证码：获取按钮 + 倒计时
 * - 密码强度检测（长度 / 大小写 / 数字 / 符号）+ 强度条动态展示
 * - 确认密码一致性校验
 * - loading + 防重复提交
 * - 提交成功后跳转登录页并回填邮箱
 */
(function () {
  const $ = (id) => document.getElementById(id);

  const form = $("registerForm");
  const emailInput = $("email");
  const codeInput = $("code");
  const sendCodeBtn = $("sendCodeBtn");
  const passwordInput = $("password");
  const confirmInput = $("confirmPassword");
  const submitBtn = $("submitBtn");
  const tips = $("tips");
  const card = document.querySelector(".login-card");

  const emailError = $("emailError");
  const codeError = $("codeError");
  const passwordError = $("passwordError");
  const confirmError = $("confirmError");

  const capsHint = $("capsHint");
  const togglePwd = $("togglePwd");
  const eyeOpen = $("eyeOpen");
  const eyeClose = $("eyeClose");
  const toggleConfirm = $("toggleConfirm");
  const eyeOpen2 = $("eyeOpen2");
  const eyeClose2 = $("eyeClose2");

  const strengthWrap = $("pwdStrength");
  const strengthLabel = $("pwdStrengthLabel");
  const strengthHint = $("pwdStrengthHint");

  let inflight = false;
  $("year").textContent = new Date().getFullYear();

  // 简易邮箱校验：允许 label+tag 格式，最大 128 字符
  const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

  // ---------- 提示 & 错误 ----------
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

  // ---------- 密码强度检测 ----------
  function evalStrength(pwd) {
    if (!pwd) return { level: 0, label: "—", hint: "建议 8+ 位，含大小写与数字" };
    let score = 0;
    if (pwd.length >= 8) score++;
    if (pwd.length >= 12) score++;
    if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score++;
    if (/\d/.test(pwd)) score++;
    if (/[^A-Za-z0-9]/.test(pwd)) score++;
    const level = Math.max(1, Math.min(4, Math.round(score * 0.8)));
    const map = {
      1: { label: "弱", hint: "太短或字符类型单一" },
      2: { label: "一般", hint: "增加大小写或数字" },
      3: { label: "较强", hint: "再添加特殊符号更佳" },
      4: { label: "很强", hint: "已达到较高强度" },
    };
    return { level, ...map[level] };
  }

  function refreshStrength() {
    const v = passwordInput.value || "";
    if (!v) {
      strengthWrap.setAttribute("hidden", "");
      strengthWrap.setAttribute("data-level", "0");
      return;
    }
    strengthWrap.removeAttribute("hidden");
    const s = evalStrength(v);
    strengthWrap.setAttribute("data-level", String(s.level));
    strengthLabel.textContent = s.label;
    strengthHint.textContent = s.hint;
  }

  // ---------- 校验 ----------
  function validateEmail(showError, opts) {
    opts = opts || {};
    const v = (emailInput.value || "").trim();
    if (!v) {
      if (opts.allowEmpty) {
        setFieldError(emailInput, emailError, "");
        return false;
      }
      if (showError) setFieldError(emailInput, emailError, "请输入邮箱");
      return false;
    }
    if (v.length > 128) {
      if (showError) setFieldError(emailInput, emailError, "邮箱长度不能超过 128");
      return false;
    }
    if (!EMAIL_RE.test(v)) {
      if (showError) setFieldError(emailInput, emailError, "邮箱格式不正确");
      return false;
    }
    setFieldError(emailInput, emailError, "");
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
      if (showError) setFieldError(passwordInput, passwordError, "请设置密码");
      return false;
    }
    if (v.length < 8) {
      if (showError) setFieldError(passwordInput, passwordError, "密码至少 8 位");
      return false;
    }
    if (v.length > 128) {
      if (showError) setFieldError(passwordInput, passwordError, "密码长度不能超过 128");
      return false;
    }
    const hasLower = /[a-z]/.test(v);
    const hasUpper = /[A-Z]/.test(v);
    const hasDigit = /\d/.test(v);
    if (!(hasLower && hasUpper && hasDigit)) {
      if (showError)
        setFieldError(
          passwordInput,
          passwordError,
          "密码需同时包含大写字母、小写字母和数字"
        );
      return false;
    }
    setFieldError(passwordInput, passwordError, "");
    return true;
  }

  function validateConfirm(showError, opts) {
    opts = opts || {};
    const v = confirmInput.value || "";
    if (!v) {
      if (opts.allowEmpty) {
        setFieldError(confirmInput, confirmError, "");
        return false;
      }
      if (showError) setFieldError(confirmInput, confirmError, "请再次输入密码");
      return false;
    }
    if (v !== passwordInput.value) {
      if (showError) setFieldError(confirmInput, confirmError, "两次输入的密码不一致");
      return false;
    }
    setFieldError(confirmInput, confirmError, "");
    return true;
  }

  function validateCode(showError, opts) {
    opts = opts || {};
    const v = (codeInput.value || "").trim();
    if (!v) {
      if (opts.allowEmpty) {
        setFieldError(codeInput, codeError, "");
        return false;
      }
      if (showError) setFieldError(codeInput, codeError, "请输入邮箱验证码");
      return false;
    }
    if (!/^\d{4,10}$/.test(v)) {
      if (showError) setFieldError(codeInput, codeError, "验证码为 4-10 位数字");
      return false;
    }
    setFieldError(codeInput, codeError, "");
    return true;
  }

  // ---------- 事件绑定 ----------
  emailInput.addEventListener("blur", () => validateEmail(true, { allowEmpty: true }));
  emailInput.addEventListener("input", () => {
    if (emailInput.getAttribute("aria-invalid") === "true") {
      validateEmail(true, { allowEmpty: true });
    }
  });

  passwordInput.addEventListener("blur", () => validatePassword(true, { allowEmpty: true }));
  passwordInput.addEventListener("input", () => {
    refreshEye(togglePwd, passwordInput, eyeOpen, eyeClose);
    refreshStrength();
    if (passwordInput.getAttribute("aria-invalid") === "true") {
      validatePassword(true, { allowEmpty: true });
    }
    if (confirmInput.value) validateConfirm(true, { allowEmpty: true });
  });

  confirmInput.addEventListener("blur", () => validateConfirm(true, { allowEmpty: true }));
  confirmInput.addEventListener("input", () => {
    refreshEye(toggleConfirm, confirmInput, eyeOpen2, eyeClose2);
    if (confirmInput.getAttribute("aria-invalid") === "true") {
      validateConfirm(true, { allowEmpty: true });
    }
  });

  // 验证码输入：只保留数字
  codeInput.addEventListener("input", () => {
    const cleaned = (codeInput.value || "").replace(/\D+/g, "");
    if (cleaned !== codeInput.value) codeInput.value = cleaned;
    if (codeInput.getAttribute("aria-invalid") === "true") {
      validateCode(true, { allowEmpty: true });
    }
  });
  codeInput.addEventListener("blur", () => validateCode(true, { allowEmpty: true }));

  // ---------- 发送验证码 ----------
  let sendCooldown = 0;
  let sendTimer = null;

  function startCooldown(seconds) {
    sendCooldown = Math.max(1, seconds | 0);
    sendCodeBtn.disabled = true;
    updateSendBtnText();
    if (sendTimer) clearInterval(sendTimer);
    sendTimer = setInterval(() => {
      sendCooldown -= 1;
      if (sendCooldown <= 0) {
        clearInterval(sendTimer);
        sendTimer = null;
        sendCodeBtn.disabled = false;
        sendCodeBtn.textContent = "重新获取";
      } else {
        updateSendBtnText();
      }
    }, 1000);
  }

  function updateSendBtnText() {
    sendCodeBtn.textContent = `${sendCooldown}s 后重试`;
  }

  sendCodeBtn.addEventListener("click", async () => {
    if (sendCodeBtn.disabled) return;
    if (!validateEmail(true)) {
      emailInput.focus();
      return;
    }
    const email = emailInput.value.trim();
    sendCodeBtn.disabled = true;
    const original = sendCodeBtn.textContent;
    sendCodeBtn.textContent = "发送中…";
    setTip("");
    try {
      const resp = await Api.sendEmailCode(email);
      const data = (resp && resp.data) || {};
      const wait = Math.max(30, data.resend_after_seconds || 60);
      setTip(resp.message || `验证码已发送至 ${email}`, "success");
      codeInput.focus();
      startCooldown(wait);
    } catch (err) {
      const detail = (err && err.detail) || err || {};
      const msg = detail.message || err.message || "发送失败，请稍后再试";
      setTip(msg);
      shakeCard();
      if (detail.code === 42903 || (typeof msg === "string" && msg.indexOf("频繁") >= 0)) {
        startCooldown(30);
      } else {
        sendCodeBtn.disabled = false;
        sendCodeBtn.textContent = original;
      }
    }
  });

  // Caps Lock
  function updateCaps(e) {
    if (!e || typeof e.getModifierState !== "function") return;
    const on = e.getModifierState("CapsLock");
    if (on) capsHint.removeAttribute("hidden");
    else capsHint.setAttribute("hidden", "");
  }
  passwordInput.addEventListener("keydown", updateCaps);
  passwordInput.addEventListener("keyup", updateCaps);
  passwordInput.addEventListener("blur", () => capsHint.setAttribute("hidden", ""));

  // 眼睛切换
  function refreshEye(btn, input, iconOpen, iconClose) {
    if (input.value.length > 0) {
      btn.classList.add("visible");
    } else {
      btn.classList.remove("visible");
      input.type = "password";
      iconOpen.style.display = "";
      iconClose.style.display = "none";
      btn.setAttribute("aria-pressed", "false");
      btn.setAttribute("aria-label", "显示密码");
    }
  }
  function bindEye(btn, input, iconOpen, iconClose) {
    btn.addEventListener("click", () => {
      const showing = input.type === "text";
      input.type = showing ? "password" : "text";
      iconOpen.style.display = showing ? "" : "none";
      iconClose.style.display = showing ? "none" : "";
      btn.setAttribute("aria-pressed", showing ? "false" : "true");
      btn.setAttribute("aria-label", showing ? "显示密码" : "隐藏密码");
    });
  }
  bindEye(togglePwd, passwordInput, eyeOpen, eyeClose);
  bindEye(toggleConfirm, confirmInput, eyeOpen2, eyeClose2);

  // Loading
  function toggleLoading(loading) {
    submitBtn.disabled = loading;
    submitBtn.classList.toggle("is-loading", loading);
    submitBtn.setAttribute("aria-busy", loading ? "true" : "false");
    submitBtn.querySelector(".btn-label").textContent = loading ? "注册中…" : "注 册";
  }

  function shakeCard() {
    if (!card) return;
    card.classList.remove("is-shake");
    void card.offsetWidth;
    card.classList.add("is-shake");
  }

  // ---------- 提交 ----------
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (inflight) return;

    const okE = validateEmail(true);
    const okV = validateCode(true);
    const okP = validatePassword(true);
    const okC = validateConfirm(true);

    if (!okE) return emailInput.focus();
    if (!okV) return codeInput.focus();
    if (!okP) return passwordInput.focus();
    if (!okC) return confirmInput.focus();

    inflight = true;
    toggleLoading(true);
    setTip("");
    try {
      const email = emailInput.value.trim();
      const password = passwordInput.value;
      const code = codeInput.value.trim();
      const resp = await Api.register(email, password, code);
      setTip(resp.message || "注册成功，即将跳转登录…", "success");
      setTimeout(() => {
        const url = "/?email=" + encodeURIComponent(email);
        window.location.href = url;
      }, 900);
    } catch (err) {
      const detail = (err && err.detail) || err || {};
      const msg = detail.message || err.message || "注册失败，请稍后再试";
      setTip(msg);
      shakeCard();
      if (msg.indexOf("验证码") >= 0) {
        setFieldError(codeInput, codeError, msg);
        codeInput.focus();
      } else if (msg.indexOf("邮箱") >= 0) {
        setFieldError(emailInput, emailError, msg);
        emailInput.focus();
      } else if (msg.indexOf("密码") >= 0) {
        setFieldError(passwordInput, passwordError, msg);
        passwordInput.focus();
      }
    } finally {
      toggleLoading(false);
      inflight = false;
    }
  });

  // ---------- 初始化 ----------
  emailInput.focus();
})();
