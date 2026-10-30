import sys
import time
from pathlib import Path

import numpy as np
from mss import mss
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from Overtilt import ContadorSesion, DetectorResultado, analizar_frame, crear_region


class DetectorThread(QThread):
    status_changed = Signal(str)
    ocr_changed = Signal(str)
    stats_changed = Signal(int, int, int)
    result_detected = Signal(str, int, int, int)
    rest_alert = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, loss_limit):
        super().__init__()
        self.loss_limit = loss_limit

    def run(self):
        counter = ContadorSesion(self.loss_limit)
        detector = DetectorResultado()
        self.status_changed.emit("Conectando con el monitor…")
        last_ocr = None
        last_debug = 0.0

        try:
            with mss() as screen:
                monitor = screen.monitors[1]
                bbox = crear_region(monitor)
                self.status_changed.emit(
                    f"Capturando · {bbox['width']} × {bbox['height']} px"
                )

                while not self.isInterruptionRequested():
                    frame = np.array(screen.grab(bbox))
                    _, _, _, text = analizar_frame(frame)
                    outcome = detector.actualizar(text)

                    now = time.monotonic()
                    if text != last_ocr or now - last_debug >= 1.5:
                        self.ocr_changed.emit(text.strip() or "Sin texto de resultado")
                        last_ocr = text
                        last_debug = now

                    if outcome:
                        if counter.registrar(outcome):
                            self.rest_alert.emit(counter.racha_derrotas)
                        self.stats_changed.emit(
                            counter.victorias, counter.derrotas, counter.racha_derrotas
                        )
                        self.result_detected.emit(
                            outcome,
                            counter.victorias,
                            counter.derrotas,
                            counter.racha_derrotas,
                        )

                    self.msleep(350)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        finally:
            self.status_changed.emit("Detección detenida")


class RestDialog(QDialog):
    def __init__(self, streak, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pausa recomendada")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedWidth(390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        title = QLabel("Hora de hacer una pausa")
        title.setObjectName("dialogTitle")
        body = QLabel(
            f"Has perdido {streak} partidas seguidas.\n"
            "Levántate un momento, toma agua y descansa la vista."
        )
        body.setObjectName("dialogBody")
        body.setWordWrap(True)
        button = QPushButton("Entendido")
        button.clicked.connect(self.close)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(body)
        layout.addSpacing(16)
        layout.addWidget(button)
        QTimer.singleShot(15000, self.close)


class OverlayWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("overlayRoot")
        self.setFixedSize(390, 116)
        self._drag_offset = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("overlayPanel")
        row = QHBoxLayout(panel)
        row.setContentsMargins(16, 12, 12, 12)
        row.setSpacing(0)

        brand = QVBoxLayout()
        mark = QLabel("OVERTILT")
        mark.setObjectName("overlayBrand")
        self.state = QLabel("● DETENIDO")
        self.state.setObjectName("overlayState")
        brand.addWidget(mark)
        brand.addWidget(self.state)
        row.addLayout(brand)
        row.addSpacing(12)

        self.win_value = self._metric(row, "V", "0", "win")
        self.loss_value = self._metric(row, "D", "0", "loss")
        self.streak_value = self._metric(row, "RACHA", "0", "streak")
        row.addStretch(1)

        hide_button = QPushButton("×")
        hide_button.setObjectName("overlayHide")
        hide_button.setFixedSize(25, 25)
        hide_button.setToolTip("Ocultar overlay")
        hide_button.clicked.connect(self.hide)
        row.addWidget(hide_button, alignment=Qt.AlignmentFlag.AlignTop)
        outer.addWidget(panel)
        self.setStyleSheet("""
            QWidget#overlayRoot { background: transparent; }
            QFrame#overlayPanel { background: rgba(9, 15, 20, 224); border: 1px solid rgba(115, 242, 193, 135); border-radius: 15px; }
            QLabel#overlayBrand { color: #e8f2f4; font-size: 12px; font-weight: 800; letter-spacing: 1px; }
            QLabel#overlayState { color: #81929d; font-size: 9px; font-weight: 700; }
            QLabel#overlayMetricCaption { color: #9aabb3; font-size: 9px; font-weight: 700; }
            QLabel#overlayMetricValue { font-size: 23px; font-weight: 800; }
            QWidget[tone="win"] QLabel#overlayMetricValue { color: #73f2c1; }
            QWidget[tone="loss"] QLabel#overlayMetricValue { color: #ff7d85; }
            QWidget[tone="streak"] QLabel#overlayMetricValue { color: #f7c96b; }
            QPushButton#overlayHide { background: rgba(255,255,255,18); color: #b8c4ca; border: none; border-radius: 12px; font-size: 17px; }
            QPushButton#overlayHide:hover { background: rgba(255,125,133,100); color: white; }
        """)

    @staticmethod
    def _metric(row, caption, value, tone):
        holder = QWidget()
        holder.setProperty("tone", tone)
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(9, 0, 9, 0)
        layout.setSpacing(2)
        cap = QLabel(caption)
        cap.setObjectName("overlayMetricCaption")
        number = QLabel(value)
        number.setObjectName("overlayMetricValue")
        layout.addWidget(cap, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(number, alignment=Qt.AlignmentFlag.AlignHCenter)
        row.addWidget(holder)
        return number

    def place_default(self):
        screen = QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 24, area.top() + 80)

    def set_stats(self, wins, losses, streak):
        self.win_value.setText(str(wins))
        self.loss_value.setText(str(losses))
        self.streak_value.setText(str(streak))

    def set_running(self, running):
        self.state.setText("● CAPTURANDO" if running else "● DETENIDO")
        self.state.setStyleSheet(
            f"color: {'#73f2c1' if running else '#81929d'}; font-size: 9px; font-weight: 700"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        event.accept()


class OverTiltWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OverTilt")
        self.app_icon = QIcon(str(Path(__file__).parent / "assets" / "overtilt.png"))
        self.setWindowIcon(self.app_icon)
        self.setMinimumSize(760, 620)
        self.resize(880, 700)
        self.detector_thread = None
        self.wins = 0
        self.losses = 0
        self.streak = 0
        self.activity_rows = []
        self.detector_active = False
        self.defeat_sound = QSoundEffect(self)
        self.defeat_sound.setSource(
            QUrl.fromLocalFile(str(Path(__file__).parent / "assets" / "defeat.wav"))
        )
        self.defeat_sound.setVolume(0.45)
        self.rest_sound = QSoundEffect(self)
        self.rest_sound.setSource(
            QUrl.fromLocalFile(str(Path(__file__).parent / "assets" / "rest.wav"))
        )
        self.rest_sound.setVolume(0.55)
        self.start_sound = QSoundEffect(self)
        self.start_sound.setSource(
            QUrl.fromLocalFile(
                str(Path(__file__).parent / "assets" / "detection_start.wav")
            )
        )
        self.start_sound.setVolume(0.38)
        self.stop_sound = QSoundEffect(self)
        self.stop_sound.setSource(
            QUrl.fromLocalFile(
                str(Path(__file__).parent / "assets" / "detection_stop.wav")
            )
        )
        self.stop_sound.setVolume(0.38)
        self._build_ui()
        self._apply_style()
        # Ventana independiente para que siga visible al minimizar el panel principal.
        self.overlay = OverlayWindow()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(30, 26, 30, 26)
        outer.setSpacing(20)

        header = QHBoxLayout()
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setObjectName("logo")
        logo.setPixmap(
            QPixmap(str(Path(__file__).parent / "assets" / "overtilt.png")).scaled(
                46,
                46,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        brand_text = QVBoxLayout()
        name = QLabel("OVERTILT")
        name.setObjectName("brand")
        tagline = QLabel("SESSION COMPANION")
        tagline.setObjectName("tagline")
        brand_text.addWidget(name)
        brand_text.addWidget(tagline)
        brand.addWidget(logo)
        brand.addLayout(brand_text)
        header.addLayout(brand)
        header.addStretch()
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("statusDot")
        self.status_label = QLabel("Listo para empezar")
        self.status_label.setObjectName("statusLabel")
        header.addWidget(self.status_dot)
        header.addWidget(self.status_label)
        outer.addLayout(header)

        intro = QVBoxLayout()
        title = QLabel("Tu sesión, bajo control.")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Seguimiento de resultados y pausas más saludables.")
        subtitle.setObjectName("subtitle")
        intro.addWidget(title)
        intro.addWidget(subtitle)
        outer.addLayout(intro)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.wins_value = self._stat_card(stats, "VICTORIAS", "0", "win")
        self.losses_value = self._stat_card(stats, "DERROTAS", "0", "loss")
        self.streak_value = self._stat_card(stats, "RACHA ACTUAL", "0", "streak")
        outer.addLayout(stats)

        settings = QFrame()
        settings.setObjectName("panel")
        settings_layout = QHBoxLayout(settings)
        settings_layout.setContentsMargins(20, 17, 20, 17)
        settings_info = QVBoxLayout()
        settings_title = QLabel("Límite de derrotas")
        settings_title.setObjectName("sectionTitle")
        settings_hint = QLabel("Te avisaremos cuando alcances esta racha.")
        settings_hint.setObjectName("muted")
        settings_info.addWidget(settings_title)
        settings_info.addWidget(settings_hint)
        settings_layout.addLayout(settings_info)
        settings_layout.addStretch()
        self.loss_limit = QSpinBox()
        self.loss_limit.setRange(1, 20)
        self.loss_limit.setValue(3)
        self.loss_limit.setSuffix(" derrotas")
        settings_layout.addWidget(self.loss_limit)
        outer.addWidget(settings)

        progress_panel = QFrame()
        progress_panel.setObjectName("panel")
        progress_layout = QVBoxLayout(progress_panel)
        progress_layout.setContentsMargins(20, 16, 20, 16)
        progress_head = QHBoxLayout()
        progress_head.addWidget(QLabel("Progreso hacia la pausa"))
        progress_head.addStretch()
        self.progress_text = QLabel("0 / 3")
        self.progress_text.setObjectName("progressText")
        progress_head.addWidget(self.progress_text)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 3)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        progress_layout.addLayout(progress_head)
        progress_layout.addWidget(self.progress_bar)
        outer.addWidget(progress_panel)

        lower = QHBoxLayout()
        lower.setSpacing(14)
        activity = QFrame()
        activity.setObjectName("panel")
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(20, 17, 20, 17)
        activity_title = QLabel("Actividad reciente")
        activity_title.setObjectName("sectionTitle")
        self.activity_label = QLabel("Los resultados detectados aparecerán aquí.")
        self.activity_label.setObjectName("muted")
        self.activity_label.setWordWrap(True)
        activity_layout.addWidget(activity_title)
        activity_layout.addSpacing(10)
        activity_layout.addWidget(self.activity_label)
        activity_layout.addStretch()

        ocr = QFrame()
        ocr.setObjectName("panel")
        ocr_layout = QVBoxLayout(ocr)
        ocr_layout.setContentsMargins(20, 17, 20, 17)
        ocr_title = QLabel("Lectura del OCR")
        ocr_title.setObjectName("sectionTitle")
        self.ocr_label = QLabel("Esperando a iniciar la captura…")
        self.ocr_label.setObjectName("ocrText")
        self.ocr_label.setWordWrap(True)
        ocr_layout.addWidget(ocr_title)
        ocr_layout.addSpacing(10)
        ocr_layout.addWidget(self.ocr_label)
        ocr_layout.addStretch()
        lower.addWidget(activity, 1)
        lower.addWidget(ocr, 1)
        outer.addLayout(lower, 1)

        actions = QHBoxLayout()
        self.start_button = QPushButton("Iniciar detección")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_detection)
        self.stop_button = QPushButton("Detener")
        self.stop_button.setObjectName("secondaryButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_detection)
        self.reset_button = QPushButton("Reiniciar sesión")
        self.reset_button.setObjectName("secondaryButton")
        self.reset_button.clicked.connect(self.reset_session)
        self.overlay_button = QPushButton("Mostrar overlay")
        self.overlay_button.setObjectName("secondaryButton")
        self.overlay_button.clicked.connect(self.toggle_overlay)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addStretch()
        actions.addWidget(self.overlay_button)
        actions.addWidget(self.reset_button)
        outer.addLayout(actions)

    def _stat_card(self, row, title, value, tone):
        card = QFrame()
        card.setObjectName("statCard")
        card.setProperty("tone", tone)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        caption = QLabel(title)
        caption.setObjectName("statCaption")
        number = QLabel(value)
        number.setObjectName("statValue")
        layout.addWidget(caption)
        layout.addWidget(number)
        row.addWidget(card)
        return number

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #0b1015; color: #e9f0f4; font-family: 'Segoe UI'; }
            QLabel#logo { background: transparent; min-width: 46px; max-width: 46px; min-height: 46px; max-height: 46px; }
            QLabel#brand { font-size: 16px; font-weight: 800; letter-spacing: 2px; }
            QLabel#tagline { color: #75838f; font-size: 9px; letter-spacing: 2px; }
            QLabel#statusDot { color: #73f2c1; font-size: 14px; }
            QLabel#statusLabel { color: #9aaab4; font-size: 12px; }
            QLabel#pageTitle { font-size: 28px; font-weight: 700; }
            QLabel#subtitle, QLabel#muted { color: #82919b; font-size: 12px; }
            QFrame#statCard, QFrame#panel { background: #121a21; border: 1px solid #202c35; border-radius: 14px; }
            QLabel#statCaption { color: #84939d; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
            QLabel#statValue { font-size: 32px; font-weight: 700; }
            QFrame#statCard[tone="win"] QLabel#statValue { color: #73f2c1; }
            QFrame#statCard[tone="loss"] QLabel#statValue { color: #ff7d85; }
            QFrame#statCard[tone="streak"] QLabel#statValue { color: #f7c96b; }
            QLabel#sectionTitle { font-size: 13px; font-weight: 700; }
            QLabel#progressText { color: #73f2c1; font-size: 12px; font-weight: 700; }
            QProgressBar { background: #202b33; border: none; border-radius: 5px; height: 9px; }
            QProgressBar::chunk { background: #73f2c1; border-radius: 5px; }
            QSpinBox { background: #0d141a; border: 1px solid #2a3944; border-radius: 8px; padding: 8px 10px; min-width: 120px; }
            QLabel#ocrText { color: #a8b8c2; font-family: Consolas; font-size: 12px; }
            QPushButton { border-radius: 9px; padding: 11px 18px; font-weight: 700; }
            QPushButton#primaryButton { background: #73f2c1; color: #08120f; }
            QPushButton#primaryButton:hover { background: #9bf8d5; }
            QPushButton#primaryButton:disabled { background: #33443f; color: #81918b; }
            QPushButton#secondaryButton { background: #172129; border: 1px solid #2b3a44; color: #c4d0d7; }
            QPushButton#secondaryButton:hover { background: #202d36; }
            QPushButton#secondaryButton:disabled { color: #59656d; }
            QLabel#dialogTitle { font-size: 19px; font-weight: 700; color: #73f2c1; }
            QLabel#dialogBody { color: #b7c3ca; font-size: 13px; }
        """)

    def start_detection(self):
        if self.detector_thread and self.detector_thread.isRunning():
            return
        self.detector_thread = DetectorThread(self.loss_limit.value())
        self.detector_thread.status_changed.connect(self.set_status)
        self.detector_thread.ocr_changed.connect(self.ocr_label.setText)
        self.detector_thread.stats_changed.connect(self.update_stats)
        self.detector_thread.result_detected.connect(self.add_result)
        self.detector_thread.rest_alert.connect(self.show_rest_alert)
        self.detector_thread.error_occurred.connect(self.show_error)
        self.detector_thread.finished.connect(self.on_detection_finished)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.loss_limit.setEnabled(False)
        self.overlay.set_running(True)
        self.set_status("Iniciando detector…")
        self.detector_thread.start()

    def stop_detection(self):
        if self.detector_thread and self.detector_thread.isRunning():
            self.detector_thread.requestInterruption()
            self.stop_button.setEnabled(False)
            self.set_status("Deteniendo…")

    def on_detection_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.loss_limit.setEnabled(True)
        self.overlay.set_running(False)
        self.detector_thread = None

    def set_status(self, text):
        self.status_label.setText(text)
        active = text.startswith("Capturando") or text.startswith("Conectando")
        self.status_dot.setStyleSheet(f"color: {'#73f2c1' if active else '#65737d'}")
        capture_is_active = text.startswith("Capturando")
        if capture_is_active and not self.detector_active:
            self.detector_active = True
            self.start_sound.play()
        elif not capture_is_active and self.detector_active:
            self.detector_active = False
            self.stop_sound.play()

    def update_stats(self, wins, losses, streak):
        self.wins, self.losses, self.streak = wins, losses, streak
        self.wins_value.setText(str(wins))
        self.losses_value.setText(str(losses))
        self.streak_value.setText(str(streak))
        self.overlay.set_stats(wins, losses, streak)
        limit = self.loss_limit.value()
        self.progress_bar.setMaximum(limit)
        self.progress_bar.setValue(min(streak, limit))
        self.progress_text.setText(f"{min(streak, limit)} / {limit}")

    def add_result(self, result, wins, losses, streak):
        self.update_stats(wins, losses, streak)
        if result == "derrota":
            self.defeat_sound.play()
        label = "Victoria" if result == "victoria" else "Derrota"
        time_text = time.strftime("%H:%M:%S")
        tone = "#73f2c1" if result == "victoria" else "#ff7d85"
        self.activity_rows.insert(0, f'<span style="color:{tone}">● {label}</span> '
                                  f'<span style="color:#71808a">{time_text}</span>')
        self.activity_rows = self.activity_rows[:5]
        self.activity_label.setText("<br>".join(self.activity_rows))
        self.activity_label.setTextFormat(Qt.TextFormat.RichText)

    def show_rest_alert(self, streak):
        dialog = RestDialog(streak, self)
        dialog.show()
        # Deja terminar primero el sonido de derrota si ambos eventos coinciden.
        QTimer.singleShot(450, self.rest_sound.play)

    def show_error(self, message):
        self.set_status("Error del detector")
        self.ocr_label.setText(message)
        self.ocr_label.setStyleSheet("color: #ff7d85")

    def reset_session(self):
        if self.detector_thread and self.detector_thread.isRunning():
            self.stop_detection()
            self.detector_thread.wait(2000)
            self.on_detection_finished()
        self.wins = self.losses = self.streak = 0
        self.activity_rows.clear()
        self.activity_label.setText("Los resultados detectados aparecerán aquí.")
        self.update_stats(0, 0, 0)
        self.ocr_label.setStyleSheet("")
        self.ocr_label.setText("Sesión reiniciada. Lista para empezar.")
        self.set_status("Listo para empezar")

    def toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
            self.overlay_button.setText("Mostrar overlay")
        else:
            self.overlay.place_default()
            self.overlay.show()
            self.overlay.raise_()
            self.overlay_button.setText("Ocultar overlay")

    def closeEvent(self, event):
        if self.detector_thread and self.detector_thread.isRunning():
            self.detector_thread.requestInterruption()
            self.detector_thread.wait(2500)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("OverTilt")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "overtilt.png")))
    window = OverTiltWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
