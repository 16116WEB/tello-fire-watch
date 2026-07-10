"""Extensoes Flask compartilhadas entre app.py e dashboard.py.

Mantidas num modulo separado para evitar import circular: dashboard.py
precisa emitir eventos socketio, e app.py precisa do TelloDashboard.
"""

from flask_socketio import SocketIO

socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")
