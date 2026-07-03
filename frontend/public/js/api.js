/**
 * 通用 API 封装：
 * - 使用相对路径 `/api/v1`，同源部署，无需硬编码地址
 * - 请求携带 cookie（refresh_token 使用 httpOnly cookie）
 * - access_token 存储在 sessionStorage（仅当前浏览器会话），刷新失败时再走 /refresh 续签
 * - 401 时自动尝试 /refresh 换取新 access_token 并重放请求（一次）
 */
(function (global) {
  const API_BASE = "/api/v1";
  const TOKEN_KEY = "docker_console_access_token";
  let _accessToken = null;
  let _refreshPromise = null;

  function setAccessToken(token) {
    _accessToken = token || null;
    try {
      if (token) sessionStorage.setItem(TOKEN_KEY, token);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch (_) {}
  }

  function getAccessToken() {
    if (_accessToken) return _accessToken;
    try {
      _accessToken = sessionStorage.getItem(TOKEN_KEY) || null;
    } catch (_) {
      _accessToken = null;
    }
    return _accessToken;
  }

  function clearAccessToken() {
    _accessToken = null;
    try { sessionStorage.removeItem(TOKEN_KEY); } catch (_) {}
  }

  function _buildHeaders(extra) {
    const headers = Object.assign({ "Content-Type": "application/json" }, extra || {});
    const token = getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  async function _fetch(path, options) {
    const opts = Object.assign(
      {
        method: "GET",
        credentials: "include", // 关键：让浏览器带上 refresh_token cookie
      },
      options || {}
    );
    opts.headers = _buildHeaders(opts.headers);
    return fetch(API_BASE + path, opts);
  }

  async function _parseBody(resp) {
    try { return await resp.json(); } catch (_) { return null; }
  }

  async function _tryRefresh() {
    if (_refreshPromise) return _refreshPromise;
    _refreshPromise = (async () => {
      try {
        const resp = await fetch(API_BASE + "/auth/refresh", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        });
        if (!resp.ok) return false;
        const body = await resp.json();
        const token = body && body.data && body.data.token && body.data.token.access_token;
        if (token) {
          setAccessToken(token);
          return true;
        }
        return false;
      } catch (_) {
        return false;
      } finally {
        _refreshPromise = null;
      }
    })();
    return _refreshPromise;
  }

  async function request(path, options, _retried) {
    let resp;
    try {
      resp = await _fetch(path, options);
    } catch (err) {
      throw { code: -1, message: "网络异常，请稍后重试" };
    }

    const body = await _parseBody(resp);
    if (resp.ok) return body;

    // access_token 过期或缺失：尝试用 refresh_token 静默续签一次
    if (resp.status === 401 && !_retried && path !== "/auth/refresh" && path !== "/auth/login") {
      const ok = await _tryRefresh();
      if (ok) return request(path, options, true);
    }

    const err = body || { code: resp.status, message: resp.statusText };
    throw err;
  }

  const Api = {
    getAccessToken,
    setAccessToken,
    clearAccessToken,
    register(email, password, code) {
      return request("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          confirm_password: password,
          code,
        }),
      });
    },
    sendEmailCode(email) {
      return request("/auth/send-code", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
    },
    login(username, password) {
      return request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      }).then((body) => {
        const token = body && body.data && body.data.token && body.data.token.access_token;
        if (token) setAccessToken(token);
        return body;
      });
    },
    me() {
      return request("/auth/me", { method: "GET" });
    },
    refresh() {
      return _tryRefresh();
    },
    logout() {
      return request("/auth/logout", { method: "POST" }).finally(() => clearAccessToken());
    },
    listContainers(params) {
      const qs = new URLSearchParams();
      Object.keys(params || {}).forEach((key) => {
        const value = params[key];
        if (value !== undefined && value !== null && value !== "") qs.set(key, value);
      });
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return request(`/containers${suffix}`, { method: "GET" });
    },
    listImages(server) {
      const qs = new URLSearchParams();
      if (server) qs.set("server", server);
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return request(`/images${suffix}`, { method: "GET" });
    },
    getDashboardMetrics() {
      return request("/dashboard/metrics", { method: "GET" });
    },
    listUsers(params) {
      const qs = new URLSearchParams();
      Object.keys(params || {}).forEach((key) => {
        const value = params[key];
        if (value !== undefined && value !== null && value !== "") qs.set(key, value);
      });
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return request(`/users${suffix}`, { method: "GET" });
    },
    listAuditLogs(params) {
      const qs = new URLSearchParams();
      Object.keys(params || {}).forEach((key) => {
        const value = params[key];
        if (value !== undefined && value !== null && value !== "") qs.set(key, value);
      });
      const suffix = qs.toString() ? `?${qs.toString()}` : "";
      return request(`/audit-logs${suffix}`, { method: "GET" });
    },
    createContainer(payload) {
      return request("/containers", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    startContainer(id) {
      return request(`/containers/${encodeURIComponent(id)}/actions/start`, { method: "POST" });
    },
    stopContainer(id) {
      return request(`/containers/${encodeURIComponent(id)}/actions/stop`, { method: "POST" });
    },
    restartContainer(id) {
      return request(`/containers/${encodeURIComponent(id)}/actions/restart`, { method: "POST" });
    },
    getContainerLogs(id, tail) {
      const qs = new URLSearchParams();
      qs.set("tail", String(tail || 200));
      return request(`/containers/${encodeURIComponent(id)}/logs?${qs.toString()}`, { method: "GET" });
    },
    deleteContainer(id, force) {
      const qs = force ? "?force=true" : "";
      return request(`/containers/${encodeURIComponent(id)}${qs}`, { method: "DELETE" });
    },
  };

  global.Api = Api;
})(window);
