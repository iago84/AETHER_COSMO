import base64
import csv
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def latest_snapshot() -> Path | None:
    root = Path(__file__).resolve().parents[3]
    out_dir = root / "aetherlab" / "data" / "outputs"
    if not out_dir.exists():
        return None
    pngs = sorted(out_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return pngs[0] if pngs else None


class RoiLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.setScaledContents(True)
        self._dragging = False
        self._x0 = 0
        self._y0 = 0
        self._x1 = 0
        self._y1 = 0
        self.on_roi_change = None

    def mousePressEvent(self, e: QMouseEvent):
        if e.buttons() & e.Button.LeftButton:
            self._dragging = True
            self._x0 = int(e.position().x())
            self._y0 = int(e.position().y())
            self._x1 = self._x0
            self._y1 = self._y0
            self.update()

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._dragging:
            self._x1 = int(e.position().x())
            self._y1 = int(e.position().y())
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent):
        if self._dragging:
            self._dragging = False
            x0 = min(self._x0, self._x1)
            y0 = min(self._y0, self._y1)
            w = abs(self._x1 - self._x0)
            h = abs(self._y1 - self._y0)
            if self.on_roi_change:
                self.on_roi_change(x0, y0, w, h)
            self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._dragging or (self._x0 != self._x1 and self._y0 != self._y1):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(255, 0, 0), 2)
            p.setPen(pen)
            x0 = min(self._x0, self._x1)
            y0 = min(self._y0, self._y1)
            w = abs(self._x1 - self._x0)
            h = abs(self._y1 - self._y0)
            p.drawRect(x0, y0, w, h)
            p.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AETHERLAB")
        self.resize(1024, 720)
        self.base_url = QLineEdit("http://127.0.0.1:8000")
        self.project_cb = QComboBox()
        self.experiment_cb = QComboBox()
        btn_projects_refresh = QPushButton("Refrescar proyectos")
        btn_projects_new = QPushButton("Nuevo proyecto")
        btn_experiments_refresh = QPushButton("Refrescar experimentos")
        btn_experiments_new = QPushButton("Nuevo experimento")
        self.label = RoiLabel()
        self.label.setText("Sin snapshot")
        self.label.setMinimumSize(640, 480)
        btn_load = QPushButton("Cargar último snapshot")
        self.btn_sim = QPushButton("Simular (API)")
        btn_series = QPushButton("Cargar serie (NPZ)")
        btn_spec = QPushButton("Espectro (API)")
        btn_ac = QPushButton("Autocorr (API)")
        btn_refresh = QPushButton("Actualizar estado")
        btn_abort = QPushButton("Abortar")
        btn_retry = QPushButton("Reintentar")
        btn_download = QPushButton("Descargar snapshot")
        btn_download_series = QPushButton("Descargar serie")
        btn_download_field = QPushButton("Descargar campo")
        btn_export_csv = QPushButton("Exportar métricas CSV")
        btn_export_html = QPushButton("Exportar reporte HTML")
        btn_export_mp4 = QPushButton("Exportar MP4")
        btn_roi_spec = QPushButton("Espectro ROI (API)")
        btn_roi_ac = QPushButton("Autocorr ROI (API)")
        btn_roi_csv = QPushButton("Export ROI CSV")
        btn_play = QPushButton("Reproducir serie")
        btn_stop = QPushButton("Parar")
        self.frame_idx = QSpinBox()
        self.frame_idx.setRange(0, 100000)
        self.frame_idx.setValue(0)
        btn_load.clicked.connect(self.load_last)
        self.btn_sim.clicked.connect(self.simulate_demo)
        btn_series.clicked.connect(self.load_series_plot)
        btn_spec.clicked.connect(self.load_spectrum_api)
        btn_ac.clicked.connect(self.load_autocorr_api)
        btn_refresh.clicked.connect(self.refresh_run_state)
        btn_abort.clicked.connect(self.abort_run)
        btn_retry.clicked.connect(self.retry_run)
        btn_download.clicked.connect(self.download_snapshot)
        btn_download_series.clicked.connect(self.download_series)
        btn_download_field.clicked.connect(self.download_field)
        btn_export_csv.clicked.connect(self.export_series_metrics_csv)
        btn_export_html.clicked.connect(self.export_report_html)
        btn_export_mp4.clicked.connect(self.export_mp4)
        btn_roi_spec.clicked.connect(self.load_spectrum_roi_api)
        btn_roi_ac.clicked.connect(self.load_autocorr_roi_api)
        btn_roi_csv.clicked.connect(self.export_roi_csv)
        btn_play.clicked.connect(self.play_series)
        btn_stop.clicked.connect(self.stop_series)
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.advance_frame)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self.refresh_run_state)
        self.series_frames = None
        self.run_id = QSpinBox()
        self.run_id.setRange(1, 1000000)
        self.run_id.setValue(1)
        self.status_label = QLabel("status: -")
        self.source = QComboBox()
        self.source.addItems(["gaussian_pulse", "periodic", "stochastic", "top_hat", "lorentzian"])
        self.boundary = QComboBox()
        self.boundary.addItems(["periodic", "fixed", "absorbing"])
        self.steps = QSpinBox()
        self.steps.setRange(1, 10000)
        self.steps.setValue(60)
        self.nx = QSpinBox()
        self.nx.setRange(8, 2048)
        self.nx.setValue(128)
        self.ny = QSpinBox()
        self.ny.setRange(8, 2048)
        self.ny.setValue(128)
        self.dt = QDoubleSpinBox()
        self.dt.setDecimals(4)
        self.dt.setSingleStep(0.01)
        self.dt.setRange(0.0001, 1.0)
        self.dt.setValue(0.05)
        self.lam = QDoubleSpinBox()
        self.lam.setRange(0.0, 10.0)
        self.lam.setValue(0.5)
        self.diff = QDoubleSpinBox()
        self.diff.setRange(0.0, 10.0)
        self.diff.setValue(0.2)
        self.noise = QDoubleSpinBox()
        self.noise.setRange(0.0, 10.0)
        self.noise.setValue(0.0)
        self.seed_auto = QCheckBox("Seed auto")
        self.seed_auto.setChecked(True)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_147_483_647)
        self.seed.setValue(42)
        self.sigma = QDoubleSpinBox()
        self.sigma.setRange(0.1, 100.0)
        self.sigma.setValue(8.0)
        self.duration = QSpinBox()
        self.duration.setRange(1, 1000000)
        self.duration.setValue(20)
        self.radius = QDoubleSpinBox()
        self.radius.setRange(0.1, 100.0)
        self.radius.setValue(8.0)
        self.gamma = QDoubleSpinBox()
        self.gamma.setRange(0.1, 100.0)
        self.gamma.setValue(8.0)
        self.amp = QDoubleSpinBox()
        self.amp.setRange(0.0, 10.0)
        self.amp.setValue(1.0)
        self.freq = QDoubleSpinBox()
        self.freq.setRange(0.0, 10.0)
        self.freq.setValue(1.0)
        self.cx = QSpinBox()
        self.cy = QSpinBox()
        self.cx.setRange(0, 4096)
        self.cy.setRange(0, 4096)
        self.cx.setValue(64)
        self.cy.setValue(64)
        self.async_run = QCheckBox("Asíncrono")
        self.auto_refresh = QCheckBox("Auto refrescar")
        self.auto_refresh.setChecked(True)
        self.save_series = QCheckBox("Guardar serie")
        self.series_stride = QSpinBox()
        self.series_stride.setRange(1, 1000)
        self.series_stride.setValue(10)
        self.crop = QSpinBox()
        self.crop.setRange(8, 512)
        self.crop.setValue(96)
        self.spec_log = QCheckBox("Espectro en log")
        self.roi_x0 = QSpinBox()
        self.roi_y0 = QSpinBox()
        self.roi_w = QSpinBox()
        self.roi_h = QSpinBox()
        self.roi_x0.setRange(0, 2048)
        self.roi_y0.setRange(0, 2048)
        self.roi_w.setRange(1, 2048)
        self.roi_h.setRange(1, 2048)
        self.roi_x0.valueChanged.connect(self.update_roi_dynamic)
        self.roi_y0.valueChanged.connect(self.update_roi_dynamic)
        self.roi_w.valueChanged.connect(self.update_roi_dynamic)
        self.roi_h.valueChanged.connect(self.update_roi_dynamic)
        self.preset_cb = QComboBox()
        self.preset_cb.addItems(["Custom", "Estable rápido", "Alta difusión", "Con ruido"])
        self.preset_cb.currentIndexChanged.connect(self.apply_sim_preset)
        self.validation_label = QLabel("validación: -")
        self.nx.valueChanged.connect(self.update_sim_ranges)
        self.ny.valueChanged.connect(self.update_sim_ranges)
        for w in (self.dt, self.lam, self.diff, self.noise, self.cx, self.cy):
            w.valueChanged.connect(self.update_validation_ui)
        self.source.currentIndexChanged.connect(self.update_validation_ui)
        self.boundary.currentIndexChanged.connect(self.update_validation_ui)
        self.seed_auto.stateChanged.connect(self.update_validation_ui)
        self.auto_refresh.stateChanged.connect(self.on_auto_refresh_toggle)
        left = QVBoxLayout()
        left.addWidget(QLabel("API base"))
        left.addWidget(self.base_url)
        rowp = QHBoxLayout()
        rowp.addWidget(QLabel("Proyecto"))
        rowp.addWidget(self.project_cb)
        left.addLayout(rowp)
        rowp2 = QHBoxLayout()
        rowp2.addWidget(btn_projects_refresh)
        rowp2.addWidget(btn_projects_new)
        left.addLayout(rowp2)
        rowe = QHBoxLayout()
        rowe.addWidget(QLabel("Experimento"))
        rowe.addWidget(self.experiment_cb)
        left.addLayout(rowe)
        rowe2 = QHBoxLayout()
        rowe2.addWidget(btn_experiments_refresh)
        rowe2.addWidget(btn_experiments_new)
        left.addLayout(rowe2)
        left.addWidget(QLabel("Parámetros de simulación"))
        sp = QHBoxLayout()
        sp.addWidget(QLabel("Preset"))
        sp.addWidget(self.preset_cb)
        left.addLayout(sp)
        s0 = QHBoxLayout()
        s0.addWidget(QLabel("nx"))
        s0.addWidget(self.nx)
        s0.addWidget(QLabel("ny"))
        s0.addWidget(self.ny)
        left.addLayout(s0)
        s1 = QHBoxLayout()
        s1.addWidget(QLabel("Fuente"))
        s1.addWidget(self.source)
        s1.addWidget(QLabel("Boundary"))
        s1.addWidget(self.boundary)
        left.addLayout(s1)
        s2 = QHBoxLayout()
        s2.addWidget(QLabel("steps"))
        s2.addWidget(self.steps)
        s2.addWidget(QLabel("dt"))
        s2.addWidget(self.dt)
        left.addLayout(s2)
        s2b = QHBoxLayout()
        s2b.addWidget(QLabel("lam"))
        s2b.addWidget(self.lam)
        s2b.addWidget(QLabel("diff"))
        s2b.addWidget(self.diff)
        s2b.addWidget(QLabel("noise"))
        s2b.addWidget(self.noise)
        left.addLayout(s2b)
        s2c = QHBoxLayout()
        s2c.addWidget(QLabel("cx"))
        s2c.addWidget(self.cx)
        s2c.addWidget(QLabel("cy"))
        s2c.addWidget(self.cy)
        s2c.addWidget(QLabel("dur"))
        s2c.addWidget(self.duration)
        left.addLayout(s2c)
        s2d = QHBoxLayout()
        s2d.addWidget(self.seed_auto)
        s2d.addWidget(QLabel("seed"))
        s2d.addWidget(self.seed)
        left.addLayout(s2d)
        s3 = QHBoxLayout()
        s3.addWidget(QLabel("amp"))
        s3.addWidget(self.amp)
        s3.addWidget(QLabel("sigma"))
        s3.addWidget(self.sigma)
        left.addLayout(s3)
        s4 = QHBoxLayout()
        s4.addWidget(QLabel("radius"))
        s4.addWidget(self.radius)
        s4.addWidget(QLabel("gamma"))
        s4.addWidget(self.gamma)
        left.addLayout(s4)
        s5 = QHBoxLayout()
        s5.addWidget(QLabel("freq"))
        s5.addWidget(self.freq)
        left.addLayout(s5)
        s6 = QHBoxLayout()
        s6.addWidget(self.save_series)
        s6.addWidget(QLabel("stride"))
        s6.addWidget(self.series_stride)
        s6.addWidget(self.async_run)
        s6.addWidget(self.auto_refresh)
        left.addLayout(s6)
        sb = QHBoxLayout()
        sb.addWidget(self.btn_sim)
        sb.addWidget(btn_load)
        left.addLayout(sb)
        left.addWidget(self.validation_label)
        self.export_kind = QComboBox()
        self.export_kind.addItems(
            [
                "Reporte HTML",
                "Métricas CSV",
                "Snapshot PNG",
                "Snapshot SVG",
                "Snapshot PDF",
                "Serie NPZ",
                "Campo NPY",
                "ROI CSV",
                "MP4",
            ]
        )
        btn_export = QPushButton("Exportar…")
        btn_export.clicked.connect(self.export_unified)
        er = QHBoxLayout()
        er.addWidget(self.export_kind)
        er.addWidget(btn_export)
        left.addLayout(er)
        left.addStretch(1)
        left_w = QWidget()
        left_w.setLayout(left)

        right = QVBoxLayout()
        right.addWidget(self.label)
        self.tabs = QTabWidget()
        # Energy
        self.fig = Figure(figsize=(5, 2.5), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        w1 = QWidget()
        l1 = QVBoxLayout()
        l1.addWidget(self.canvas)
        w1.setLayout(l1)
        self.tabs.addTab(w1, "Energía")
        # Spectrum
        self.fig2 = Figure(figsize=(5, 2.5), dpi=100)
        self.canvas2 = FigureCanvas(self.fig2)
        w2 = QWidget()
        l2 = QVBoxLayout()
        l2.addWidget(self.canvas2)
        w2.setLayout(l2)
        self.tabs.addTab(w2, "Espectro")
        # Autocorr
        self.fig3 = Figure(figsize=(5, 2.5), dpi=100)
        self.canvas3 = FigureCanvas(self.fig3)
        w3 = QWidget()
        l3 = QVBoxLayout()
        l3.addWidget(self.canvas3)
        w3.setLayout(l3)
        self.tabs.addTab(w3, "Autocorr")
        self.data_tab = QWidget()
        self.ai_tab = QWidget()
        self.compare_tab = QWidget()
        self.reports_tab = QWidget()
        self.config_tab = QWidget()
        self.tabs.addTab(self.data_tab, "Datos")
        self.tabs.addTab(self.ai_tab, "IA")
        self.tabs.addTab(self.compare_tab, "Comparación")
        self.tabs.addTab(self.reports_tab, "Reportes")
        self.tabs.addTab(self.config_tab, "Configuración")
        controls2 = QHBoxLayout()
        controls2.addWidget(QLabel("run_id"))
        controls2.addWidget(self.run_id)
        controls2.addWidget(self.status_label)
        controls2.addWidget(btn_refresh)
        controls2.addWidget(btn_abort)
        controls2.addWidget(btn_retry)
        controls3 = QHBoxLayout()
        controls3.addWidget(btn_series)
        controls3.addWidget(btn_spec)
        controls3.addWidget(self.spec_log)
        controls3.addWidget(btn_ac)
        controls3.addWidget(QLabel("crop"))
        controls3.addWidget(self.crop)
        controls3.addWidget(QLabel("ROI x0"))
        controls3.addWidget(self.roi_x0)
        controls3.addWidget(QLabel("y0"))
        controls3.addWidget(self.roi_y0)
        controls3.addWidget(QLabel("w"))
        controls3.addWidget(self.roi_w)
        controls3.addWidget(QLabel("h"))
        controls3.addWidget(self.roi_h)
        controls3.addWidget(btn_roi_spec)
        controls3.addWidget(btn_roi_ac)
        controls3.addWidget(QLabel("frame"))
        controls3.addWidget(self.frame_idx)
        controls3.addWidget(btn_play)
        controls3.addWidget(btn_stop)
        controls3.addWidget(btn_roi_csv)
        right.addLayout(controls2)
        right.addLayout(controls3)
        right.addWidget(self.tabs)
        right_w = QWidget()
        right_w.setLayout(right)

        main = QHBoxLayout()
        main.addWidget(left_w, 1)
        main.addWidget(right_w, 4)
        c = QWidget()
        c.setLayout(main)
        self.setCentralWidget(c)
        def _on_roi_change(x0, y0, w, h):
            self.roi_x0.setValue(x0)
            self.roi_y0.setValue(y0)
            self.roi_w.setValue(max(1, w))
            self.roi_h.setValue(max(1, h))
        self.label.on_roi_change = _on_roi_change
        btn_projects_refresh.clicked.connect(self.refresh_projects)
        btn_projects_new.clicked.connect(self.create_project_ui)
        btn_experiments_refresh.clicked.connect(self.refresh_experiments)
        btn_experiments_new.clicked.connect(self.create_experiment_ui)
        self.project_cb.currentIndexChanged.connect(self.refresh_experiments)
        self.init_data_tab()
        self.init_ai_tab()
        self.init_compare_tab()
        self.init_reports_tab()
        self.init_config_tab()
        self.refresh_projects()
        self.load_last()
        self.update_sim_ranges()
        self.update_validation_ui()
        self.on_auto_refresh_toggle()

    def update_sim_ranges(self):
        nx = int(self.nx.value())
        ny = int(self.ny.value())
        self.cx.setRange(0, max(0, nx - 1))
        self.cy.setRange(0, max(0, ny - 1))
        self.cx.setValue(min(int(self.cx.value()), max(0, nx - 1)))
        self.cy.setValue(min(int(self.cy.value()), max(0, ny - 1)))
        self.update_validation_ui()

    def validate_sim_params(self) -> tuple[bool, str]:
        dt = float(self.dt.value())
        lam = float(self.lam.value())
        diff = float(self.diff.value())
        noise = float(self.noise.value())
        nx = int(self.nx.value())
        ny = int(self.ny.value())
        cx = int(self.cx.value())
        cy = int(self.cy.value())
        if dt * diff > 1.0:
            return False, "inestable: dt*diff > 1.0"
        if dt * lam > 1.0:
            return False, "inestable: dt*lam > 1.0"
        if noise > 0.0 and dt * noise > 1.0:
            return False, "inestable: dt*noise > 1.0"
        if cx >= nx or cy >= ny:
            return False, "fuente fuera de límites"
        return True, "ok"

    def update_validation_ui(self):
        ok, msg = self.validate_sim_params()
        self.validation_label.setText(f"validación: {msg}")
        self.btn_sim.setEnabled(bool(ok))
        self.seed.setEnabled(not self.seed_auto.isChecked())

    def on_auto_refresh_toggle(self):
        if self.auto_refresh.isChecked():
            self.status_timer.start()
        else:
            self.status_timer.stop()

    def apply_sim_preset(self):
        name = self.preset_cb.currentText()
        if name == "Estable rápido":
            self.nx.setValue(128)
            self.ny.setValue(128)
            self.steps.setValue(80)
            self.dt.setValue(0.05)
            self.lam.setValue(0.5)
            self.diff.setValue(0.2)
            self.noise.setValue(0.0)
            self.source.setCurrentText("gaussian_pulse")
            self.boundary.setCurrentText("periodic")
            self.sigma.setValue(8.0)
            self.duration.setValue(20)
            self.amp.setValue(1.0)
        elif name == "Alta difusión":
            self.nx.setValue(128)
            self.ny.setValue(128)
            self.steps.setValue(120)
            self.dt.setValue(0.02)
            self.lam.setValue(0.2)
            self.diff.setValue(0.8)
            self.noise.setValue(0.0)
            self.source.setCurrentText("gaussian_pulse")
            self.boundary.setCurrentText("absorbing")
            self.sigma.setValue(10.0)
            self.duration.setValue(30)
            self.amp.setValue(1.0)
        elif name == "Con ruido":
            self.nx.setValue(128)
            self.ny.setValue(128)
            self.steps.setValue(120)
            self.dt.setValue(0.03)
            self.lam.setValue(0.4)
            self.diff.setValue(0.3)
            self.noise.setValue(0.2)
            self.source.setCurrentText("stochastic")
            self.boundary.setCurrentText("periodic")
            self.sigma.setValue(8.0)
            self.duration.setValue(20)
            self.amp.setValue(0.8)
        self.cx.setValue(int(self.nx.value()) // 2)
        self.cy.setValue(int(self.ny.value()) // 2)
        self.update_sim_ranges()

    def api_base(self) -> str:
        return self.base_url.text().strip().rstrip("/")

    def http_get(self, path: str, timeout: int = 15) -> bytes:
        url = self.api_base() + path
        return urllib.request.urlopen(url, timeout=timeout).read()

    def http_get_text(self, path: str, timeout: int = 15) -> str:
        return self.http_get(path, timeout=timeout).decode()

    def http_post_json(self, path: str, payload: dict, timeout: int = 15) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.api_base() + path,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())

    def http_post_empty(self, path: str, timeout: int = 15) -> dict:
        req = urllib.request.Request(self.api_base() + path, data=b"", method="POST")
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())

    def current_project_id(self) -> int | None:
        v = self.project_cb.currentData()
        return int(v) if v is not None else None

    def current_experiment_id(self) -> int | None:
        v = self.experiment_cb.currentData()
        return int(v) if v is not None else None

    def refresh_projects(self):
        try:
            rows = json.loads(self.http_get_text("/projects", timeout=10))
            self.project_cb.blockSignals(True)
            self.project_cb.clear()
            for r in rows:
                self.project_cb.addItem(f"{r['id']}: {r['name']}", r["id"])
            self.project_cb.blockSignals(False)
            self.refresh_experiments()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def refresh_experiments(self):
        try:
            pid = self.current_project_id()
            if pid is None:
                self.experiment_cb.clear()
                return
            rows = json.loads(self.http_get_text(f"/experiments?project_id={pid}", timeout=10))
            self.experiment_cb.clear()
            for r in rows:
                self.experiment_cb.addItem(f"{r['id']}: {r['name']}", r["id"])
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def create_project_ui(self):
        name, ok = QInputDialog.getText(self, "Nuevo proyecto", "Nombre del proyecto")
        if not ok or not name.strip():
            return
        desc, ok2 = QInputDialog.getText(self, "Nuevo proyecto", "Descripción (opcional)")
        if not ok2:
            desc = ""
        try:
            _ = self.http_post_json(
                "/projects",
                {"name": name.strip(), "description": desc.strip() or None},
                timeout=15,
            )
            self.refresh_projects()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def create_experiment_ui(self):
        pid = self.current_project_id()
        if pid is None:
            QMessageBox.information(self, "Experimentos", "Selecciona o crea un proyecto primero")
            return
        name, ok = QInputDialog.getText(self, "Nuevo experimento", "Nombre del experimento")
        if not ok or not name.strip():
            return
        try:
            _ = self.http_post_json("/experiments", {"project_id": pid, "name": name.strip()}, timeout=15)
            self.refresh_experiments()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def export_unified(self):
        k = self.export_kind.currentText()
        if k == "Reporte HTML":
            self.export_report_html()
            return
        if k == "Métricas CSV":
            self.export_series_metrics_csv()
            return
        if k == "Snapshot PNG":
            self.download_snapshot()
            return
        if k == "Snapshot SVG":
            self.download_snapshot_svg()
            return
        if k == "Snapshot PDF":
            self.download_snapshot_pdf()
            return
        if k == "Serie NPZ":
            self.download_series()
            return
        if k == "Campo NPY":
            self.download_field()
            return
        if k == "ROI CSV":
            self.export_roi_csv()
            return
        if k == "MP4":
            self.export_mp4()
            return

    def init_data_tab(self):
        self.data_ds_cb = QComboBox()
        self.data_norm_cb = QComboBox()
        self.data_norm_cb.addItems(["zscore", "minmax", "robust", "none"])
        self.data_qc = QCheckBox("QC")
        self.data_qc.setChecked(True)
        self.data_out = QTextEdit()
        self.data_out.setReadOnly(True)
        btn_ds_refresh = QPushButton("Refrescar datasets")
        btn_ds_meta = QPushButton("Meta")
        btn_ds_etl = QPushButton("ETL")
        btn_ds_artifacts = QPushButton("Artefactos")
        btn_ds_refresh.clicked.connect(self.data_refresh_datasets)
        btn_ds_meta.clicked.connect(self.data_show_meta)
        btn_ds_etl.clicked.connect(self.data_run_etl)
        btn_ds_artifacts.clicked.connect(self.data_list_artifacts)
        top = QHBoxLayout()
        top.addWidget(self.data_ds_cb)
        top.addWidget(btn_ds_refresh)
        top2 = QHBoxLayout()
        top2.addWidget(QLabel("Normalize"))
        top2.addWidget(self.data_norm_cb)
        top2.addWidget(self.data_qc)
        top2.addWidget(btn_ds_meta)
        top2.addWidget(btn_ds_etl)
        top2.addWidget(btn_ds_artifacts)
        lay = QVBoxLayout()
        lay.addLayout(top)
        lay.addLayout(top2)
        lay.addWidget(self.data_out)
        self.data_tab.setLayout(lay)
        self.data_refresh_datasets()

    def data_refresh_datasets(self):
        try:
            rows = json.loads(self.http_get_text("/datasets", timeout=10))
            self.data_ds_cb.clear()
            for d in rows:
                self.data_ds_cb.addItem(f"{d['id']}: {d['name']}", d["id"])
        except Exception as e:
            self.data_out.setPlainText(str(e))

    def data_current_dataset_id(self) -> int | None:
        v = self.data_ds_cb.currentData()
        return int(v) if v is not None else None

    def data_show_meta(self):
        did = self.data_current_dataset_id()
        if did is None:
            return
        try:
            o = json.loads(self.http_get_text(f"/datasets/{did}/meta", timeout=20))
            self.data_out.setPlainText(json.dumps(o, ensure_ascii=False, indent=2))
        except Exception as e:
            self.data_out.setPlainText(str(e))

    def data_run_etl(self):
        did = self.data_current_dataset_id()
        if did is None:
            return
        try:
            o = self.http_post_json(
                "/etl/dataset",
                {"dataset_id": did, "normalize": self.data_norm_cb.currentText(), "qc": self.data_qc.isChecked()},
                timeout=40,
            )
            self.data_out.setPlainText(json.dumps(o, ensure_ascii=False, indent=2))
        except Exception as e:
            self.data_out.setPlainText(str(e))

    def data_list_artifacts(self):
        did = self.data_current_dataset_id()
        if did is None:
            return
        try:
            o = json.loads(self.http_get_text(f"/artifacts?dataset_id={did}", timeout=20))
            self.data_out.setPlainText(json.dumps(o, ensure_ascii=False, indent=2))
        except Exception as e:
            self.data_out.setPlainText(str(e))

    def init_ai_tab(self):
        self.ai_method = QComboBox()
        self.ai_method.addItems(["isoforest", "mean_dist"])
        self.ai_out = QTextEdit()
        self.ai_out.setReadOnly(True)
        self.ai_img = QLabel()
        self.ai_img.setMinimumHeight(240)
        self.ai_img.setScaledContents(True)
        btn_ai_run_run = QPushButton("IA sobre run")
        btn_ai_run_series = QPushButton("IA sobre serie")
        btn_ai_run_ds = QPushButton("IA sobre dataset")
        btn_ai_pca_series = QPushButton("PCA serie")
        btn_ai_models = QPushButton("ModelRuns")
        btn_ai_run_run.clicked.connect(self.ai_run_on_run)
        btn_ai_run_series.clicked.connect(self.ai_run_on_run_series)
        btn_ai_run_ds.clicked.connect(self.ai_run_on_dataset)
        btn_ai_pca_series.clicked.connect(self.ai_pca_on_run_series)
        btn_ai_models.clicked.connect(self.ai_list_models)
        row = QHBoxLayout()
        row.addWidget(QLabel("Método"))
        row.addWidget(self.ai_method)
        row.addWidget(btn_ai_run_run)
        row.addWidget(btn_ai_run_series)
        row.addWidget(btn_ai_run_ds)
        row.addWidget(btn_ai_pca_series)
        row.addWidget(btn_ai_models)
        lay = QVBoxLayout()
        lay.addLayout(row)
        lay.addWidget(self.ai_img)
        lay.addWidget(self.ai_out)
        self.ai_tab.setLayout(lay)

    def ai_pca_on_run_series(self):
        try:
            run_id = int(self.run_id.value())
            o = json.loads(self.http_get_text(f"/figures/{run_id}/series-metrics", timeout=40))
            series = o.get("series") or []
            X = [[m["energy"], m["mean"], m["variance"], m["spatial_corr"]] for m in series]
            if not X:
                self.ai_out.setPlainText("No hay serie de métricas para PCA")
                return
            out = self.http_post_json("/ai/pca-plot", {"X": X, "n_components": 2}, timeout=60)
            img = out.get("image") or ""
            if img.startswith("data:image/png;base64,"):
                raw = base64.b64decode(img.split(",", 1)[1])
                pix = QPixmap()
                pix.loadFromData(raw)
                self.ai_img.setPixmap(pix)
            self.ai_out.setPlainText(json.dumps(out, ensure_ascii=False, indent=2))
        except Exception as e:
            self.ai_out.setPlainText(str(e))

    def ai_run_on_run(self):
        try:
            run_id = int(self.run_id.value())
            o = self.http_post_json(
                "/ai/run-on-run",
                {"run_id": run_id, "method": self.ai_method.currentText()},
                timeout=40,
            )
            self.ai_out.setPlainText(json.dumps(o, ensure_ascii=False, indent=2))
        except Exception as e:
            self.ai_out.setPlainText(str(e))

    def ai_run_on_run_series(self):
        win, ok = QInputDialog.getInt(self, "IA sobre serie", "ventana", 1, 1, 1000, 1)
        if not ok:
            return
        try:
            run_id = int(self.run_id.value())
            o = self.http_post_json(
                "/ai/run-on-run-series",
                {"run_id": run_id, "method": self.ai_method.currentText(), "window": win},
                timeout=60,
            )
            self.ai_out.setPlainText(json.dumps(o, ensure_ascii=False, indent=2))
        except Exception as e:
            self.ai_out.setPlainText(str(e))

    def ai_run_on_dataset(self):
        did, ok = QInputDialog.getInt(self, "IA sobre dataset", "dataset_id", 1, 1, 1000000, 1)
        if not ok:
            return
        try:
            o = self.http_post_json(
                "/ai/run-on-dataset",
                {"dataset_id": did, "method": self.ai_method.currentText()},
                timeout=60,
            )
            self.ai_out.setPlainText(json.dumps(o, ensure_ascii=False, indent=2))
        except Exception as e:
            self.ai_out.setPlainText(str(e))

    def ai_list_models(self):
        try:
            eid = self.current_experiment_id()
            if eid is None:
                self.ai_out.setPlainText("Selecciona un experimento")
                return
            o = json.loads(self.http_get_text(f"/models?experiment_id={eid}", timeout=20))
            self.ai_out.setPlainText(json.dumps(o, ensure_ascii=False, indent=2))
        except Exception as e:
            self.ai_out.setPlainText(str(e))

    def init_compare_tab(self):
        self.cmp_run_a = QSpinBox()
        self.cmp_run_a.setRange(1, 1000000)
        self.cmp_run_b = QSpinBox()
        self.cmp_run_b.setRange(1, 1000000)
        self.cmp_ds_id = QSpinBox()
        self.cmp_ds_id.setRange(1, 1000000)
        self.cmp_out = QTextEdit()
        self.cmp_out.setReadOnly(True)
        self.cmp_img = QLabel()
        self.cmp_img.setMinimumHeight(240)
        self.cmp_img.setScaledContents(True)
        btn_rr = QPushButton("Run↔Run")
        btn_rd = QPushButton("Run↔Dataset")
        btn_rr_fig = QPushButton("Figura Run↔Run")
        btn_rd_fig = QPushButton("Figura Run↔Dataset")
        btn_rr.clicked.connect(self.compare_run_run)
        btn_rd.clicked.connect(self.compare_run_dataset)
        btn_rr_fig.clicked.connect(self.compare_run_run_fig)
        btn_rd_fig.clicked.connect(self.compare_run_dataset_fig)
        row = QHBoxLayout()
        row.addWidget(QLabel("run_a"))
        row.addWidget(self.cmp_run_a)
        row.addWidget(QLabel("run_b"))
        row.addWidget(self.cmp_run_b)
        row.addWidget(btn_rr)
        row.addWidget(btn_rr_fig)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("dataset_id"))
        row2.addWidget(self.cmp_ds_id)
        row2.addWidget(btn_rd)
        row2.addWidget(btn_rd_fig)
        lay = QVBoxLayout()
        lay.addLayout(row)
        lay.addLayout(row2)
        lay.addWidget(self.cmp_img)
        lay.addWidget(self.cmp_out)
        self.compare_tab.setLayout(lay)

    def compare_run_run(self):
        try:
            a = int(self.cmp_run_a.value())
            b = int(self.cmp_run_b.value())
            o = json.loads(self.http_get_text(f"/compare/run-run?run_a={a}&run_b={b}", timeout=30))
            self.cmp_out.setPlainText(json.dumps(o, ensure_ascii=False, indent=2))
        except Exception as e:
            self.cmp_out.setPlainText(str(e))

    def compare_run_dataset(self):
        try:
            run_id = int(self.run_id.value())
            did = int(self.cmp_ds_id.value())
            o = json.loads(self.http_get_text(f"/compare/run-dataset?run_id={run_id}&dataset_id={did}", timeout=30))
            self.cmp_out.setPlainText(json.dumps(o, ensure_ascii=False, indent=2))
        except Exception as e:
            self.cmp_out.setPlainText(str(e))

    def compare_run_run_fig(self):
        try:
            a = int(self.cmp_run_a.value())
            b = int(self.cmp_run_b.value())
            png = self.http_get(f"/compare/run-run/figure.png?run_a={a}&run_b={b}", timeout=40)
            pix = QPixmap()
            pix.loadFromData(png)
            self.cmp_img.setPixmap(pix)
        except Exception as e:
            self.cmp_out.setPlainText(str(e))

    def compare_run_dataset_fig(self):
        try:
            run_id = int(self.run_id.value())
            did = int(self.cmp_ds_id.value())
            png = self.http_get(
                f"/compare/run-dataset/figure.png?run_id={run_id}&dataset_id={did}",
                timeout=40,
            )
            pix = QPixmap()
            pix.loadFromData(png)
            self.cmp_img.setPixmap(pix)
        except Exception as e:
            self.cmp_out.setPlainText(str(e))

    def init_reports_tab(self):
        self.rep_run_id = QSpinBox()
        self.rep_run_id.setRange(1, 1000000)
        self.rep_exp_id = QSpinBox()
        self.rep_exp_id.setRange(1, 1000000)
        self.rep_html = QTextEdit()
        self.rep_html.setReadOnly(True)
        btn_run = QPushButton("Cargar Run HTML")
        btn_exp = QPushButton("Cargar Exp HTML")
        btn_save = QPushButton("Guardar HTML…")
        btn_run.clicked.connect(self.reports_load_run)
        btn_exp.clicked.connect(self.reports_load_experiment)
        btn_save.clicked.connect(self.reports_save_html)
        row = QHBoxLayout()
        row.addWidget(QLabel("run_id"))
        row.addWidget(self.rep_run_id)
        row.addWidget(btn_run)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("exp_id"))
        row2.addWidget(self.rep_exp_id)
        row2.addWidget(btn_exp)
        row2.addWidget(btn_save)
        lay = QVBoxLayout()
        lay.addLayout(row)
        lay.addLayout(row2)
        lay.addWidget(self.rep_html)
        self.reports_tab.setLayout(lay)
        self.rep_run_id.setValue(int(self.run_id.value()))

    def reports_load_run(self):
        rid = int(self.rep_run_id.value())
        crop = int(self.crop.value())
        try:
            html = self.http_get_text(f"/reports/run/{rid}/html?crop={crop}", timeout=40)
            self.rep_html.setPlainText(html)
        except Exception as e:
            self.rep_html.setPlainText(str(e))

    def reports_load_experiment(self):
        eid = int(self.rep_exp_id.value())
        try:
            html = self.http_get_text(f"/reports/experiment/{eid}/html", timeout=40)
            self.rep_html.setPlainText(html)
        except Exception as e:
            self.rep_html.setPlainText(str(e))

    def reports_save_html(self):
        html = self.rep_html.toPlainText()
        if not html.strip():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar HTML", "report.html", "HTML (*.html)")
        if not path:
            return
        Path(path).write_text(html, encoding="utf-8")

    def init_config_tab(self):
        self.cfg_out = QTextEdit()
        self.cfg_out.setReadOnly(True)
        btn = QPushButton("Estado")
        btn.clicked.connect(self.config_status)
        lay = QVBoxLayout()
        lay.addWidget(btn)
        lay.addWidget(self.cfg_out)
        self.config_tab.setLayout(lay)

    def config_status(self):
        try:
            o = json.loads(self.http_get_text("/health", timeout=5))
            self.cfg_out.setPlainText(json.dumps(o, ensure_ascii=False, indent=2))
        except Exception as e:
            self.cfg_out.setPlainText(str(e))

    def load_last(self):
        p = latest_snapshot()
        if p is None:
            self.label.setText("No se encontró snapshot")
            return
        pix = QPixmap(str(p))
        if pix.isNull():
            self.label.setText("No se pudo abrir el snapshot")
        else:
            self.label.setPixmap(pix)

    def simulate_demo(self):
        try:
            ok, msg = self.validate_sim_params()
            if not ok:
                QMessageBox.warning(self, "Validación", msg)
                return
            eid = self.current_experiment_id()
            if eid is None:
                QMessageBox.information(self, "Simulación", "Selecciona o crea un experimento primero")
                return
            source = self.source.currentText()
            seed = None if self.seed_auto.isChecked() else int(self.seed.value())
            payload = {
                "experiment_id": eid,
                "nx": int(self.nx.value()),
                "ny": int(self.ny.value()),
                "steps": int(self.steps.value()),
                "dt": float(self.dt.value()),
                "lam": float(self.lam.value()),
                "diff": float(self.diff.value()),
                "noise": float(self.noise.value()),
                "seed": seed,
                "boundary": self.boundary.currentText(),
                "source_kind": source,
                "cx": int(self.cx.value()),
                "cy": int(self.cy.value()),
                "sigma": float(self.sigma.value()),
                "duration": int(self.duration.value()),
                "radius": float(self.radius.value()),
                "gamma": float(self.gamma.value()),
                "amplitude": float(self.amp.value()),
                "frequency": float(self.freq.value()) if source == "periodic" else None,
                "save_series": bool(self.save_series.isChecked()),
                "series_stride": int(self.series_stride.value()),
            }
            if self.async_run.isChecked():
                o = self.http_post_json("/simulate/async", payload, timeout=25)
            else:
                o = self.http_post_json("/simulate/simple", payload, timeout=25)
            if "run_id" in o:
                self.run_id.setValue(int(o["run_id"]))
                self.rep_run_id.setValue(int(o["run_id"]))
            if not self.async_run.isChecked():
                self.load_last()
            if self.auto_refresh.isChecked():
                self.status_timer.start()
            QMessageBox.information(self, "Simulación", f"Ejecutada: {json.dumps(o, ensure_ascii=False)}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def load_series_plot(self):
        try:
            run_id = int(self.run_id.value())
            resp = self.http_get(f"/figures/{run_id}/series", timeout=25)
            bio = io.BytesIO(resp)
            z = np.load(bio)
            frames = z["frames"]
            self.series_frames = frames
            self.frame_idx.setRange(0, int(frames.shape[0]) - 1)
            idx = int(self.frame_idx.value())
            idx = max(0, min(idx, int(frames.shape[0]) - 1))
            energy = np.mean(frames**2, axis=(1, 2))
            self.fig.clear()
            ax = self.fig.add_subplot(111)
            ax.plot(np.arange(len(energy)), energy, label="Energía")
            ax.axvline(idx, color="red", linestyle="--", label="frame actual")
            ax.set_xlabel("frame")
            ax.set_ylabel("energía")
            ax.grid(True)
            ax.legend()
            self.canvas.draw_idle()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def load_spectrum_api(self):
        try:
            run_id = int(self.run_id.value())
            o = json.loads(self.http_get_text(f"/figures/{run_id}/spectrum", timeout=15))
            k = np.array(o["k"])
            ps = np.array(o["ps"])
            self.fig2.clear()
            ax = self.fig2.add_subplot(111)
            if self.spec_log.isChecked():
                ax.semilogy(k, ps, label="Espectro radial")
            else:
                ax.plot(k, ps, label="Espectro radial")
            ax.set_xlabel("k")
            ax.set_ylabel("potencia")
            ax.grid(True)
            ax.legend()
            self.canvas2.draw_idle()
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def update_roi_dynamic(self):
        try:
            run_id = int(self.run_id.value())
            x0 = int(self.roi_x0.value())
            y0 = int(self.roi_y0.value())
            w = int(self.roi_w.value())
            h = int(self.roi_h.value())
            # Spectrum with ROI
            o_all = json.loads(self.http_get_text(f"/figures/{run_id}/spectrum", timeout=15))
            o_roi = json.loads(
                self.http_get_text(f"/figures/{run_id}/spectrum-roi?x0={x0}&y0={y0}&w={w}&h={h}", timeout=15)
            )
            k_all = np.array(o_all["k"])
            ps_all = np.array(o_all["ps"])
            k_roi = np.array(o_roi["k"])
            ps_roi = np.array(o_roi["ps"])
            self.fig2.clear()
            ax2 = self.fig2.add_subplot(111)
            if self.spec_log.isChecked():
                ax2.semilogy(k_all, ps_all, label="Espectro global")
                ax2.semilogy(k_roi, ps_roi, label="Espectro ROI")
            else:
                ax2.plot(k_all, ps_all, label="Espectro global")
                ax2.plot(k_roi, ps_roi, label="Espectro ROI")
            ax2.set_xlabel("k")
            ax2.set_ylabel("potencia")
            ax2.grid(True)
            ax2.legend()
            self.canvas2.draw_idle()
            # Autocorr with ROI
            o_ac = json.loads(
                self.http_get_text(f"/figures/{run_id}/autocorr-roi?x0={x0}&y0={y0}&w={w}&h={h}", timeout=15)
            )
            ac = np.array(o_ac["autocorr"])
            self.fig3.clear()
            ax3 = self.fig3.add_subplot(111)
            im = ax3.imshow(ac, cmap="viridis", origin="lower")
            self.fig3.colorbar(im, ax=ax3, fraction=0.046, pad=0.04)
            self.canvas3.draw_idle()
        except Exception:
            pass

    def load_autocorr_api(self):
        try:
            run_id = int(self.run_id.value())
            crop = int(self.crop.value())
            o = json.loads(self.http_get_text(f"/figures/{run_id}/autocorr?crop={crop}", timeout=20))
            ac = np.array(o["autocorr"], dtype=np.float32)
            self.fig3.clear()
            ax = self.fig3.add_subplot(111)
            im = ax.imshow(ac, cmap="viridis", origin="lower")
            ax.set_title("Autocorrelación 2D (recorte)")
            self.fig3.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            self.canvas3.draw_idle()
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def load_spectrum_roi_api(self):
        try:
            run_id = int(self.run_id.value())
            x0 = int(self.roi_x0.value())
            y0 = int(self.roi_y0.value())
            w = int(self.roi_w.value())
            h = int(self.roi_h.value())
            path = f"/figures/{run_id}/spectrum-roi?x0={x0}&y0={y0}&w={w}&h={h}"
            o = json.loads(self.http_get_text(path, timeout=15))
            k = np.array(o["k"])
            ps = np.array(o["ps"])
            self.fig2.clear()
            ax = self.fig2.add_subplot(111)
            if self.spec_log.isChecked():
                ax.semilogy(k, ps, label="Espectro ROI")
            else:
                ax.plot(k, ps, label="Espectro ROI")
            ax.set_xlabel("k")
            ax.set_ylabel("potencia")
            ax.grid(True)
            ax.legend()
            self.canvas2.draw_idle()
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def load_autocorr_roi_api(self):
        try:
            run_id = int(self.run_id.value())
            x0 = int(self.roi_x0.value())
            y0 = int(self.roi_y0.value())
            w = int(self.roi_w.value())
            h = int(self.roi_h.value())
            path = f"/figures/{run_id}/autocorr-roi?x0={x0}&y0={y0}&w={w}&h={h}"
            o = json.loads(self.http_get_text(path, timeout=15))
            ac = np.array(o["autocorr"], dtype=np.float32)
            self.fig3.clear()
            ax = self.fig3.add_subplot(111)
            im = ax.imshow(ac, cmap="viridis", origin="lower")
            ax.set_title("Autocorrelación ROI")
            self.fig3.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            self.canvas3.draw_idle()
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def export_roi_csv(self):
        try:
            run_id = int(self.run_id.value())
            x0 = int(self.roi_x0.value())
            y0 = int(self.roi_y0.value())
            w = int(self.roi_w.value())
            h = int(self.roi_h.value())
            path = f"/figures/{run_id}/spectrum-roi?x0={x0}&y0={y0}&w={w}&h={h}"
            o = json.loads(self.http_get_text(path, timeout=15))
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar ROI espectro CSV",
                f"roi_spec_{run_id}.csv",
                "CSV (*.csv)",
            )
            if not path:
                return
            with open(path, "w", newline="", encoding="utf-8") as f:
                wcsv = csv.writer(f)
                ks = o.get("k", [])
                ps = o.get("ps", [])
                wcsv.writerow(["k", "ps"])
                for i in range(min(len(ks), len(ps))):
                    wcsv.writerow([ks[i], ps[i]])
            QMessageBox.information(self, "CSV", f"Guardado en {path}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def export_mp4(self):
        try:
            if self.series_frames is None:
                QMessageBox.information(self, "MP4", "Carga primero una serie NPZ")
                return
            path, _ = QFileDialog.getSaveFileName(self, "Guardar MP4", "series.mp4", "MP4 (*.mp4)")
            if not path:
                return
            import matplotlib.animation as animation
            fig = Figure(figsize=(5, 4), dpi=120)
            ax = fig.add_subplot(111)
            im = ax.imshow(self.series_frames[0], cmap="viridis", origin="lower")
            ax.set_title("Serie de frames")
            def update(i):
                im.set_data(self.series_frames[i])
                return [im]
            ani = animation.FuncAnimation(fig, update, frames=int(self.series_frames.shape[0]), interval=100, blit=True)
            try:
                writer = animation.FFMpegWriter(fps=10)
                buf = io.BytesIO()
                fig.canvas.print_png(buf)
                ani.save(path, writer=writer)
                QMessageBox.information(self, "MP4", f"Guardado en {path}")
            except Exception as e:
                QMessageBox.warning(self, "MP4", f"No se pudo exportar MP4: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
    def refresh_run_state(self):
        try:
            run_id = int(self.run_id.value())
            o = json.loads(self.http_get_text(f"/runs/{run_id}", timeout=15))
            st = o.get("status", "-")
            backend = o.get("backend", "-")
            job_id = o.get("job_id", None)
            extra = f"{backend}" + (f":{job_id}" if job_id else "")
            self.status_label.setText(f"status: {st} ({extra})")
            if self.auto_refresh.isChecked() and st in ("finished", "failed", "cancelled", "cleaned"):
                self.status_timer.stop()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def abort_run(self):
        try:
            run_id = int(self.run_id.value())
            o = self.http_post_empty(f"/runs/{run_id}/abort", timeout=20)
            self.status_label.setText(f"status: {o.get('status','-')}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def retry_run(self):
        try:
            run_id = int(self.run_id.value())
            o = self.http_post_empty(f"/runs/{run_id}/retry", timeout=20)
            self.status_label.setText(f"status: {o.get('status','-')}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def download_snapshot(self):
        try:
            run_id = int(self.run_id.value())
            path, _ = QFileDialog.getSaveFileName(self, "Guardar snapshot", f"snapshot_{run_id}.png", "PNG (*.png)")
            if not path:
                return
            data = self.http_get(f"/figures/{run_id}/snapshot", timeout=25)
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Descarga", f"Guardado en {path}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def download_snapshot_svg(self):
        try:
            run_id = int(self.run_id.value())
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar snapshot (SVG)",
                f"snapshot_{run_id}.svg",
                "SVG (*.svg)",
            )
            if not path:
                return
            data = self.http_get(f"/figures/{run_id}/snapshot.svg", timeout=40)
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Descarga", f"Guardado en {path}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def download_snapshot_pdf(self):
        try:
            run_id = int(self.run_id.value())
            path, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar snapshot (PDF)",
                f"snapshot_{run_id}.pdf",
                "PDF (*.pdf)",
            )
            if not path:
                return
            data = self.http_get(f"/figures/{run_id}/snapshot.pdf", timeout=40)
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Descarga", f"Guardado en {path}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def download_series(self):
        try:
            run_id = int(self.run_id.value())
            path, _ = QFileDialog.getSaveFileName(self, "Guardar serie", f"series_{run_id}.npz", "NPZ (*.npz)")
            if not path:
                return
            data = self.http_get(f"/figures/{run_id}/series", timeout=30)
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Descarga", f"Guardado en {path}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def download_field(self):
        try:
            run_id = int(self.run_id.value())
            path, _ = QFileDialog.getSaveFileName(self, "Guardar campo", f"field_{run_id}.npy", "NPY (*.npy)")
            if not path:
                return
            data = self.http_get(f"/figures/{run_id}/field", timeout=30)
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Descarga", f"Guardado en {path}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def export_series_metrics_csv(self):
        try:
            run_id = int(self.run_id.value())
            path, _ = QFileDialog.getSaveFileName(self, "Guardar métricas CSV", f"metrics_{run_id}.csv", "CSV (*.csv)")
            if not path:
                return
            data = self.http_get(f"/figures/{run_id}/series-metrics.csv", timeout=40)
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "CSV", f"Guardado en {path}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def export_report_html(self):
        try:
            run_id = int(self.run_id.value())
            crop = int(self.crop.value())
            path, _ = QFileDialog.getSaveFileName(
                self, "Guardar reporte HTML", f"report_run_{run_id}.html", "HTML (*.html)"
            )
            if not path:
                return
            html = self.http_get_text(f"/reports/run/{run_id}/html?crop={crop}", timeout=40)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            QMessageBox.information(self, "Reporte", f"Reporte guardado en {path}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def play_series(self):
        if self.series_frames is None:
            QMessageBox.information(self, "Serie", "Carga primero una serie NPZ")
            return
        self.timer.start()

    def stop_series(self):
        self.timer.stop()

    def advance_frame(self):
        if self.series_frames is None:
            self.timer.stop()
            return
        idx = int(self.frame_idx.value()) + 1
        if idx >= int(self.series_frames.shape[0]):
            idx = 0
        self.frame_idx.setValue(idx)
        energy = np.mean(self.series_frames**2, axis=(1, 2))
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.plot(np.arange(len(energy)), energy, label="Energía")
        ax.axvline(idx, color="red", linestyle="--", label="frame actual")
        ax.set_xlabel("frame")
        ax.set_ylabel("energía")
        ax.grid(True)
        ax.legend()
        self.canvas.draw_idle()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
