/*
 * Modo VR (WebXR) do dashboard do Tello.
 *
 * Sem Three.js examples (VRButton/controllers) porque o build vendorizado
 * (three.min.js) nao inclui os arquivos de exemplo - entao a sessao WebXR e
 * o mapeamento de input dos controllers sao feitos "na mao" aqui, lendo
 * navigator.xr e session.inputSources diretamente.
 *
 * IMPORTANTE sobre os indices de botao/eixo dos controllers: sao baseados no
 * mapeamento "xr-standard" tipico do Meta Quest, mas podem variar por
 * navegador/firmware. Abra com "?debug=1" na URL (ex: /vr?debug=1) para ver
 * no console o estado bruto dos controllers e recalibrar os indices abaixo
 * se algum botao nao corresponder.
 */

const DEBUG = new URLSearchParams(location.search).has("debug");

const socket = io();

const overlay = document.getElementById("vrOverlay");
const unsupportedMsg = document.getElementById("vrUnsupported");
const exitHint = document.getElementById("exitHint");
const enterBtn = document.getElementById("enterVrBtn");

// --- Estado vindo do servidor ---
let latestStatus = null;
let hudDirty = true;

socket.on("status", (status) => {
  latestStatus = status;
  hudDirty = true;
});

socket.on("detection_event", (event) => {
  if (event.kind === "fire") {
    latestStatus = { ...(latestStatus || {}), message: `FOGO detectado as ${event.time}!` };
    hudDirty = true;
  }
});

// --- Textura de video (atualizada a partir dos frames JPEG em base64) ---
const videoImg = new Image();
let videoFrameDirty = false;
videoImg.onload = () => {
  videoFrameDirty = true;
};
socket.on("video_frame", (payload) => {
  videoImg.src = payload.image;
});

// --- Three.js: cena, camera, renderer ---
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x05070a);

const camera = new THREE.PerspectiveCamera(70, window.innerWidth / window.innerHeight, 0.05, 50);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.xr.enabled = true;
document.body.appendChild(renderer.domElement);
renderer.domElement.style.position = "fixed";
renderer.domElement.style.inset = "0";

window.addEventListener("resize", () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

scene.add(new THREE.HemisphereLight(0xffffff, 0x202030, 1.1));

// Plano com o stream da camera, ~2.5m a frente do usuario.
const videoTexture = new THREE.Texture(videoImg);
videoTexture.minFilter = THREE.LinearFilter;
videoTexture.magFilter = THREE.LinearFilter;

const VIDEO_WIDTH = 3.2;
const VIDEO_HEIGHT = 1.8;
const videoPlane = new THREE.Mesh(
  new THREE.PlaneGeometry(VIDEO_WIDTH, VIDEO_HEIGHT),
  new THREE.MeshBasicMaterial({ map: videoTexture })
);
videoPlane.position.set(0, 1.6, -2.6);
scene.add(videoPlane);

// Placeholder enquanto nao chega nenhum frame ainda.
const placeholderPlane = new THREE.Mesh(
  new THREE.PlaneGeometry(VIDEO_WIDTH, VIDEO_HEIGHT),
  new THREE.MeshBasicMaterial({ color: 0x0d121b })
);
placeholderPlane.position.copy(videoPlane.position);
placeholderPlane.position.z += 0.001;
scene.add(placeholderPlane);

// HUD de telemetria: canvas 2D desenhado em texto, projetado como textura.
const hudCanvas = document.createElement("canvas");
hudCanvas.width = 900;
hudCanvas.height = 360;
const hudCtx = hudCanvas.getContext("2d");
const hudTexture = new THREE.CanvasTexture(hudCanvas);

const HUD_WIDTH = 1.5;
const HUD_HEIGHT = 0.6;
const hudPlane = new THREE.Mesh(
  new THREE.PlaneGeometry(HUD_WIDTH, HUD_HEIGHT),
  new THREE.MeshBasicMaterial({ map: hudTexture, transparent: true })
);
hudPlane.position.set(0, 0.55, -2.2);
hudPlane.rotation.x = -0.22;
scene.add(hudPlane);

function drawHud() {
  const s = latestStatus || {};
  const ctx = hudCtx;
  ctx.clearRect(0, 0, hudCanvas.width, hudCanvas.height);

  ctx.fillStyle = "rgba(13, 18, 27, 0.82)";
  ctx.strokeStyle = "#263243";
  ctx.lineWidth = 4;
  roundRect(ctx, 4, 4, hudCanvas.width - 8, hudCanvas.height - 8, 24);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = s.connected ? "#19d39a" : "#ff4d67";
  ctx.font = "bold 46px sans-serif";
  ctx.fillText(s.connected ? "TELLO ONLINE" : "TELLO OFFLINE", 36, 70);

  ctx.fillStyle = "#eef4f8";
  ctx.font = "bold 38px sans-serif";
  const battery = s.battery == null ? "--%" : `${s.battery}%`;
  const wifi = s.wifi_dbm == null ? "-- dBm" : `${s.wifi_dbm} dBm`;
  ctx.fillText(`Bateria: ${battery}`, 36, 140);
  ctx.fillText(`Wi-Fi: ${wifi}`, 36, 190);
  ctx.fillText(`Altura: ${s.session_altitude || 0} cm`, 36, 240);
  ctx.fillText(`Pessoas: ${s.person_count || 0}  Fogo: ${s.fire_count || 0}`, 36, 290);

  ctx.fillStyle = "#92a2b5";
  ctx.font = "30px sans-serif";
  const message = (s.message || "").slice(0, 70);
  ctx.fillText(message, 36, 340);

  hudTexture.needsUpdate = true;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

drawHud();

// --- Entrar/sair do VR ---
async function checkXrSupport() {
  if (!navigator.xr || !navigator.xr.isSessionSupported) {
    enterBtn.disabled = true;
    unsupportedMsg.classList.remove("hidden");
    return;
  }
  const supported = await navigator.xr.isSessionSupported("immersive-vr").catch(() => false);
  if (!supported) {
    enterBtn.disabled = true;
    unsupportedMsg.classList.remove("hidden");
  }
}

enterBtn.addEventListener("click", async () => {
  try {
    const session = await navigator.xr.requestSession("immersive-vr", {
      optionalFeatures: ["local-floor", "bounded-floor"],
    });
    await renderer.xr.setSession(session);
    overlay.classList.add("hidden");
    exitHint.classList.remove("hidden");

    session.addEventListener("end", () => {
      overlay.classList.remove("hidden");
      exitHint.classList.add("hidden");
    });
  } catch (exc) {
    console.error("Falha ao entrar em VR:", exc);
    alert(`Nao foi possivel entrar em VR: ${exc.message || exc}`);
  }
});

checkXrSupport();

// --- Controle do drone via gamepads dos controllers XR ---
const CONTROL_SPEED = 70;
const DEADZONE = 0.16;

let rcState = { lr: 0, fb: 0, ud: 0, yaw: 0 };
let lastRcSentAt = 0;
const buttonWasPressed = {}; // chave: `${handedness}-${index}`

function axisValue(gamepad, index) {
  const value = gamepad.axes[index] || 0;
  return Math.abs(value) > DEADZONE ? value : 0;
}

function emitAction(name) {
  socket.emit("action", { name });
}

// Controle de Xbox (ou qualquer gamepad Bluetooth "standard") pareado direto
// no sistema do Quest. Nao depende da sessao XR - so do Gamepad API normal.
// Layout "standard": eixo 0/1 = stick esquerdo, eixo 2/3 = stick direito;
// botoes 0-3 = A/B/X/Y.
function handleStandardGamepad(next) {
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  const pad = Array.from(pads).find((p) => p && p.connected);
  if (!pad) return;

  if (DEBUG) {
    console.log(
      `[VR][gamepad] ${pad.id} axes=${pad.axes.map((v) => v.toFixed(2))} buttons=${pad.buttons
        .map((b) => (b.pressed ? "1" : "0"))
        .join("")}`
    );
  }

  next.lr = Math.round(axisValue(pad, 0) * CONTROL_SPEED);
  next.fb = Math.round(-axisValue(pad, 1) * CONTROL_SPEED);
  next.yaw = Math.round(axisValue(pad, 2) * CONTROL_SPEED);
  next.ud = Math.round(-axisValue(pad, 3) * CONTROL_SPEED);

  const pressedEdge = (index) => {
    const key = `xbox-${index}`;
    const pressedNow = Boolean(pad.buttons[index]?.pressed);
    const wasPressed = Boolean(buttonWasPressed[key]);
    buttonWasPressed[key] = pressedNow;
    return pressedNow && !wasPressed;
  };

  // A=0 decolar, B=1 pousar, X=2 foto, Y=3 gravar (layout tipico de Xbox).
  if (pressedEdge(0)) emitAction("takeoff");
  if (pressedEdge(1)) emitAction("land");
  if (pressedEdge(2)) emitAction("photo");
  if (pressedEdge(3)) emitAction("record");
}

function handleControllerInput(session) {
  const next = { lr: 0, fb: 0, ud: 0, yaw: 0 };
  let usedTrackedController = false;

  for (const source of session.inputSources) {
    if (!source.gamepad || source.targetRayMode !== "tracked-pointer") continue;
    usedTrackedController = true;
    const gp = source.gamepad;
    const hand = source.handedness; // "left" | "right" | "none"

    if (DEBUG) {
      console.log(
        `[VR] ${hand} axes=${gp.axes.map((v) => v.toFixed(2))} buttons=${gp.buttons
          .map((b) => (b.pressed ? "1" : "0"))
          .join("")}`
      );
    }

    // Thumbstick costuma estar em axes[2] (x) e axes[3] (y); fallback pros
    // indices 0/1 em navegadores que ainda usam o layout antigo.
    const stickX = gp.axes.length > 2 ? axisValue(gp, 2) : axisValue(gp, 0);
    const stickY = gp.axes.length > 3 ? axisValue(gp, 3) : axisValue(gp, 1);

    if (hand === "left") {
      next.lr = Math.round(stickX * CONTROL_SPEED);
      next.fb = Math.round(-stickY * CONTROL_SPEED);
    } else if (hand === "right") {
      next.yaw = Math.round(stickX * CONTROL_SPEED);
      next.ud = Math.round(-stickY * CONTROL_SPEED);
    }

    // Botoes (mapeamento "xr-standard" tipico do Quest):
    //   0 = trigger, 1 = squeeze/grip, 3 = clique do thumbstick,
    //   4 = botao A/X, 5 = botao B/Y.
    const pressedEdge = (index) => {
      const key = `${hand}-${index}`;
      const pressedNow = Boolean(gp.buttons[index]?.pressed);
      const wasPressed = Boolean(buttonWasPressed[key]);
      buttonWasPressed[key] = pressedNow;
      return pressedNow && !wasPressed;
    };

    if (hand === "right" && pressedEdge(0)) emitAction("photo");
    if (hand === "right" && pressedEdge(1)) emitAction("record");
    if (hand === "left" && pressedEdge(4)) emitAction("takeoff");
    if (hand === "left" && pressedEdge(5)) emitAction("land");
  }

  // Fallback: gamepad "normal" pareado por Bluetooth (ex: controle de Xbox).
  // So entra em acao se nenhum controller rastreado (Meta) foi lido acima -
  // assim os dois nao brigam pelo mesmo "rc" ao mesmo tempo.
  if (!usedTrackedController) {
    handleStandardGamepad(next);
  }

  const now = performance.now();
  const changed = Object.keys(next).some((key) => next[key] !== rcState[key]);
  if (changed || now - lastRcSentAt > 180) {
    rcState = next;
    lastRcSentAt = now;
    socket.emit("rc", rcState);
  }
}

// --- Loop de render ---
let lastHudUpdateAt = 0;

renderer.setAnimationLoop((timestamp, frame) => {
  if (videoFrameDirty) {
    videoTexture.needsUpdate = true;
    placeholderPlane.visible = false;
    videoFrameDirty = false;
  }

  if (hudDirty && timestamp - lastHudUpdateAt > 200) {
    drawHud();
    hudDirty = false;
    lastHudUpdateAt = timestamp;
  }

  const session = renderer.xr.getSession();
  if (session) {
    handleControllerInput(session);
  }

  renderer.render(scene, camera);
});
