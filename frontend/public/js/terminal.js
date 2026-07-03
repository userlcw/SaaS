(function () {
  const terminal = document.getElementById("containerTerminal");
  const input = document.getElementById("terminalInput");
  const subtitle = document.getElementById("terminalSubtitle");
  const reconnectBtn = document.getElementById("reconnectBtn");
  const closeBtn = document.getElementById("closeTerminalBtn");

  const params = new URLSearchParams(window.location.search);
  const hashParams = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
  const containerId = params.get("container") || "";
  const containerName = params.get("name") || containerId;
  let socket = null;

  function write(text) {
    terminal.textContent += text;
    terminal.scrollTop = terminal.scrollHeight;
  }

  function setStatus(text) {
    subtitle.textContent = containerName ? `${containerName} · ${text}` : text;
  }

  function closeSocket() {
    if (socket) {
      socket.onclose = null;
      socket.close();
      socket = null;
    }
  }

  function connect() {
    closeSocket();
    terminal.textContent = "";

    if (!containerId) {
      setStatus("缺少容器 ID");
      write("Missing container id.\r\n");
      return;
    }

    const token = hashParams.get("token") || Api.getAccessToken();
    if (!token) {
      setStatus("未登录");
      write("No access token. Please return to the console and login again.\r\n");
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/api/v1/containers/${encodeURIComponent(containerId)}/terminal`;
    socket = new WebSocket(url);
    setStatus("正在连接");
    write(`Connecting to ${containerName || containerId}...\r\n`);

    socket.onopen = () => {
      setStatus("已连接");
      socket.send(JSON.stringify({ token }));
      input.focus();
    };
    socket.onmessage = (event) => {
      write(String(event.data || ""));
    };
    socket.onerror = () => {
      setStatus("连接异常");
      write("\r\nWebSocket connection error.\r\n");
    };
    socket.onclose = () => {
      setStatus("连接已关闭");
      write("\r\n[connection closed]\r\n");
    };
  }

  function send(text) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      write("\r\n[not connected]\r\n");
      return;
    }
    socket.send(text);
  }

  input.addEventListener("keydown", (event) => {
    event.preventDefault();
    if (event.key === "Enter") {
      send("\r");
      return;
    }
    if (event.key === "Backspace") {
      send("\x7f");
      return;
    }
    if (event.key === "Tab") {
      send("\t");
      return;
    }
    if (event.key === "ArrowUp") {
      send("\x1b[A");
      return;
    }
    if (event.key === "ArrowDown") {
      send("\x1b[B");
      return;
    }
    if (event.key === "ArrowRight") {
      send("\x1b[C");
      return;
    }
    if (event.key === "ArrowLeft") {
      send("\x1b[D");
      return;
    }
    if (event.ctrlKey && event.key.toLowerCase() === "c") {
      send("\x03");
      return;
    }
    if (event.ctrlKey && event.key.toLowerCase() === "d") {
      send("\x04");
      return;
    }
    if (event.key.length === 1) {
      send(event.key);
    }
  });

  terminal.addEventListener("click", () => input.focus());
  reconnectBtn.addEventListener("click", connect);
  closeBtn.addEventListener("click", () => window.close());
  window.addEventListener("beforeunload", closeSocket);
  connect();
})();
