import sys
from pathlib import Path

import pytest

# Garante que o diretorio raiz do projeto esta no path para "import dashboard".
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(autouse=True)
def _silence_socketio_emit(monkeypatch):
    """Evita que os testes precisem de uma app Flask real rodando.

    dashboard.py emite eventos via socketio.emit a cada mudanca de estado;
    aqui isso vira um no-op para os testes ficarem isolados.
    """
    import dashboard as dashboard_module

    monkeypatch.setattr(dashboard_module.socketio, "emit", lambda *args, **kwargs: None)
