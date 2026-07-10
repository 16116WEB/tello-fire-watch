const socket = io();

const DEFAULT_BINDS = {
  takeoff: "KeyT",
  land: "KeyL",
  emergency: "KeyE",
  photo: "KeyP",
  record: "KeyR",
  up: "ArrowUp",
  down: "ArrowDown",
  yawLeft: "ArrowLeft",
  yawRight: "ArrowRight",
  forward: "KeyW",
  backward: "KeyS",
  left: "KeyA",
  right: "KeyD"
};

const ACTION_LABELS = {
  takeoff: "Decolar",
  land: "Pousar",
  emergency: "Emergencia",
  photo: "Foto",
  record: "Gravar",
  forward: "Frente",
  backward: "Tras",
  left: "Esquerda",
  right: "Direita",
  up: "Subir",
  down: "Descer",
  yawLeft: "Yaw esquerda",
  yawRight: "Yaw direita"
};

let binds = loadBinds();
let pressed = new Set();
let rcState = { lr: 0, fb: 0, ud: 0, yaw: 0 };
let lastRcSent = 0;
let waitingBind = null;
let previousGamepadButtons = {};
let currentEvents = [];
let alertTimer = null;

const $ = (id) => document.getElementById(id);

function loadBinds() {
  const saved = localStorage.getItem("tello-binds");
  if (!saved) return { ...DEFAULT_BINDS };
  try {
    return { ...DEFAULT_BINDS, ...JSON.parse(saved) };
  } catch {
    return { ...DEFAULT_BINDS };
  }
}

function saveBinds() {
  localStorage.setItem("tello-binds", JSON.stringify(binds));
}

function emitAction(name) {
  socket.emit("action", { name });
}

function codeToText(code) {
  return code.replace("Key", "").replace("Arrow", "Seta ");
}

function renderBinds() {
  const list = $("bindList");
  list.innerHTML = "";

  Object.keys(ACTION_LABELS).forEach((action) => {
    const row = document.createElement("div");
    row.className = "bind-row";

    const label = document.createElement("label");
    label.textContent = ACTION_LABELS[action];

    const input = document.createElement("input");
    input.readOnly = true;
    input.value = codeToText(binds[action]);
    input.addEventListener("focus", () => {
      waitingBind = action;
      input.value = "pressione";
    });

    row.append(label, input);
    list.appendChild(row);
  });
}

function buildKeyboardRc() {
  const speed = 45;
  const next = { lr: 0, fb: 0, ud: 0, yaw: 0 };

  if (pressed.has(binds.left)) next.lr -= speed;
  if (pressed.has(binds.right)) next.lr += speed;
  if (pressed.has(binds.forward)) next.fb += speed;
  if (pressed.has(binds.backward)) next.fb -= speed;
  if (pressed.has(binds.up)) next.ud += speed;
  if (pressed.has(binds.down)) next.ud -= speed;
  if (pressed.has(binds.yawLeft)) next.yaw -= speed;
  if (pressed.has(binds.yawRight)) next.yaw += speed;

  return next;
}

function mergeGamepadRc(base) {
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  const pad = Array.from(pads).find(Boolean);
  if (!pad) return base;

  const dead = 0.16;
  const scale = 70;
  const axis = (i) => Math.abs(pad.axes[i] || 0) > dead ? pad.axes[i] : 0;

  base.lr = Math.round(axis(0) * scale);
  base.fb = Math.round(-axis(1) * scale);
  base.yaw = Math.round(axis(2) * scale);
  base.ud = Math.round(-axis(3) * scale);

  const buttonActions = {
    0: "takeoff",
    1: "land",
    2: "photo",
    3: "record"
  };

  Object.entries(buttonActions).forEach(([index, action]) => {
    const pressedNow = Boolean(pad.buttons[index]?.pressed);
    if (pressedNow && !previousGamepadButtons[index]) emitAction(action);
    previousGamepadButtons[index] = pressedNow;
  });

  return base;
}

// --- Joysticks virtuais (touch) ---
let touchLr = 0;
let touchFb = 0;
let touchUd = 0;
let touchYaw = 0;

function attachJoystick(zone, knob, onChange) {
  if (!zone || !knob) return;

  const radius = zone.offsetWidth / 2;
  let activeTouchId = null;

  function updateFromPoint(clientX, clientY) {
    const rect = zone.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const rawDx = clientX - cx;
    const rawDy = clientY - cy;
    const dist = Math.min(Math.hypot(rawDx, rawDy), radius);
    const angle = Math.atan2(rawDy, rawDx);
    const dx = Math.cos(angle) * dist;
    const dy = Math.sin(angle) * dist;

    knob.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
    onChange(dx / radius, dy / radius);
  }

  function reset() {
    activeTouchId = null;
    knob.style.transform = "translate(-50%, -50%)";
    onChange(0, 0);
  }

  zone.addEventListener(
    "touchstart",
    (event) => {
      const touch = event.changedTouches[0];
      activeTouchId = touch.identifier;
      updateFromPoint(touch.clientX, touch.clientY);
      event.preventDefault();
    },
    { passive: false }
  );

  zone.addEventListener(
    "touchmove",
    (event) => {
      const touch = Array.from(event.changedTouches).find((t) => t.identifier === activeTouchId);
      if (!touch) return;
      updateFromPoint(touch.clientX, touch.clientY);
      event.preventDefault();
    },
    { passive: false }
  );

  const endTouch = (event) => {
    const touch = Array.from(event.changedTouches).find((t) => t.identifier === activeTouchId);
    if (!touch) return;
    reset();
  };

  zone.addEventListener("touchend", endTouch);
  zone.addEventListener("touchcancel", endTouch);
}

function mergeTouchRc(base) {
  base.lr = touchLr || base.lr;
  base.fb = touchFb || base.fb;
  base.yaw = touchYaw || base.yaw;
  base.ud = touchUd || base.ud;
  return base;
}

attachJoystick($("joyLeft"), $("joyLeftKnob"), (nx, ny) => {
  touchLr = Math.round(nx * 70);
  touchFb = Math.round(-ny * 70);
});

attachJoystick($("joyRight"), $("joyRightKnob"), (nx, ny) => {
  touchYaw = Math.round(nx * 70);
  touchUd = Math.round(-ny * 70);
});

function sendRcLoop() {
  const now = performance.now();
  const next = mergeTouchRc(mergeGamepadRc(buildKeyboardRc()));
  const changed = Object.keys(next).some((key) => next[key] !== rcState[key]);

  if (changed || now - lastRcSent > 180) {
    rcState = next;
    lastRcSent = now;
    socket.emit("rc", rcState);
    $("rcLr").textContent = rcState.lr;
    $("rcFb").textContent = rcState.fb;
    $("rcUd").textContent = rcState.ud;
    $("rcYaw").textContent = rcState.yaw;
  }

  requestAnimationFrame(sendRcLoop);
}

function renderEvents(events) {
  currentEvents = events || [];
  const log = $("eventLog");
  log.innerHTML = "";

  if (!currentEvents.length) {
    const empty = document.createElement("p");
    empty.className = "empty-log";
    empty.textContent = "Sem eventos nesta sessao.";
    log.appendChild(empty);
    return;
  }

  currentEvents.forEach((event) => {
    const item = document.createElement("div");
    item.className = `event-item ${event.kind}`;
    item.textContent = `${event.time.slice(0, 5)} - ${event.label} detectado (${Math.round(event.confidence)}%)`;
    log.appendChild(item);
  });
}

function showFireAlert(event) {
  $("fireAlertText").textContent = `${event.time} - confianca ${Math.round(event.confidence)}%`;
  $("fireAlert").classList.add("active");
  window.clearTimeout(alertTimer);
  alertTimer = window.setTimeout(() => $("fireAlert").classList.remove("active"), 9000);
}

function updateStatus(status) {
  $("connected").textContent = status.connected ? "online" : "offline";
  $("battery").textContent = status.battery == null ? "--%" : `${status.battery}%`;
  $("wifi").textContent = status.wifi_dbm == null ? "-- dBm" : `${status.wifi_dbm} dBm`;
  $("quality").textContent = status.stream_quality == null ? "--%" : `${status.stream_quality}%`;
  $("vx").textContent = `${status.vx || 0} cm/s`;
  $("vy").textContent = `${status.vy || 0} cm/s`;
  $("vz").textContent = `${status.vz || 0} cm/s`;
  $("height").textContent = `${status.session_altitude || 0} cm`;
  $("hdist").textContent = `${status.horizontal_distance || 0} cm`;
  $("vdist").textContent = `${status.vertical_distance || 0} cm`;
  $("message").textContent = status.message || "";
  $("recordPill").classList.toggle("active", Boolean(status.recording));
  $("recordBtn").textContent = status.recording ? "Parar" : "Gravar";
  $("detectButton").textContent = status.detecting ? "Pausar deteccao" : "Retomar deteccao";
  $("nightButton").classList.toggle("active", Boolean(status.night_mode));
  $("personCount").textContent = status.person_count || 0;
  $("fireCount").textContent = status.fire_count || 0;
  $("confidenceSlider").value = status.confidence_threshold ?? $("confidenceSlider").value;
  $("confidenceLabel").textContent = `${$("confidenceSlider").value}%`;
  renderEvents(status.events);
  drawFlightPath(status.flight_path);
}

function drawFlightPath(path) {
  const canvas = $("pathCanvas");
  if (!canvas || !path || !path.length) return;

  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const xs = path.map((p) => p.x);
  const ys = path.map((p) => p.y);
  const minX = Math.min(0, ...xs);
  const maxX = Math.max(0, ...xs);
  const minY = Math.min(0, ...ys);
  const maxY = Math.max(0, ...ys);
  const spanX = Math.max(50, maxX - minX);
  const spanY = Math.max(50, maxY - minY);
  const padding = 20;
  const scale = Math.min((w - padding * 2) / spanX, (h - padding * 2) / spanY);

  const toCanvas = (x, y) => [padding + (x - minX) * scale, h - padding - (y - minY) * scale];

  // grade leve de referencia
  ctx.strokeStyle = "#1c2734";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const gx = padding + ((w - padding * 2) / 4) * i;
    const gy = padding + ((h - padding * 2) / 4) * i;
    ctx.beginPath();
    ctx.moveTo(gx, padding);
    ctx.lineTo(gx, h - padding);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(padding, gy);
    ctx.lineTo(w - padding, gy);
    ctx.stroke();
  }

  // trilha
  if (path.length > 1) {
    ctx.strokeStyle = "#58a6ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    path.forEach((p, i) => {
      const [cx, cy] = toCanvas(p.x, p.y);
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    });
    ctx.stroke();
  }

  // ponto de decolagem
  const [sx, sy] = toCanvas(0, 0);
  ctx.fillStyle = "#92a2b5";
  ctx.beginPath();
  ctx.arc(sx, sy, 4, 0, Math.PI * 2);
  ctx.fill();

  // posicao atual
  const last = path[path.length - 1];
  const [lx, ly] = toCanvas(last.x, last.y);
  ctx.fillStyle = "#19d39a";
  ctx.beginPath();
  ctx.arc(lx, ly, 6, 0, Math.PI * 2);
  ctx.fill();
}

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => emitAction(button.dataset.action));
});

$("startBtn").addEventListener("click", () => {
  const splash = $("splash");
  const mainApp = $("mainApp");

  mainApp.classList.remove("hidden");
  mainApp.classList.add("entering");
  splash.classList.add("leaving");

  requestAnimationFrame(() => {
    mainApp.classList.remove("entering");
  });

  window.setTimeout(() => {
    splash.classList.add("hidden");
  }, 1550);
});

$("closeAlertBtn").addEventListener("click", () => $("fireAlert").classList.remove("active"));
$("connectBtn").addEventListener("click", () => socket.emit("connect_drone"));
$("disconnectBtn").addEventListener("click", () => socket.emit("disconnect_drone"));

$("detectButton").addEventListener("click", () => {
  const enabled = $("detectButton").textContent.startsWith("Retomar");
  socket.emit("detection", { enabled });
});

$("nightButton").addEventListener("click", () => {
  socket.emit("night_mode", { enabled: !$("nightButton").classList.contains("active") });
});

$("confidenceSlider").addEventListener("input", (event) => {
  $("confidenceLabel").textContent = `${event.target.value}%`;
  socket.emit("confidence", { value: Number(event.target.value) });
});

window.addEventListener("keydown", (event) => {
  if (waitingBind) {
    event.preventDefault();
    binds[waitingBind] = event.code;
    waitingBind = null;
    saveBinds();
    renderBinds();
    return;
  }

  pressed.add(event.code);
  const action = Object.entries(binds).find(([name, code]) => code === event.code && ["takeoff", "land", "emergency", "photo", "record"].includes(name));
  if (action && !event.repeat) {
    event.preventDefault();
    emitAction(action[0]);
  }
});

window.addEventListener("keyup", (event) => {
  pressed.delete(event.code);
});

socket.on("connect", () => {
  $("connBanner").classList.remove("active");
});

socket.on("disconnect", () => {
  $("connBannerText").textContent = "Conexao com o servidor perdida. Tentando reconectar...";
  $("connBanner").classList.add("active");
});

socket.io.on("reconnect_attempt", () => {
  $("connBannerText").textContent = "Tentando reconectar...";
});

socket.on("status", updateStatus);
socket.on("detection_event", (event) => {
  if (event.kind === "fire") showFireAlert(event);
});

socket.on("video_frame", (payload) => {
  const img = $("videoFeed");
  img.src = payload.image;
  $("videoPlaceholder").style.display = "none";
});

renderBinds();
sendRcLoop();
