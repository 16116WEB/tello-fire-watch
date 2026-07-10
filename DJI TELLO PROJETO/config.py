import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


BASE_DIR = Path(__file__).resolve().parent
MEDIA_DIR = BASE_DIR / "media"
PHOTO_DIR = MEDIA_DIR / "photos"
VIDEO_DIR = MEDIA_DIR / "videos"
MODELS_DIR = BASE_DIR / "models"
PERSON_MODEL_PATH = MODELS_DIR / "person_yolov8n.pt"
FIRE_MODEL_PATH = MODELS_DIR / "fire_yolov8n.pt"
FIRE_MODEL_CLASSES = [1]
CERT_DIR = BASE_DIR / "certs"
CERT_PATH = CERT_DIR / "server.crt"
KEY_PATH = CERT_DIR / "server.key"

PHOTO_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)


# --- Servidor ---
SECRET_KEY = os.environ.get("TELLO_SECRET_KEY", "tello-dashboard-local-dev")
PORT = int(os.environ.get("PORT", "5000"))
DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"


# --- Seguranca de voo ---
# Se nenhum comando (rc ou acao) chegar do navegador por esse tempo enquanto o
# drone esta voando, ele pousa sozinho. Fica abaixo do failsafe interno do
# Tello (~15s sem comando) para garantir um pouso controlado em vez do
# failsafe bruto do proprio drone.
COMMAND_TIMEOUT_SECONDS = float(os.environ.get("TELLO_COMMAND_TIMEOUT", "8"))

# Abaixo desse percentual de bateria, so avisa. Abaixo do critico, pousa sozinho.
BATTERY_WARNING_PCT = int(os.environ.get("TELLO_BATTERY_WARNING_PCT", "20"))
BATTERY_CRITICAL_PCT = int(os.environ.get("TELLO_BATTERY_CRITICAL_PCT", "10"))


# --- Limite de espaco em disco ---
# Mantem so os N arquivos mais recentes em media/photos e media/videos,
# apagando os mais antigos automaticamente.
MAX_PHOTOS = int(os.environ.get("TELLO_MAX_PHOTOS", "300"))
MAX_VIDEOS = int(os.environ.get("TELLO_MAX_VIDEOS", "50"))
