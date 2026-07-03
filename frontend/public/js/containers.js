/**
 * 容器管理页：
 * - HTTP 列表 + 筛选 + 分页
 * - 30 秒自动刷新
 * - 基础创建容器与启停重启删除操作
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const state = {
    page: 1,
    pageSize: 20,
    total: 0,
    items: [],
    images: [],
    timer: null,
    currentView: "containers",
    viewLoaded: {
      containers: false,
      dashboard: false,
      users: false,
    },
    dashboardTimer: null,
    dashboardHistory: [],
    dashboardCache: null,
    dashboardCacheAt: 0,
  };
  const SIDEBAR_KEY = "docker_console_sidebar_collapsed";

  const els = {
    summaryText: $("summaryText"),
    keyword: $("keyword"),
    queryField: $("queryField"),
    statusFilter: $("statusFilter"),
    imageFilter: $("imageFilter"),
    imageSummaryText: $("imageSummaryText"),
    imageListBody: $("imageListBody"),
    pageSize: $("pageSize"),
    tableBody: $("containerTableBody"),
    runningCount: $("runningCount"),
    exitedCount: $("exitedCount"),
    errorCount: $("errorCount"),
    totalCount: $("totalCount"),
    pageInfo: $("pageInfo"),
    prevPage: $("prevPage"),
    nextPage: $("nextPage"),
    refreshBtn: $("refreshBtn"),
    autoRefresh: $("autoRefresh"),
    createBtn: $("createBtn"),
    modal: $("createContainerModal"),
    closeCreateModal: $("closeCreateModal"),
    cancelCreate: $("cancelCreate"),
    createForm: $("createForm"),
    createImage: $("createImage"),
    createName: $("createName"),
    hostPort: $("hostPort"),
    containerPort: $("containerPort"),
    restartPolicy: $("restartPolicy"),
    startAfterCreate: $("startAfterCreate"),
    createTip: $("createTip"),
    logModal: $("containerLogModal"),
    closeLogModal: $("closeLogModal"),
    closeLogBtn: $("closeLogBtn"),
    refreshLogBtn: $("refreshLogBtn"),
    logSubtitle: $("logSubtitle"),
    logContent: $("containerLogContent"),
    appLayout: document.querySelector(".app-layout"),
    sidebar: $("appSidebar"),
    sidebarToggle: $("sidebarToggle"),
    settingsBtn: $("settingsBtn"),
    settingsMenu: $("settingsMenu"),
    logoutBtn: $("logoutBtn"),
    navItems: Array.from(document.querySelectorAll(".sidebar-nav-item")),
    viewPanels: Array.from(document.querySelectorAll("[data-view-panel]")),
    dashboardInterval: $("dashboardInterval"),
    refreshDashboardBtn: $("refreshDashboardBtn"),
    dashboardSummary: $("dashboardSummary"),
    cpuPercent: $("cpuPercent"),
    cpuBar: $("cpuBar"),
    cpuMeta: $("cpuMeta"),
    memoryPercent: $("memoryPercent"),
    memoryBar: $("memoryBar"),
    memoryMeta: $("memoryMeta"),
    diskPercent: $("diskPercent"),
    diskBar: $("diskBar"),
    diskMeta: $("diskMeta"),
    networkRate: $("networkRate"),
    networkBar: $("networkBar"),
    networkMeta: $("networkMeta"),
    metricsChart: $("metricsChart"),
    refreshUsersBtn: $("refreshUsersBtn"),
    refreshAuditBtn: $("refreshAuditBtn"),
    usersSummary: $("usersSummary"),
    userKeyword: $("userKeyword"),
    userStatus: $("userStatus"),
    userSort: $("userSort"),
    userTableBody: $("userTableBody"),
    auditUser: $("auditUser"),
    auditAction: $("auditAction"),
    auditStartTime: $("auditStartTime"),
    auditEndTime: $("auditEndTime"),
    auditTableBody: $("auditTableBody"),
    toast: $("toast"),
  };

  function toast(message, type) {
    els.toast.textContent = message;
    els.toast.className = `toast ${type || ""}`;
    els.toast.hidden = false;
    clearTimeout(els.toast._timer);
    els.toast._timer = setTimeout(() => { els.toast.hidden = true; }, 2600);
  }

  function statusText(status, health) {
    if (health === "unhealthy") return "健康异常";
    const map = {
      running: "运行中",
      exited: "已停止",
      paused: "暂停",
      restarting: "重启中",
      dead: "异常",
      created: "已创建",
      removing: "删除中",
    };
    return map[status] || status || "未知";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatBytes(value) {
    const bytes = Number(value || 0);
    if (!bytes || bytes < 0) return "-";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = bytes;
    let index = 0;
    while (size >= 1024 && index < units.length - 1) {
      size /= 1024;
      index += 1;
    }
    const precision = size >= 10 || index === 0 ? 0 : 1;
    return `${size.toFixed(precision)} ${units[index]}`;
  }

  function formatRate(value) {
    const rate = Number(value || 0);
    if (!rate) return "0 B/s";
    return `${formatBytes(rate)}/s`;
  }

  function clampPercent(value) {
    const number = Number(value || 0);
    return Math.max(0, Math.min(100, number));
  }

  function setBar(el, value) {
    if (el) el.style.width = `${clampPercent(value)}%`;
  }

  function setSidebarCollapsed(collapsed) {
    if (!els.appLayout || !els.sidebar) return;
    els.appLayout.classList.toggle("is-sidebar-collapsed", collapsed);
    els.sidebar.classList.toggle("is-collapsed", collapsed);
    if (els.sidebarToggle) {
      els.sidebarToggle.setAttribute("aria-label", collapsed ? "展开侧边栏" : "收起侧边栏");
      els.sidebarToggle.title = collapsed ? "展开侧边栏" : "收起侧边栏";
      els.sidebarToggle.querySelector("span").textContent = collapsed ? "›" : "‹";
    }
    try { localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0"); } catch (_) {}
  }

  function restoreSidebarState() {
    let collapsed = false;
    try { collapsed = localStorage.getItem(SIDEBAR_KEY) === "1"; } catch (_) {}
    setSidebarCollapsed(collapsed);
  }

  function activateView(view) {
    state.currentView = view;
    els.navItems.forEach((item) => {
      const active = item.dataset.view === view;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-current", active ? "page" : "false");
    });
    els.viewPanels.forEach((panel) => {
      const active = panel.dataset.viewPanel === view;
      panel.classList.toggle("is-active", active);
      panel.hidden = !active;
    });

    stopDashboardPolling();
    if (view === "dashboard") {
      loadDashboard();
      setupDashboardPolling();
    } else if (view === "users") {
      if (!state.viewLoaded.users) {
        loadUsers();
        loadAuditLogs();
      }
    } else {
      setupAutoRefresh();
    }
  }

  function renderStats(items, total) {
    const running = items.filter((x) => x.status === "running").length;
    const exited = items.filter((x) => x.status === "exited").length;
    const error = items.filter((x) => x.status === "dead" || x.health === "unhealthy").length;
    els.runningCount.textContent = running;
    els.exitedCount.textContent = exited;
    els.errorCount.textContent = error;
    els.totalCount.textContent = total;
    els.summaryText.textContent = `当前显示 ${items.length} / ${total} 个容器`;
  }

  function renderTable(items) {
    if (!items.length) {
      els.tableBody.innerHTML = '<tr><td colspan="8" class="empty-cell">没有匹配的容器</td></tr>';
      return;
    }
    els.tableBody.innerHTML = items.map((item) => {
      const ports = (item.ports || []).slice(0, 2).map(escapeHtml).join("<br>") || "-";
      const statusClass = item.health === "unhealthy" ? "dead" : (item.status || "unknown");
      return `
        <tr>
          <td><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.id)}</small></td>
          <td>${escapeHtml(item.server_name || "local")}<small>${escapeHtml(item.server_ip || "")}</small></td>
          <td>${escapeHtml(item.container_type || "other")}</td>
          <td>${escapeHtml(item.image)}</td>
          <td><span class="status-badge ${escapeHtml(statusClass)}">${escapeHtml(statusText(item.status, item.health))}</span></td>
          <td>${ports}</td>
          <td>${escapeHtml((item.created_at || "").replace("T", " ").replace("Z", ""))}</td>
          <td class="row-actions">
            <button data-action="start" data-id="${escapeHtml(item.docker_id || item.id)}">启动</button>
            <button data-action="stop" data-id="${escapeHtml(item.docker_id || item.id)}">停止</button>
            <button data-action="restart" data-id="${escapeHtml(item.docker_id || item.id)}">重启</button>
            <button data-action="logs" data-id="${escapeHtml(item.docker_id || item.id)}" data-name="${escapeHtml(item.name)}">日志</button>
            <button data-action="terminal" data-id="${escapeHtml(item.docker_id || item.id)}" data-name="${escapeHtml(item.name)}">进入</button>
            <button data-action="delete" data-id="${escapeHtml(item.docker_id || item.id)}">删除</button>
          </td>
        </tr>`;
    }).join("");
  }

  function renderPager(data) {
    state.total = data.total || 0;
    const pages = data.pages || 0;
    els.pageInfo.textContent = `第 ${state.page} / ${pages || 1} 页`;
    els.prevPage.disabled = state.page <= 1;
    els.nextPage.disabled = pages > 0 && state.page >= pages;
  }

  function renderImageList(images) {
    els.imageSummaryText.textContent = `当前服务器共 ${images.length} 个镜像`;
    if (!images.length) {
      els.imageListBody.innerHTML = '<div class="empty-cell">当前服务器没有可用镜像</div>';
      return;
    }
    els.imageListBody.innerHTML = images.map((img) => {
      const created = (img.created_at || "").replace("T", " ").replace("Z", "");
      return `
        <article class="image-item" title="${escapeHtml(img.name)}">
          <div class="image-main">
            <strong>${escapeHtml(img.repository || img.name)}</strong>
            <small>${escapeHtml(img.id || "-")}</small>
          </div>
          <span class="image-tag">${escapeHtml(img.tag || "latest")}</span>
          <span class="image-meta">${escapeHtml(img.image_type || "other")}</span>
          <span class="image-meta">${escapeHtml(formatBytes(img.size))}</span>
          <span class="image-time">${escapeHtml(created || "-")}</span>
        </article>`;
    }).join("");
  }

  function metricPercentText(value) {
    return `${clampPercent(value).toFixed(1).replace(".0", "")}%`;
  }

  function renderDashboard(data) {
    const cpu = data.cpu || {};
    const memory = data.memory || {};
    const disk = data.disk || {};
    const network = data.network || {};
    const totalRate = Number(network.rx_rate || 0) + Number(network.tx_rate || 0);
    const sampledAt = data.sampled_at ? new Date(data.sampled_at) : new Date();
    const timeLabel = Number.isNaN(sampledAt.getTime()) ? "--" : sampledAt.toLocaleTimeString();

    els.cpuPercent.textContent = metricPercentText(cpu.percent);
    setBar(els.cpuBar, cpu.percent);
    els.cpuMeta.textContent = `${cpu.cores || 1} 核 · ${timeLabel}`;

    els.memoryPercent.textContent = metricPercentText(memory.percent);
    setBar(els.memoryBar, memory.percent);
    els.memoryMeta.textContent = `${formatBytes(memory.used)} / ${formatBytes(memory.total)}`;

    els.diskPercent.textContent = metricPercentText(disk.percent);
    setBar(els.diskBar, disk.percent);
    els.diskMeta.textContent = `${formatBytes(disk.used)} / ${formatBytes(disk.total)}`;

    els.networkRate.textContent = formatRate(totalRate);
    setBar(els.networkBar, Math.min(100, totalRate / (1024 * 1024) * 10));
    els.networkMeta.textContent = `入 ${formatRate(network.rx_rate)} · 出 ${formatRate(network.tx_rate)}`;
    els.dashboardSummary.textContent = `最近采样：${timeLabel} · 服务端缓存 ${data.cache_ttl_seconds || 30} 秒`;

    state.dashboardHistory.push({
      label: timeLabel,
      cpu: clampPercent(cpu.percent),
      memory: clampPercent(memory.percent),
      disk: clampPercent(disk.percent),
      network: Math.min(100, totalRate / (1024 * 1024) * 10),
    });
    state.dashboardHistory = state.dashboardHistory.slice(-24);
    drawMetricsChart();
  }

  function drawMetricsChart() {
    const canvas = els.metricsChart;
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    const padding = { left: 44, right: 18, top: 22, bottom: 34 };
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "rgba(2, 6, 23, 0.35)";
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "rgba(148, 197, 255, 0.12)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = padding.top + (height - padding.top - padding.bottom) * (i / 4);
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();
    }
    if (!state.dashboardHistory.length) return;
    const keys = [
      ["cpu", "#5eb8f0"],
      ["memory", "#34d399"],
      ["disk", "#fbbf24"],
      ["network", "#f87171"],
    ];
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const xFor = (index) => padding.left + (plotWidth * index) / Math.max(1, state.dashboardHistory.length - 1);
    const yFor = (value) => padding.top + plotHeight - (plotHeight * clampPercent(value)) / 100;

    keys.forEach(([key, color]) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      state.dashboardHistory.forEach((point, index) => {
        const x = xFor(index);
        const y = yFor(point[key]);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    });
  }

  async function loadDashboard(force) {
    const interval = Number(els.dashboardInterval ? els.dashboardInterval.value : 30000) || 30000;
    const now = Date.now();
    if (!force && state.dashboardCache && now - state.dashboardCacheAt < Math.min(interval, 30000)) {
      renderDashboard(state.dashboardCache);
      return;
    }
    if (els.refreshDashboardBtn) els.refreshDashboardBtn.disabled = true;
    try {
      const body = await Api.getDashboardMetrics();
      const data = (body && body.data) || {};
      state.dashboardCache = data;
      state.dashboardCacheAt = Date.now();
      state.viewLoaded.dashboard = true;
      renderDashboard(data);
    } catch (err) {
      toast(err.message || "资源指标加载失败", "error");
      if (els.dashboardSummary) els.dashboardSummary.textContent = "资源数据加载失败，请稍后重试。";
    } finally {
      if (els.refreshDashboardBtn) els.refreshDashboardBtn.disabled = false;
    }
  }

  function stopDashboardPolling() {
    if (state.dashboardTimer) {
      clearInterval(state.dashboardTimer);
      state.dashboardTimer = null;
    }
  }

  function setupDashboardPolling() {
    stopDashboardPolling();
    if (state.currentView !== "dashboard" || document.hidden) return;
    const interval = Number(els.dashboardInterval ? els.dashboardInterval.value : 30000) || 30000;
    state.dashboardTimer = setInterval(() => loadDashboard(true), Math.max(30000, interval));
  }

  function userParams() {
    return {
      keyword: els.userKeyword.value.trim(),
      status: els.userStatus.value,
      sort: els.userSort.value,
      page: 1,
      page_size: 50,
    };
  }

  function renderUsers(items, total) {
    els.usersSummary.textContent = `当前匹配 ${total || 0} 个用户，展示 ${items.length} 条`;
    if (!items.length) {
      els.userTableBody.innerHTML = '<tr><td colspan="5" class="empty-cell">没有匹配的用户</td></tr>';
      return;
    }
    els.userTableBody.innerHTML = items.map((user) => `
      <tr>
        <td><strong>${escapeHtml(user.username)}</strong><small>${escapeHtml(user.email || "-")}</small></td>
        <td><span class="status-badge ${user.is_active ? "running" : "exited"}">${user.is_active ? "启用" : "停用"}</span></td>
        <td>${escapeHtml((user.roles || []).join(", ") || (user.is_admin ? "admin" : "-"))}</td>
        <td><small>${escapeHtml((user.permissions || []).join(", ") || "-")}</small></td>
        <td>${escapeHtml((user.last_login_at || "").replace("T", " ").replace("Z", "") || "-")}</td>
      </tr>`).join("");
  }

  async function loadUsers() {
    if (!els.userTableBody) return;
    els.userTableBody.innerHTML = '<tr><td colspan="5" class="empty-cell">正在加载用户数据...</td></tr>';
    try {
      const body = await Api.listUsers(userParams());
      const data = body.data || { items: [], total: 0 };
      state.viewLoaded.users = true;
      renderUsers(data.items || [], data.total || 0);
    } catch (err) {
      els.userTableBody.innerHTML = '<tr><td colspan="5" class="empty-cell">用户数据加载失败</td></tr>';
      toast(err.message || "用户数据加载失败", "error");
    }
  }

  function auditParams() {
    return {
      user: els.auditUser.value.trim(),
      action: els.auditAction.value,
      startTime: els.auditStartTime.value,
      endTime: els.auditEndTime.value,
      page: 1,
      page_size: 50,
    };
  }

  function renderAuditLogs(items) {
    if (!items.length) {
      els.auditTableBody.innerHTML = '<tr><td colspan="6" class="empty-cell">没有匹配的审计日志</td></tr>';
      return;
    }
    els.auditTableBody.innerHTML = items.map((log) => {
      const before = log.before && log.before.status ? log.before.status : "-";
      const after = log.after && log.after.status ? log.after.status : "-";
      return `
        <tr>
          <td>${escapeHtml(log.username || "system")}</td>
          <td>${escapeHtml(log.action || "-")}<small>${escapeHtml(log.result || "")}</small></td>
          <td>${escapeHtml(log.container || "-")}</td>
          <td><small>${escapeHtml(before)} → ${escapeHtml(after)}</small></td>
          <td>${escapeHtml(log.ip || "-")}<small>${escapeHtml(log.device || "-")}</small></td>
          <td>${escapeHtml((log.created_at || "").replace("T", " ").replace("Z", ""))}</td>
        </tr>`;
    }).join("");
  }

  async function loadAuditLogs() {
    if (!els.auditTableBody) return;
    els.auditTableBody.innerHTML = '<tr><td colspan="6" class="empty-cell">正在加载审计日志...</td></tr>';
    try {
      const body = await Api.listAuditLogs(auditParams());
      const data = body.data || { items: [] };
      renderAuditLogs(data.items || []);
    } catch (err) {
      els.auditTableBody.innerHTML = '<tr><td colspan="6" class="empty-cell">审计日志加载失败</td></tr>';
      toast(err.message || "审计日志加载失败", "error");
    }
  }

  function currentParams() {
    return {
      keyword: els.keyword.value.trim(),
      queryField: els.queryField.value,
      status: els.statusFilter.value,
      image: els.imageFilter.value,
      page: state.page,
      page_size: state.pageSize,
    };
  }

  async function loadContainers() {
    els.refreshBtn.disabled = true;
    try {
      const body = await Api.listContainers(currentParams());
      const data = body.data || { items: [], total: 0, page: 1, pages: 0 };
      state.items = data.items || [];
      renderStats(state.items, data.total || 0);
      renderTable(state.items);
      renderPager(data);
    } catch (err) {
      toast(err.message || "容器列表加载失败", "error");
      els.tableBody.innerHTML = '<tr><td colspan="8" class="empty-cell">容器列表加载失败</td></tr>';
    } finally {
      els.refreshBtn.disabled = false;
    }
  }

  async function loadImages() {
    try {
      const body = await Api.listImages("local");
      state.images = (body.data && body.data.items) || [];
      const options = ['<option value="">镜像：全部</option>'].concat(
        state.images.map((img) => `<option value="${escapeHtml(img.name)}">${escapeHtml(img.name)}</option>`)
      );
      els.imageFilter.innerHTML = options.join("");
      els.createImage.innerHTML = state.images.length
        ? state.images.map((img) => `<option value="${escapeHtml(img.name)}">${escapeHtml(img.name)}</option>`).join("")
        : '<option value="">暂无可用镜像</option>';
      renderImageList(state.images);
    } catch (err) {
      els.imageSummaryText.textContent = "镜像数据加载失败";
      els.imageListBody.innerHTML = '<div class="empty-cell">镜像列表加载失败</div>';
      toast(err.message || "镜像列表加载失败", "error");
    }
  }

  let filterTimer = null;
  function scheduleReload() {
    clearTimeout(filterTimer);
    filterTimer = setTimeout(() => {
      state.page = 1;
      loadContainers();
    }, 300);
  }

  function openCreateModal() {
    els.createTip.textContent = "";
    els.modal.hidden = false;
    els.createName.focus();
  }

  function closeCreateModal() {
    els.modal.hidden = true;
    els.createForm.reset();
    els.startAfterCreate.checked = true;
  }

  async function openLogModal(id, name) {
    state.activeLogId = id;
    state.activeLogName = name || id;
    els.logSubtitle.textContent = `${state.activeLogName} · 最近 200 行`;
    els.logContent.textContent = "正在加载日志...";
    els.logModal.hidden = false;
    await refreshLogModal();
  }

  function closeLogModal() {
    els.logModal.hidden = true;
    state.activeLogId = null;
    state.activeLogName = "";
  }

  async function refreshLogModal() {
    if (!state.activeLogId) return;
    els.refreshLogBtn.disabled = true;
    try {
      const body = await Api.getContainerLogs(state.activeLogId, 200);
      const logs = body && body.data ? body.data.logs : "";
      els.logContent.textContent = logs || "当前容器暂无日志输出";
      els.logContent.scrollTop = els.logContent.scrollHeight;
    } catch (err) {
      els.logContent.textContent = err.message || "日志加载失败";
    } finally {
      els.refreshLogBtn.disabled = false;
    }
  }

  function openTerminalPage(id, name) {
    const params = new URLSearchParams();
    params.set("container", id);
    if (name) params.set("name", name);
    const hash = new URLSearchParams();
    const token = Api.getAccessToken();
    if (token) hash.set("token", token);
    window.open(`/console/terminal?${params.toString()}#${hash.toString()}`, "_blank", "noopener");
  }

  async function submitCreate(e) {
    e.preventDefault();
    const hostPort = Number(els.hostPort.value || 0);
    const containerPort = Number(els.containerPort.value || 0);
    const ports = hostPort && containerPort ? [{
      host_ip: "0.0.0.0",
      host_port: hostPort,
      container_port: containerPort,
      protocol: "tcp",
    }] : [];
    const payload = {
      server: "local",
      image: els.createImage.value,
      name: els.createName.value.trim(),
      ports,
      restart_policy: els.restartPolicy.value,
      is_start_after_create: els.startAfterCreate.checked,
    };
    els.createTip.textContent = "正在创建容器...";
    try {
      await Api.createContainer(payload);
      toast("容器创建成功", "success");
      closeCreateModal();
      await loadContainers();
    } catch (err) {
      els.createTip.textContent = err.message || "容器创建失败";
    }
  }

  async function handleAction(action, id) {
    if (action === "logs") {
      const item = state.items.find((x) => (x.docker_id || x.id) === id);
      await openLogModal(id, item ? item.name : id);
      return;
    }
    if (action === "terminal") {
      const item = state.items.find((x) => (x.docker_id || x.id) === id);
      openTerminalPage(id, item ? item.name : id);
      return;
    }
    const confirmText = {
      start: "确认启动该容器？",
      stop: "确认停止该容器？",
      restart: "确认重启该容器？",
      delete: "确认删除该容器？",
    }[action];
    if (!window.confirm(confirmText)) return;
    try {
      if (action === "start") await Api.startContainer(id);
      if (action === "stop") await Api.stopContainer(id);
      if (action === "restart") await Api.restartContainer(id);
      if (action === "delete") await Api.deleteContainer(id, true);
      toast("操作已完成", "success");
      await loadContainers();
    } catch (err) {
      toast(err.message || "操作失败", "error");
    }
  }

  function bindEvents() {
    if (els.sidebarToggle) {
      els.sidebarToggle.addEventListener("click", () => {
        setSidebarCollapsed(!els.sidebar.classList.contains("is-collapsed"));
      });
    }
    els.navItems.forEach((item) => {
      item.addEventListener("click", () => activateView(item.dataset.view || "containers"));
    });
    if (els.settingsBtn && els.settingsMenu) {
      els.settingsBtn.addEventListener("click", () => {
        const expanded = els.settingsBtn.getAttribute("aria-expanded") === "true";
        els.settingsBtn.setAttribute("aria-expanded", expanded ? "false" : "true");
        els.settingsMenu.hidden = expanded;
      });
    }
    if (els.logoutBtn) {
      els.logoutBtn.addEventListener("click", async () => {
        try { await Api.logout(); } catch (_) { Api.clearAccessToken(); }
        window.location.replace("/");
      });
    }
    els.keyword.addEventListener("input", scheduleReload);
    els.queryField.addEventListener("change", scheduleReload);
    els.statusFilter.addEventListener("change", scheduleReload);
    els.imageFilter.addEventListener("change", scheduleReload);
    els.pageSize.addEventListener("change", () => {
      state.pageSize = Number(els.pageSize.value || 20);
      state.page = 1;
      loadContainers();
    });
    els.prevPage.addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        loadContainers();
      }
    });
    els.nextPage.addEventListener("click", () => {
      state.page += 1;
      loadContainers();
    });
    els.refreshBtn.addEventListener("click", loadContainers);
    els.createBtn.addEventListener("click", openCreateModal);
    els.closeCreateModal.addEventListener("click", closeCreateModal);
    els.cancelCreate.addEventListener("click", closeCreateModal);
    els.createForm.addEventListener("submit", submitCreate);
    els.closeLogModal.addEventListener("click", closeLogModal);
    els.closeLogBtn.addEventListener("click", closeLogModal);
    els.refreshLogBtn.addEventListener("click", refreshLogModal);
    els.tableBody.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-action]");
      if (!btn) return;
      handleAction(btn.dataset.action, btn.dataset.id);
    });
    els.autoRefresh.addEventListener("change", () => {
      setupAutoRefresh();
    });
    if (els.refreshDashboardBtn) els.refreshDashboardBtn.addEventListener("click", () => loadDashboard(true));
    if (els.dashboardInterval) {
      els.dashboardInterval.addEventListener("change", () => {
        loadDashboard(true);
        setupDashboardPolling();
      });
    }
    if (els.refreshUsersBtn) els.refreshUsersBtn.addEventListener("click", loadUsers);
    if (els.refreshAuditBtn) els.refreshAuditBtn.addEventListener("click", loadAuditLogs);
    let userFilterTimer = null;
    [els.userKeyword, els.userStatus, els.userSort].forEach((node) => {
      if (!node) return;
      node.addEventListener(node.tagName === "INPUT" ? "input" : "change", () => {
        clearTimeout(userFilterTimer);
        userFilterTimer = setTimeout(loadUsers, 300);
      });
    });
    let auditFilterTimer = null;
    [els.auditUser, els.auditAction, els.auditStartTime, els.auditEndTime].forEach((node) => {
      if (!node) return;
      node.addEventListener(node.tagName === "INPUT" ? "input" : "change", () => {
        clearTimeout(auditFilterTimer);
        auditFilterTimer = setTimeout(loadAuditLogs, 300);
      });
    });
    document.addEventListener("visibilitychange", () => {
      if (state.currentView === "dashboard") setupDashboardPolling();
      else setupAutoRefresh();
    });
  }

  function setupAutoRefresh() {
    if (state.timer) {
      clearInterval(state.timer);
      state.timer = null;
    }
    if (state.currentView !== "containers") return;
    if (els.autoRefresh.checked && !document.hidden) {
      state.timer = setInterval(loadContainers, 30000);
    }
  }

  async function ensureAuthenticated() {
    if (Api.getAccessToken()) {
      try {
        await Api.me();
        return true;
      } catch (_) {
        Api.clearAccessToken();
      }
    }
    const refreshed = await Api.refresh();
    if (!refreshed) return false;
    try {
      await Api.me();
      return true;
    } catch (_) {
      Api.clearAccessToken();
      return false;
    }
  }

  (async function bootstrap() {
    const ok = await ensureAuthenticated();
    if (!ok) {
      window.location.replace("/");
      return;
    }
    restoreSidebarState();
    bindEvents();
    await loadImages();
    await loadContainers();
    state.viewLoaded.containers = true;
    setupAutoRefresh();
  })();
})();
