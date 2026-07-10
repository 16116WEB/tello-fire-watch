import base64
import csv
import io
import math
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

try:
    from djitellopy import Tello
except Exception:
    Tello = None

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas
except Exception:
    canvas = None

from config import (
    BATTERY_CRITICAL_PCT,
    BATTERY_WARNING_PCT,
    COMMAND_TIMEOUT_SECONDS,
    FIRE_MODEL_CLASSES,
    FIRE_MODEL_PATH,
    MAX_PHOTOS,
    MAX_VIDEOS,
    PERSON_MODEL_PATH,
    PHOTO_DIR,
    VIDEO_DIR,
)
from extensions import socketio

MAX_FLIGHT_PATH_POINTS = 400


def _enforce_media_limit(directory, max_files):
    """Mantem so os 'max_files' arquivos mais recentes em 'directory'."""
    try:
        files = sorted(directory.glob("*"), key=lambda p: p.stat().st_mtime)
    except FileNotFoundError:
        return
    excess = len(files) - max_files
    for old_file in files[: max(0, excess)]:
        try:
            old_file.unlink()
        except OSError:
            pass


class TelloDashboard:
    """Controla o Tello, processa frames e publica estado para a interface."""

    def __init__(self):
        self.tello = None
        self.frame_reader = None
        self.person_model = None
        self.fire_model = None
        self.connected = False
        self.streaming = False
        self.detecting = True
        self.night_mode = False
        self.confidence_threshold = 0.60
        self.nms_iou_threshold = 0.25
        self.last_frame = None
        self.last_annotated_frame = None
        self.last_detection_input = None
        self.last_detection_boxes = []
        self.last_detection_warnings = []
        self.frame_lock = threading.Lock()
        self.session_lock = threading.Lock()
        self.command_lock = threading.Lock()
        self.video_writer = None
        self.recording = False
        self.recording_path = None
        self.last_rc = {"lr": 0, "fb": 0, "ud": 0, "yaw": 0}
        self.last_frame_time = 0.0
        self.stream_quality = 0
        self.total_horizontal_cm = 0.0
        self.total_vertical_cm = 0.0
        self.current_altitude_cm = 0.0
        self.path_x_cm = 0.0
        self.path_y_cm = 0.0
        self.flight_path = [{"x": 0.0, "y": 0.0}]
        self.last_odom_time = time.time()
        self.session_started_at = datetime.now()
        self.events = []
        self.fire_screenshots = []
        self.detection_counts = {"person": 0, "fire": 0}
        self.last_detection_event = {"person": 0.0, "fire": 0.0}
        self.event_cooldown_seconds = 10.0
        self.last_command_time = time.time()
        self.battery_warned = False
        self.status = {
            "connected": False,
            "flying": False,
            "battery": None,
            "wifi_dbm": None,
            "wifi_source": "indisponivel",
            "stream_quality": 0,
            "vx": 0,
            "vy": 0,
            "vz": 0,
            "height": None,
            "temperature": None,
            "tof": None,
            "horizontal_distance": 0,
            "vertical_distance": 0,
            "session_altitude": 0,
            "recording": False,
            "detecting": True,
            "night_mode": False,
            "confidence_threshold": 60,
            "person_count": 0,
            "fire_count": 0,
            "events": [],
            "flight_path": [{"x": 0.0, "y": 0.0}],
            "message": "Servidor iniciado. Drone ainda nao conectado.",
        }

    def load_person_model(self):
        if self.person_model is None and YOLO is not None:
            model_path = PERSON_MODEL_PATH if PERSON_MODEL_PATH.exists() else "yolov8n.pt"
            self.person_model = YOLO(str(model_path))
        return self.person_model

    def load_fire_model(self):
        if self.fire_model is None and YOLO is not None:
            if not FIRE_MODEL_PATH.exists():
                return None
            self.fire_model = YOLO(str(FIRE_MODEL_PATH))
        return self.fire_model

    def connect(self, max_attempts=3, retry_delay_seconds=2.0):
        if Tello is None:
            self.set_message("Biblioteca djitellopy nao instalada.")
            return False

        with self.command_lock:
            if self.connected:
                return True

            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    if attempt > 1:
                        self.set_message(f"Tentando conectar no Tello (tentativa {attempt}/{max_attempts})...")

                    self.tello = Tello()
                    self.tello.connect()
                    self.tello.streamon()
                    self.frame_reader = self.tello.get_frame_read()
                    self.connected = True
                    self.streaming = True
                    self.status["connected"] = True
                    self.status["message"] = "Tello conectado e stream iniciado."
                    self.last_command_time = time.time()
                    self.start_workers()
                    return True
                except Exception as exc:
                    last_exc = exc
                    self.tello = None
                    if attempt < max_attempts:
                        time.sleep(retry_delay_seconds)

            self.connected = False
            self.status["connected"] = False
            self.set_message(
                f"Falha ao conectar no Tello apos {max_attempts} tentativas: {last_exc}. "
                "Verifique se o Wi-Fi do PC esta conectado a rede TELLO-XXXXXX."
            )
            return False

    def disconnect(self):
        with self.command_lock:
            self.streaming = False
            self.stop_recording()
            if self.tello is not None:
                try:
                    self.tello.send_rc_control(0, 0, 0, 0)
                    self.tello.streamoff()
                    self.tello.end()
                except Exception:
                    pass
            self.tello = None
            self.frame_reader = None
            self.connected = False
            self.status["connected"] = False
            self.status["flying"] = False
            self.set_message("Drone desconectado.")

    def start_workers(self):
        threading.Thread(target=self.video_loop, daemon=True).start()
        threading.Thread(target=self.detection_loop, daemon=True).start()
        threading.Thread(target=self.telemetry_loop, daemon=True).start()

    def set_message(self, message):
        self.status["message"] = message
        socketio.emit("status", self.status)

    def touch_command(self):
        """Marca que um comando vivo chegou do cliente (usado pelo watchdog de seguranca)."""
        self.last_command_time = time.time()

    def send_rc(self, lr=0, fb=0, ud=0, yaw=0):
        self.touch_command()
        lr, fb, ud, yaw = [int(np.clip(v, -100, 100)) for v in (lr, fb, ud, yaw)]
        self.last_rc = {"lr": lr, "fb": fb, "ud": ud, "yaw": yaw}
        if not self.connected or self.tello is None:
            return
        try:
            self.tello.send_rc_control(lr, fb, ud, yaw)
        except Exception as exc:
            self.set_message(f"Erro ao enviar controle RC: {exc}")

    def action(self, name):
        self.touch_command()

        if name == "photo":
            return self.take_photo()
        if name == "record":
            return self.toggle_recording()

        if not self.connected or self.tello is None:
            self.set_message("Conecte o Tello antes de executar comandos de voo.")
            return False

        try:
            if name == "takeoff":
                self.tello.takeoff()
                self.status["flying"] = True
                self.last_odom_time = time.time()
                self.path_x_cm = 0.0
                self.path_y_cm = 0.0
                self.flight_path = [{"x": 0.0, "y": 0.0}]
                self.status["flight_path"] = list(self.flight_path)
                self.set_message("Decolagem enviada.")
            elif name == "land":
                self.tello.land()
                self.mark_landed()
                self.set_message("Pouso enviado.")
            elif name == "emergency":
                self.tello.emergency()
                self.mark_landed()
                self.set_message("EMERGENCIA enviada.")
            else:
                self.set_message(f"Acao desconhecida: {name}")
                return False
            return True
        except Exception as exc:
            self.set_message(f"Erro ao executar {name}: {exc}")
            return False

    def auto_land(self, reason):
        """Pouso automatico disparado por seguranca (watchdog de comando ou bateria critica)."""
        if not self.status.get("flying") or not self.connected or self.tello is None:
            return
        self.set_message(reason)
        try:
            self.tello.land()
        except Exception as exc:
            self.set_message(f"{reason} | Erro ao pousar automaticamente: {exc}")
        finally:
            self.mark_landed()

    def mark_landed(self):
        """Ao pousar, a altura acumulada da sessao volta para zero."""
        self.status["flying"] = False
        self.current_altitude_cm = 0.0
        self.total_vertical_cm = 0.0
        self.status["height"] = 0
        self.status["session_altitude"] = 0

    def take_photo(self):
        with self.frame_lock:
            frame = None if self.last_annotated_frame is None else self.last_annotated_frame.copy()
        if frame is None:
            self.set_message("Nenhum frame disponivel para foto.")
            return False
        filename = PHOTO_DIR / f"foto_{datetime.now():%Y%m%d_%H%M%S}.jpg"
        cv2.imwrite(str(filename), frame)
        _enforce_media_limit(PHOTO_DIR, MAX_PHOTOS)
        self.set_message(f"Foto salva em {filename}")
        return True

    def toggle_recording(self):
        if self.recording:
            self.stop_recording()
            self.set_message("Gravacao finalizada.")
            return True
        return self.start_recording()

    def start_recording(self):
        with self.frame_lock:
            frame = None if self.last_annotated_frame is None else self.last_annotated_frame.copy()
        if frame is None:
            self.set_message("Aguarde um frame antes de gravar.")
            return False

        height, width = frame.shape[:2]
        filename = VIDEO_DIR / f"video_{datetime.now():%Y%m%d_%H%M%S}.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.video_writer = cv2.VideoWriter(str(filename), fourcc, 20.0, (width, height))
        self.recording = True
        self.recording_path = str(filename)
        self.status["recording"] = True
        self.set_message(f"Gravando em {filename}")
        return True

    def stop_recording(self):
        if self.video_writer is not None:
            self.video_writer.release()
        self.video_writer = None
        self.recording = False
        self.recording_path = None
        self.status["recording"] = False
        _enforce_media_limit(VIDEO_DIR, MAX_VIDEOS)

    def video_loop(self):
        """Le, processa e transmite os frames. Nunca espera a deteccao (thread separada) -
        so desenha por cima as ultimas caixas que ela ja tiver calculado, o que e uma
        operacao barata. Isso mantem o stream sempre liso, com deteccao ligada ou nao.
        """
        while self.streaming:
            try:
                raw = self.frame_reader.frame if self.frame_reader is not None else None
                if raw is None:
                    time.sleep(0.03)
                    continue

                frame = cv2.cvtColor(raw, cv2.COLOR_RGB2BGR)
                processed = self.apply_night_mode(frame) if self.night_mode else frame

                with self.frame_lock:
                    self.last_frame = frame.copy()
                    # Frame que a thread de deteccao vai processar na proxima passada dela.
                    self.last_detection_input = processed.copy()
                    boxes = list(self.last_detection_boxes) if self.detecting else []
                    warnings = list(self.last_detection_warnings) if self.detecting else []

                annotated = processed.copy()
                if boxes:
                    self.draw_boxes(annotated, boxes)
                if warnings:
                    self.draw_warnings(annotated, warnings)

                with self.frame_lock:
                    self.last_annotated_frame = annotated.copy()

                if self.recording and self.video_writer is not None:
                    self.video_writer.write(annotated)

                ok, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                if ok:
                    encoded = base64.b64encode(buffer).decode("ascii")
                    socketio.emit("video_frame", {"image": f"data:image/jpeg;base64,{encoded}"})

                self.update_stream_quality()
                socketio.sleep(0.02)
            except Exception as exc:
                self.set_message(f"Erro no loop de video: {exc}")
                socketio.sleep(0.2)

    def detection_loop(self):
        """Roda o YOLO numa thread separada do streaming de video.

        Sempre pega o frame mais recente disponivel (nunca uma fila acumulada) e atualiza
        a lista compartilhada de caixas quando termina - o video_loop so consome o
        resultado mais recente, sem nunca esperar o modelo rodar.
        """
        while self.streaming:
            if not self.detecting:
                time.sleep(0.1)
                continue

            with self.frame_lock:
                frame = None if self.last_detection_input is None else self.last_detection_input.copy()

            if frame is None:
                time.sleep(0.05)
                continue

            try:
                boxes, warnings = self.detect_objects(frame)
                with self.frame_lock:
                    self.last_detection_boxes = boxes
                    self.last_detection_warnings = warnings
            except Exception as exc:
                self.set_message(f"Erro na deteccao: {exc}")
                time.sleep(0.2)

    def apply_night_mode(self, frame):
        """Aumenta brilho/contraste para cenas escuras sem interromper o stream."""
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced_l = clahe.apply(l_channel)
        enhanced = cv2.merge((enhanced_l, a_channel, b_channel))
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        return cv2.convertScaleAbs(enhanced, alpha=1.18, beta=14)

    def detect_objects(self, frame):
        """Roda os modelos numa copia do frame (chamado pela detection_loop).

        Devolve (boxes, warnings): boxes e uma lista de dicts prontos pra serem desenhados
        pelo video_loop a qualquer momento depois, sem precisar rodar o modelo de novo.
        """
        if YOLO is None:
            return [], ["ultralytics nao instalado"]

        warnings = []

        person_boxes, warn = self.run_model(self.load_person_model(), frame, "Pessoa", (0, 255, 140), classes=[0])
        if warn:
            warnings.append(warn)

        fire_model = self.load_fire_model()
        fire_boxes, warn = self.run_model(fire_model, frame, "Fogo", (0, 0, 255), classes=FIRE_MODEL_CLASSES)
        if warn:
            warnings.append(warn)

        boxes = person_boxes + fire_boxes

        person_confs = [b["conf"] for b in person_boxes]
        fire_confs = [b["conf"] for b in fire_boxes]
        if person_confs or fire_confs:
            snapshot = frame.copy()
            self.draw_boxes(snapshot, boxes)
            if person_confs:
                self.register_detection("person", max(person_confs), snapshot)
            if fire_confs:
                self.register_detection("fire", max(fire_confs), snapshot)

        return boxes, warnings

    def run_model(self, model, frame, label, color, classes=None):
        """Roda um modelo YOLO e devolve so as caixas (nao desenha nada)."""
        if model is None:
            warning = "modelo de fogo ausente: rode setup_models.py" if label == "Fogo" else None
            return [], warning

        boxes = []
        results = model.predict(
            frame,
            imgsz=640,
            conf=self.confidence_threshold,
            iou=self.nms_iou_threshold,
            agnostic_nms=True,
            max_det=8,
            classes=classes,
            verbose=False,
        )
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                boxes.append(
                    {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "label": label, "color": color, "conf": conf}
                )
        return boxes, None

    @staticmethod
    def draw_boxes(frame, boxes):
        """Desenha uma lista de caixas ja calculadas - operacao barata, sem rodar modelo nenhum."""
        for box in boxes:
            x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
            color = box["color"]
            text = f"{box['label']} {box['conf'] * 100:.0f}%"
            text_width = max(112, len(text) * 12)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.rectangle(frame, (x1, max(0, y1 - 28)), (x1 + text_width, y1), color, -1)
            cv2.putText(frame, text, (x1 + 6, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (8, 12, 10), 2)

    @staticmethod
    def draw_warnings(frame, warnings):
        for i, text in enumerate(warnings):
            cv2.putText(frame, text, (20, 35 + i * 33), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 180, 255), 2)

    def register_detection(self, kind, confidence, frame):
        now = time.time()
        if now - self.last_detection_event[kind] < self.event_cooldown_seconds:
            return

        self.last_detection_event[kind] = now
        event_time = datetime.now()
        label = "Fogo" if kind == "fire" else "Pessoa"
        screenshot_path = None

        if kind == "fire":
            screenshot_path = PHOTO_DIR / f"fogo_{event_time:%Y%m%d_%H%M%S}.jpg"
            cv2.imwrite(str(screenshot_path), frame)
            self.fire_screenshots.append(str(screenshot_path))
            _enforce_media_limit(PHOTO_DIR, MAX_PHOTOS)

        event = {
            "time": event_time.strftime("%H:%M:%S"),
            "timestamp": event_time.isoformat(timespec="seconds"),
            "kind": kind,
            "label": label,
            "confidence": round(confidence * 100, 1),
            "screenshot": str(screenshot_path) if screenshot_path else "",
        }

        with self.session_lock:
            self.events.insert(0, event)
            self.events = self.events[:250]
            self.detection_counts[kind] += 1
            self.status["events"] = self.events[:30]
            self.status["person_count"] = self.detection_counts["person"]
            self.status["fire_count"] = self.detection_counts["fire"]

        socketio.emit("detection_event", event)
        socketio.emit("status", self.status)

    def update_stream_quality(self):
        now = time.time()
        if self.last_frame_time:
            dt = max(0.001, now - self.last_frame_time)
            fps = 1.0 / dt
            self.stream_quality = int(np.clip((fps / 25.0) * 100, 0, 100))
            self.status["stream_quality"] = self.stream_quality
        self.last_frame_time = now

    def telemetry_loop(self):
        while self.streaming:
            try:
                self.refresh_status()
                self.check_safety_failsafes()
                socketio.emit("status", self.status)
                socketio.sleep(0.5)
            except Exception as exc:
                self.set_message(f"Erro na telemetria: {exc}")
                socketio.sleep(1.0)

    def check_safety_failsafes(self):
        """Watchdog de comando + pouso automatico por bateria critica.

        So roda enquanto o status indica que o drone esta voando.
        """
        if not self.status.get("flying"):
            self.battery_warned = False
            return

        if time.time() - self.last_command_time > COMMAND_TIMEOUT_SECONDS:
            self.auto_land(
                f"Nenhum comando recebido por {COMMAND_TIMEOUT_SECONDS:.0f}s - pousando por seguranca (failsafe)."
            )
            return

        battery = self.status.get("battery")
        if battery is None:
            return

        if battery <= BATTERY_CRITICAL_PCT:
            self.auto_land(f"Bateria critica ({battery}%) - pousando automaticamente.")
        elif battery <= BATTERY_WARNING_PCT and not self.battery_warned:
            self.battery_warned = True
            self.set_message(f"Aviso: bateria em {battery}%. Pouse em breve.")

    def refresh_status(self):
        state = {}
        if self.connected and self.tello is not None:
            try:
                state = self.tello.get_current_state() or {}
            except Exception:
                state = {}

        vx = int(state.get("vgx", 0) or 0)
        vy = int(state.get("vgy", 0) or 0)
        vz = int(state.get("vgz", 0) or 0)
        raw_height = int(state.get("h", 0) or 0)
        if raw_height > 15 and not self.status.get("flying"):
            self.status["flying"] = True
        self.integrate_odometry(vx, vy, vz)
        if self.status.get("flying") and raw_height > self.current_altitude_cm:
            self.current_altitude_cm = float(raw_height)

        self.status.update(
            {
                "connected": self.connected,
                "battery": self.safe_tello_call("get_battery", state.get("bat")),
                "vx": vx,
                "vy": vy,
                "vz": vz,
                "height": raw_height,
                "temperature": state.get("templ"),
                "tof": state.get("tof"),
                "horizontal_distance": round(self.total_horizontal_cm, 1),
                "vertical_distance": round(self.total_vertical_cm, 1),
                "session_altitude": round(self.current_altitude_cm, 1),
                "recording": self.recording,
                "detecting": self.detecting,
                "night_mode": self.night_mode,
                "confidence_threshold": round(self.confidence_threshold * 100),
                "person_count": self.detection_counts["person"],
                "fire_count": self.detection_counts["fire"],
                "events": self.events[:30],
                "stream_quality": self.stream_quality,
                "flight_path": self.flight_path[-MAX_FLIGHT_PATH_POINTS:],
            }
        )

        dbm = get_windows_wifi_dbm()
        if dbm is None:
            self.status["wifi_dbm"] = estimate_dbm_from_quality(self.stream_quality)
            self.status["wifi_source"] = "estimativa_stream"
        else:
            self.status["wifi_dbm"] = dbm
            self.status["wifi_source"] = "windows_wifi"

    def safe_tello_call(self, method_name, fallback=None):
        if not self.connected or self.tello is None:
            return fallback
        try:
            method = getattr(self.tello, method_name)
            return method()
        except Exception:
            return fallback

    def integrate_odometry(self, vx, vy, vz):
        now = time.time()
        dt = now - self.last_odom_time
        self.last_odom_time = now
        if dt <= 0 or dt > 2:
            return
        self.total_horizontal_cm += math.sqrt(vx * vx + vy * vy) * dt
        self.total_vertical_cm += abs(vz) * dt
        if self.status.get("flying"):
            self.current_altitude_cm = max(0.0, self.current_altitude_cm + (vz * dt))
            self.update_flight_path(vx, vy, dt)

    def update_flight_path(self, vx, vy, dt):
        """Acumula uma posicao 2D aproximada (cm) a partir de vgx/vgy, pra desenhar uma
        trilha de voo no dashboard. E uma estimativa por odometria, igual a distancia
        total ja calculada - acumula deriva ao longo do tempo, nao e GPS.
        """
        self.path_x_cm += vx * dt
        self.path_y_cm += vy * dt

        last = self.flight_path[-1] if self.flight_path else None
        moved_enough = (
            last is None
            or abs(self.path_x_cm - last["x"]) > 2
            or abs(self.path_y_cm - last["y"]) > 2
        )
        if moved_enough:
            self.flight_path.append({"x": round(self.path_x_cm, 1), "y": round(self.path_y_cm, 1)})
            if len(self.flight_path) > MAX_FLIGHT_PATH_POINTS:
                self.flight_path = self.flight_path[-MAX_FLIGHT_PATH_POINTS:]

    def set_detection_enabled(self, enabled):
        self.detecting = bool(enabled)
        self.status["detecting"] = self.detecting
        self.set_message("Deteccao ativada." if self.detecting else "Deteccao pausada.")

    def set_confidence(self, value):
        self.confidence_threshold = float(np.clip(value, 0, 100)) / 100.0
        self.status["confidence_threshold"] = round(self.confidence_threshold * 100)
        self.set_message(f"Confianca minima ajustada para {self.status['confidence_threshold']}%.")

    def set_night_mode(self, enabled):
        self.night_mode = bool(enabled)
        self.status["night_mode"] = self.night_mode
        self.set_message("Modo noturno ativado." if self.night_mode else "Modo noturno desativado.")

    def csv_response(self):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["timestamp", "tipo", "confianca_percentual", "screenshot"])
        with self.session_lock:
            for event in reversed(self.events):
                writer.writerow([event["timestamp"], event["label"], event["confidence"], event["screenshot"]])
        return buffer.getvalue()

    def pdf_report(self):
        if canvas is None:
            raise RuntimeError("Instale reportlab para gerar PDF.")

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 2 * cm

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(2 * cm, y, "Relatorio da sessao DJI Tello")
        y -= 0.8 * cm
        pdf.setFont("Helvetica", 10)
        pdf.drawString(2 * cm, y, f"Inicio: {self.session_started_at:%d/%m/%Y %H:%M:%S}")
        y -= 0.5 * cm
        pdf.drawString(2 * cm, y, f"Gerado em: {datetime.now():%d/%m/%Y %H:%M:%S}")
        y -= 0.7 * cm
        pdf.drawString(2 * cm, y, f"Pessoas detectadas: {self.detection_counts['person']} | Focos de fogo: {self.detection_counts['fire']}")
        y -= 0.9 * cm

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(2 * cm, y, "Eventos")
        y -= 0.5 * cm
        pdf.setFont("Helvetica", 9)

        with self.session_lock:
            events = list(reversed(self.events))
            screenshots = list(self.fire_screenshots)

        for event in events:
            line = f"{event['time']} - {event['label']} detectado ({event['confidence']:.0f}%)"
            if y < 2 * cm:
                pdf.showPage()
                y = height - 2 * cm
                pdf.setFont("Helvetica", 9)
            pdf.drawString(2 * cm, y, line)
            y -= 0.42 * cm

        if screenshots:
            pdf.showPage()
            y = height - 2 * cm
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(2 * cm, y, "Screenshots de fogo")
            y -= 0.7 * cm
            for path in screenshots[:12]:
                if y < 6 * cm:
                    pdf.showPage()
                    y = height - 2 * cm
                if Path(path).exists():
                    pdf.drawImage(path, 2 * cm, y - 5 * cm, width=8 * cm, height=4.5 * cm, preserveAspectRatio=True, anchor="nw")
                    pdf.setFont("Helvetica", 8)
                    pdf.drawString(10.5 * cm, y - 0.5 * cm, Path(path).name)
                    y -= 5.3 * cm

        pdf.save()
        buffer.seek(0)
        return buffer


def get_windows_wifi_dbm():
    """Le o sinal Wi-Fi no Windows e converte qualidade (%) para dBm aproximado."""
    try:
        output = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"],
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=2,
        )
    except Exception:
        return None

    match = re.search(r"Signal\s*:\s*(\d+)%", output, re.IGNORECASE)
    if not match:
        match = re.search(r"Sinal\s*:\s*(\d+)%", output, re.IGNORECASE)
    if not match:
        return None

    quality = int(match.group(1))
    return int((quality / 2) - 100)


def estimate_dbm_from_quality(quality):
    if quality is None:
        return None
    return int((int(quality) / 2) - 100)
