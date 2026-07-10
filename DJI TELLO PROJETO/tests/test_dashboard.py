import time

from dashboard import TelloDashboard, estimate_dbm_from_quality


def test_estimate_dbm_from_quality_none():
    assert estimate_dbm_from_quality(None) is None


def test_estimate_dbm_from_quality_bounds():
    assert estimate_dbm_from_quality(0) == -100
    assert estimate_dbm_from_quality(100) == -50


def test_integrate_odometry_accumulates_distance():
    dash = TelloDashboard()
    dash.last_odom_time = time.time() - 1.0  # simula 1s desde a ultima leitura
    dash.integrate_odometry(vx=30, vy=40, vz=0)
    # 30/40 cm/s por ~1s -> hipotenusa (3-4-5) ~ 50cm
    assert 45 <= dash.total_horizontal_cm <= 55


def test_integrate_odometry_ignores_stale_or_negative_dt():
    dash = TelloDashboard()
    dash.last_odom_time = time.time() + 5  # dt negativo, leitura invalida
    before = dash.total_horizontal_cm
    dash.integrate_odometry(10, 10, 10)
    assert dash.total_horizontal_cm == before


def test_csv_response_includes_header_and_events():
    dash = TelloDashboard()
    dash.events = [
        {
            "time": "12:00:00",
            "timestamp": "2026-06-30T12:00:00",
            "kind": "person",
            "label": "Pessoa",
            "confidence": 87.5,
            "screenshot": "",
        }
    ]
    csv_text = dash.csv_response()
    assert "timestamp,tipo,confianca_percentual,screenshot" in csv_text
    assert "Pessoa" in csv_text
    assert "87.5" in csv_text


class _FakeTello:
    def __init__(self):
        self.landed = False

    def land(self):
        self.landed = True


def test_command_timeout_triggers_auto_land():
    dash = TelloDashboard()
    dash.connected = True
    dash.tello = _FakeTello()
    dash.status["flying"] = True
    dash.status["battery"] = 80
    dash.last_command_time = time.time() - 999  # muito tempo sem comando do navegador

    dash.check_safety_failsafes()

    assert dash.tello.landed is True
    assert dash.status["flying"] is False


def test_battery_critical_triggers_auto_land():
    dash = TelloDashboard()
    dash.connected = True
    dash.tello = _FakeTello()
    dash.status["flying"] = True
    dash.status["battery"] = 5  # abaixo do limiar critico padrao (10%)
    dash.last_command_time = time.time()  # comando recente, nao deve ser o watchdog de tempo

    dash.check_safety_failsafes()

    assert dash.tello.landed is True
    assert dash.status["flying"] is False


def test_battery_ok_and_recent_command_does_not_land():
    dash = TelloDashboard()
    dash.connected = True
    dash.tello = _FakeTello()
    dash.status["flying"] = True
    dash.status["battery"] = 80
    dash.last_command_time = time.time()

    dash.check_safety_failsafes()

    assert dash.tello.landed is False
    assert dash.status["flying"] is True


def test_safety_failsafes_skipped_when_not_flying():
    dash = TelloDashboard()
    dash.connected = True
    dash.tello = _FakeTello()
    dash.status["flying"] = False
    dash.status["battery"] = 1
    dash.last_command_time = time.time() - 999

    dash.check_safety_failsafes()

    assert dash.tello.landed is False


def test_flight_path_grows_while_flying():
    dash = TelloDashboard()
    dash.status["flying"] = True
    dash.last_odom_time = time.time() - 1.0

    dash.integrate_odometry(vx=30, vy=0, vz=0)

    assert len(dash.flight_path) >= 2
    last = dash.flight_path[-1]
    assert last["x"] > 20  # andou ~30cm em x num segundo


def test_flight_path_resets_on_takeoff():
    dash = TelloDashboard()
    dash.connected = True
    dash.tello = _FakeTello()
    dash.tello.takeoff = lambda: None
    dash.status["flying"] = True
    dash.last_odom_time = time.time() - 1.0
    dash.integrate_odometry(vx=30, vy=0, vz=0)
    assert len(dash.flight_path) >= 2

    dash.action("takeoff")

    assert dash.flight_path == [{"x": 0.0, "y": 0.0}]
    assert dash.path_x_cm == 0.0
    assert dash.path_y_cm == 0.0


def test_detect_objects_returns_warning_when_yolo_missing(monkeypatch):
    import dashboard as dashboard_module

    monkeypatch.setattr(dashboard_module, "YOLO", None)
    dash = TelloDashboard()
    boxes, warnings = dash.detect_objects(object())

    assert boxes == []
    assert warnings == ["ultralytics nao instalado"]
