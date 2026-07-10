from pathlib import Path
from urllib.request import urlretrieve


BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)

MODELS = {
    "person_yolov8n.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
    "fire_yolov8n.pt": "https://huggingface.co/rabahdev/fire-smoke-yolov8n/resolve/main/best.pt",
}


def download_model(filename, url):
    target = MODELS_DIR / filename
    if target.exists() and target.stat().st_size > 1024 * 1024:
        print(f"{filename} ja existe em {target}")
        return

    print(f"Baixando {filename}...")
    urlretrieve(url, target)
    print(f"Salvo em {target}")


if __name__ == "__main__":
    for name, source in MODELS.items():
        download_model(name, source)
    print("Modelos prontos para uso offline.")
