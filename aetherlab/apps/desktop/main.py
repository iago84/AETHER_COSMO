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
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
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
        self.label = RoiLabel()
        self.label.setText("Sin snapshot")
        self.label.setMinimumSize(640, 480)
        btn_load = QPushButton("Cargar último snapshot")
        btn_sim = QPushButton("Simular (API)")
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
        btn_sim.clicked.connect(self.simulate_demo)
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
        self.dt = QDoubleSpinBox()
        self.dt.setDecimals(4)
        self.dt.setSingleStep(0.01)
        self.dt.setRange(0.0001, 1.0)
        self.dt.setValue(0.05)
        self.sigma = QDoubleSpinBox()
        self.sigma.setRange(0.1, 100.0)
        self.sigma.setValue(8.0)
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
        layout = QVBoxLayout()
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Fuente"))
        controls.addWidget(self.source)
        controls.addWidget(QLabel("Boundary"))
        controls.addWidget(self.boundary)
        controls.addWidget(QLabel("steps"))
        controls.addWidget(self.steps)
        controls.addWidget(QLabel("dt"))
        controls.addWidget(self.dt)
        controls.addWidget(QLabel("amp"))
        controls.addWidget(self.amp)
        controls.addWidget(QLabel("sigma"))
        controls.addWidget(self.sigma)
        controls.addWidget(QLabel("radius"))
        controls.addWidget(self.radius)
        controls.addWidget(QLabel("gamma"))
        controls.addWidget(self.gamma)
        controls.addWidget(QLabel("freq"))
        controls.addWidget(self.freq)
        controls.addWidget(self.save_series)
        controls.addWidget(QLabel("stride"))
        controls.addWidget(self.series_stride)
        layout.addLayout(controls)
        buttons = QHBoxLayout()
        buttons.addWidget(btn_load)
        buttons.addWidget(btn_sim)
        layout.addLayout(buttons)
        layout.addWidget(self.label)
        # Tabs with plots
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
        controls3.addWidget(btn_download)
        controls3.addWidget(btn_download_series)
        controls3.addWidget(btn_download_field)
        controls3.addWidget(btn_export_csv)
        controls3.addWidget(btn_export_html)
        controls3.addWidget(btn_roi_csv)
        controls3.addWidget(btn_export_mp4)
        layout.addLayout(controls2)
        layout.addLayout(controls3)
        layout.addWidget(self.tabs)
        c = QWidget()
        c.setLayout(layout)
        self.setCentralWidget(c)
        def _on_roi_change(x0, y0, w, h):
            # Actualizar spinboxes de ROI
            self.roi_x0.setValue(x0)
            self.roi_y0.setValue(y0)
            self.roi_w.setValue(max(1, w))
            self.roi_h.setValue(max(1, h))
        self.label.on_roi_change = _on_roi_change
        self.load_last()

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
            base = "http://127.0.0.1:8000"
            payload = {
                "experiment_id": 1,
                "steps": int(self.steps.value()),
                "dt": float(self.dt.value()),
                "boundary": self.boundary.currentText(),
                "source_kind": self.source.currentText(),
                "sigma": float(self.sigma.value()),
                "radius": float(self.radius.value()),
                "gamma": float(self.gamma.value()),
                "amplitude": float(self.amp.value()),
                "frequency": float(self.freq.value()),
                "save_series": bool(self.save_series.isChecked()),
                "series_stride": int(self.series_stride.value()),
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                base + "/simulate/simple", data=data, headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=10).read().decode()
            self.load_last()
            QMessageBox.information(self, "Simulación", f"Ejecutada: {resp}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def load_series_plot(self):
        try:
            run_id = int(self.run_id.value())
            base = "http://127.0.0.1:8000"
            resp = urllib.request.urlopen(f"{base}/figures/{run_id}/series", timeout=15).read()
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
            base = "http://127.0.0.1:8000"
            data = urllib.request.urlopen(f"{base}/figures/{run_id}/spectrum", timeout=10).read().decode()
            o = json.loads(data)
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
            base = "http://127.0.0.1:8000"
            x0 = int(self.roi_x0.value())
            y0 = int(self.roi_y0.value())
            w = int(self.roi_w.value())
            h = int(self.roi_h.value())
            # Spectrum with ROI
            data_all = urllib.request.urlopen(f"{base}/figures/{run_id}/spectrum", timeout=10).read().decode()
            o_all = json.loads(data_all)
            url_roi = f"{base}/figures/{run_id}/spectrum-roi?x0={x0}&y0={y0}&w={w}&h={h}"
            data_roi = urllib.request.urlopen(url_roi, timeout=10).read().decode()
            o_roi = json.loads(data_roi)
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
            url_ac = f"{base}/figures/{run_id}/autocorr-roi?x0={x0}&y0={y0}&w={w}&h={h}"
            data_ac = urllib.request.urlopen(url_ac, timeout=10).read().decode()
            o_ac = json.loads(data_ac)
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
            base = "http://127.0.0.1:8000"
            crop = int(self.crop.value())
            data = urllib.request.urlopen(f"{base}/figures/{run_id}/autocorr?crop={crop}", timeout=10).read().decode()
            o = json.loads(data)
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
            base = "http://127.0.0.1:8000"
            x0 = int(self.roi_x0.value())
            y0 = int(self.roi_y0.value())
            w = int(self.roi_w.value())
            h = int(self.roi_h.value())
            url = f"{base}/figures/{run_id}/spectrum-roi?x0={x0}&y0={y0}&w={w}&h={h}"
            data = urllib.request.urlopen(url, timeout=10).read().decode()
            o = json.loads(data)
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
            base = "http://127.0.0.1:8000"
            x0 = int(self.roi_x0.value())
            y0 = int(self.roi_y0.value())
            w = int(self.roi_w.value())
            h = int(self.roi_h.value())
            url = f"{base}/figures/{run_id}/autocorr-roi?x0={x0}&y0={y0}&w={w}&h={h}"
            data = urllib.request.urlopen(url, timeout=10).read().decode()
            o = json.loads(data)
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
            base = "http://127.0.0.1:8000"
            x0 = int(self.roi_x0.value())
            y0 = int(self.roi_y0.value())
            w = int(self.roi_w.value())
            h = int(self.roi_h.value())
            url = f"{base}/figures/{run_id}/spectrum-roi?x0={x0}&y0={y0}&w={w}&h={h}"
            data = urllib.request.urlopen(url, timeout=10).read().decode()
            o = json.loads(data)
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
            base = "http://127.0.0.1:8000"
            data = urllib.request.urlopen(f"{base}/runs/{run_id}", timeout=10).read().decode()
            o = json.loads(data)
            self.status_label.setText(f"status: {o.get('status','-')}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def abort_run(self):
        try:
            run_id = int(self.run_id.value())
            base = "http://127.0.0.1:8000"
            req = urllib.request.Request(f"{base}/runs/{run_id}/abort", data=b"", method="POST")
            data = urllib.request.urlopen(req, timeout=10).read().decode()
            o = json.loads(data)
            self.status_label.setText(f"status: {o.get('status','-')}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def retry_run(self):
        try:
            run_id = int(self.run_id.value())
            base = "http://127.0.0.1:8000"
            req = urllib.request.Request(f"{base}/runs/{run_id}/retry", data=b"", method="POST")
            data = urllib.request.urlopen(req, timeout=10).read().decode()
            o = json.loads(data)
            self.status_label.setText(f"status: {o.get('status','-')}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def download_snapshot(self):
        try:
            run_id = int(self.run_id.value())
            base = "http://127.0.0.1:8000"
            path, _ = QFileDialog.getSaveFileName(self, "Guardar snapshot", f"snapshot_{run_id}.png", "PNG (*.png)")
            if not path:
                return
            data = urllib.request.urlopen(f"{base}/figures/{run_id}/snapshot", timeout=15).read()
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
            base = "http://127.0.0.1:8000"
            path, _ = QFileDialog.getSaveFileName(self, "Guardar serie", f"series_{run_id}.npz", "NPZ (*.npz)")
            if not path:
                return
            data = urllib.request.urlopen(f"{base}/figures/{run_id}/series", timeout=20).read()
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
            base = "http://127.0.0.1:8000"
            path, _ = QFileDialog.getSaveFileName(self, "Guardar campo", f"field_{run_id}.npy", "NPY (*.npy)")
            if not path:
                return
            data = urllib.request.urlopen(f"{base}/figures/{run_id}/field", timeout=20).read()
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
            base = "http://127.0.0.1:8000"
            data = urllib.request.urlopen(f"{base}/figures/{run_id}/series-metrics", timeout=20).read().decode()
            o = json.loads(data)
            if int(o.get("length", 0)) == 0:
                QMessageBox.information(self, "CSV", "No hay series métricas disponibles")
                return
            path, _ = QFileDialog.getSaveFileName(self, "Guardar métricas CSV", f"metrics_{run_id}.csv", "CSV (*.csv)")
            if not path:
                return
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["frame", "energy", "mean", "variance", "spatial_corr"])
                for i, m in enumerate(o["series"]):
                    w.writerow([i, m.get("energy"), m.get("mean"), m.get("variance"), m.get("spatial_corr")])
            QMessageBox.information(self, "CSV", f"Guardado en {path}")
        except urllib.error.URLError as e:
            QMessageBox.warning(self, "Error", f"No se pudo conectar al API: {e}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def export_report_html(self):
        try:
            run_id = int(self.run_id.value())
            crop = int(self.crop.value())
            base = "http://127.0.0.1:8000"
            path, _ = QFileDialog.getSaveFileName(
                self, "Guardar reporte HTML", f"report_run_{run_id}.html", "HTML (*.html)"
            )
            if not path:
                return
            # Snapshot
            snapshot = urllib.request.urlopen(f"{base}/figures/{run_id}/snapshot", timeout=15).read()
            # Spectrum
            spec = json.loads(urllib.request.urlopen(f"{base}/figures/{run_id}/spectrum", timeout=10).read().decode())
            k = np.array(spec.get("k", []), dtype=np.float32)
            ps = np.array(spec.get("ps", []), dtype=np.float32)
            # Autocorr
            acj = json.loads(
                urllib.request.urlopen(f"{base}/figures/{run_id}/autocorr?crop={crop}", timeout=10).read().decode()
            )
            ac = np.array(acj.get("autocorr", []), dtype=np.float32)
            # Series metrics
            ser = json.loads(
                urllib.request.urlopen(f"{base}/figures/{run_id}/series-metrics", timeout=20).read().decode()
            )
            # Build images
            # Spectrum image
            figS = Figure(figsize=(5, 3), dpi=120)
            axS = figS.add_subplot(111)
            if k.size:
                if self.spec_log.isChecked():
                    axS.semilogy(k, ps, label="Espectro radial")
                else:
                    axS.plot(k, ps, label="Espectro radial")
                axS.set_xlabel("k")
                axS.set_ylabel("potencia")
                axS.grid(True)
                axS.legend()
            bufS = io.BytesIO()
            figS.savefig(bufS, format="png", bbox_inches="tight")
            # Autocorr image
            figA = Figure(figsize=(4, 4), dpi=120)
            axA = figA.add_subplot(111)
            if ac.size:
                im = axA.imshow(ac, cmap="viridis", origin="lower")
                figA.colorbar(im, ax=axA, fraction=0.046, pad=0.04)
            bufA = io.BytesIO()
            figA.savefig(bufA, format="png", bbox_inches="tight")
            # Energy image
            e_b64 = ""
            if int(ser.get("length", 0)) > 0:
                e = np.array([m.get("energy", np.nan) for m in ser["series"]], dtype=np.float32)
                figE = Figure(figsize=(5, 3), dpi=120)
                axE = figE.add_subplot(111)
                axE.plot(np.arange(len(e)), e, label="Energía")
                axE.set_xlabel("frame")
                axE.set_ylabel("energía")
                axE.grid(True)
                axE.legend()
                bufE = io.BytesIO()
                figE.savefig(bufE, format="png", bbox_inches="tight")
                e_b64 = "data:image/png;base64," + base64.b64encode(bufE.getvalue()).decode()
            # Compose HTML
            snap_b64 = "data:image/png;base64," + base64.b64encode(snapshot).decode()
            spec_b64 = "data:image/png;base64," + base64.b64encode(bufS.getvalue()).decode()
            auto_b64 = "data:image/png;base64," + base64.b64encode(bufA.getvalue()).decode()
            html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Reporte Run {run_id}</title>
<style>
body{{font-family:Arial;margin:20px}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:20px}}
.card{{border:1px solid #ccc;padding:12px;border-radius:8px}}
img{{max-width:100%}}
</style>
</head><body><h1>Reporte de Run {run_id}</h1>
<div class="grid">
<div class="card"><h2>Snapshot</h2><img src="{snap_b64}"/></div>
<div class="card"><h2>Energía vs tiempo</h2>{('<img src=\"'+e_b64+'\"/>') if e_b64 else '<p>Sin serie</p>'}</div>
<div class="card"><h2>Espectro radial</h2><img src="{spec_b64}"/></div>
<div class="card"><h2>Autocorrelación 2D</h2><img src="{auto_b64}"/></div>
</div></body></html>"""
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
