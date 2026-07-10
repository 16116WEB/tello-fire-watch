from datetime import datetime

from flask import Flask, Response, render_template, send_file
from flask_socketio import emit

from config import CERT_PATH, DEBUG, KEY_PATH, PORT, SECRET_KEY
from dashboard import TelloDashboard
from extensions import socketio


def create_app():
    flask_app = Flask(__name__)
    flask_app.config["SECRET_KEY"] = SECRET_KEY
    flask_app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    flask_app.config["TEMPLATES_AUTO_RELOAD"] = True
    socketio.init_app(flask_app)
    return flask_app


app = create_app()
dashboard = TelloDashboard()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/vr")
def vr():
    return render_template("vr.html")


@app.route("/export/events.csv")
def export_events_csv():
    filename = f"eventos_tello_{datetime.now():%Y%m%d_%H%M%S}.csv"
    return Response(
        dashboard.csv_response(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/export/report.pdf")
def export_report_pdf():
    try:
        report = dashboard.pdf_report()
    except RuntimeError as exc:
        return Response(str(exc), status=500)

    filename = f"relatorio_tello_{datetime.now():%Y%m%d_%H%M%S}.pdf"
    return send_file(report, mimetype="application/pdf", as_attachment=True, download_name=filename)


@socketio.on("connect")
def on_connect():
    emit("status", dashboard.status)


@socketio.on("connect_drone")
def on_connect_drone():
    ok = dashboard.connect()
    emit("status", dashboard.status)
    return {"ok": ok}


@socketio.on("disconnect_drone")
def on_disconnect_drone():
    dashboard.disconnect()
    emit("status", dashboard.status)
    return {"ok": True}


@socketio.on("rc")
def on_rc(data):
    dashboard.send_rc(
        data.get("lr", 0),
        data.get("fb", 0),
        data.get("ud", 0),
        data.get("yaw", 0),
    )


@socketio.on("action")
def on_action(data):
    ok = dashboard.action(data.get("name", ""))
    emit("status", dashboard.status)
    return {"ok": ok}


@socketio.on("detection")
def on_detection(data):
    dashboard.set_detection_enabled(data.get("enabled", True))


@socketio.on("confidence")
def on_confidence(data):
    dashboard.set_confidence(data.get("value", 35))


@socketio.on("night_mode")
def on_night_mode(data):
    dashboard.set_night_mode(data.get("enabled", False))


if __name__ == "__main__":
    ssl_context = None
    if CERT_PATH.exists() and KEY_PATH.exists():
        ssl_context = (str(CERT_PATH), str(KEY_PATH))
        print(f"HTTPS habilitado com certificado em {CERT_PATH}")
    else:
        print(
            "Nenhum certificado encontrado - rodando em HTTP. "
            "O modo VR (/vr) precisa de HTTPS: rode 'python generate_cert.py' primeiro."
        )

    socketio.run(
        app,
        host="0.0.0.0",
        port=PORT,
        debug=DEBUG,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
        ssl_context=ssl_context,
    )
