import sys
import time
from pathlib import Path

import numpy as np
from mss import mss
from PySide6.QtCore import (
    QPoint,
    QPointF,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

import theme
from Overtilt import ContadorSesion, DetectorResultado, analizar_frame, crear_region


def _repolish(widget):
    """Vuelve a aplicar el QSS después de cambiar una propiedad dinámica."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


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


class ResizeGrip(QWidget):
    """Indicador de agarre dibujado en la esquina inferior derecha."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(143, 163, 157, 120))
        step = self.width() / 5
        radius = max(0.9, self.width() / 13)
        for row in range(3):
            for column in range(3):
                if row + column >= 2:
                    painter.drawEllipse(
                        QPointF(step * (column + 1.5), step * (row + 1.5)),
                        radius,
                        radius,
                    )


class RestDialog(QDialog):
    def __init__(self, streak, parent=None):
        super().__init__(parent)
        self.setObjectName("restDialog")
        self.setWindowTitle("Pausa recomendada")
        self.setModal(False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setFixedWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(0)

        badge = QLabel("II")
        badge.setObjectName("dialogBadge")
        badge.setFixedSize(44, 44)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(16)

        title = QLabel("Hora de hacer una pausa")
        title.setObjectName("dialogTitle")
        body = QLabel(
            f"Has perdido {streak} partidas seguidas.\n"
            "Levántate un momento, toma agua y descansa la vista."
        )
        body.setObjectName("dialogBody")
        body.setWordWrap(True)
        button = QPushButton("Entendido")
        button.setObjectName("primaryButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(38)
        button.clicked.connect(self.close)

        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(body)
        layout.addSpacing(20)
        layout.addWidget(button)
        QTimer.singleShot(15000, self.close)


class OverlayWindow(QWidget):
    scale_changed = Signal(float)
    visibility_changed = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.scale = self._load_scale()
        self._mode = None
        self._drag_offset = None
        self._resize_origin = None
        self._resize_start_size = QSize()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save_now)

        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setObjectName("overlayRoot")
        self.setMouseTracking(True)

        self._metric_slots = []
        self._build_ui()
        self._apply_scale(self.scale, emit=False)
        self._restore_position()

    # -- construcción -----------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.panel = QFrame()
        self.panel.setObjectName("overlayPanel")
        self.row = QHBoxLayout(self.panel)
        self.row.setSpacing(0)

        self.brand_label = QLabel("OVERTILT")
        self.brand_label.setObjectName("overlayBrand")
        self.state = QLabel("● DETENIDO")
        self.state.setObjectName("overlayState")

        brand = QVBoxLayout()
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(2)
        brand.addWidget(self.brand_label, alignment=Qt.AlignmentFlag.AlignLeft)
        brand.addWidget(self.state, alignment=Qt.AlignmentFlag.AlignLeft)
        self.row.addLayout(brand)

        self.brand_gap = QSpacerItem(
            12, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )
        self.row.addItem(self.brand_gap)

        self.win_value = self._metric("V", "0", "win")
        self.loss_value = self._metric("D", "0", "loss")
        self.streak_value = self._metric("RACHA", "0", "streak")
        self.row.addStretch(1)

        self.hide_button = QPushButton("×")
        self.hide_button.setObjectName("overlayHide")
        self.hide_button.setToolTip("Ocultar overlay")
        self.hide_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide_button.clicked.connect(self.hide)
        self.row.addWidget(self.hide_button, alignment=Qt.AlignmentFlag.AlignTop)

        outer.addWidget(self.panel)

        self.grip = ResizeGrip(self)
        self.grip.setToolTip("Arrastra para cambiar el tamaño")

    def _metric(self, caption, value, tone):
        holder = QWidget()
        holder.setProperty("tone", tone)
        layout = QVBoxLayout(holder)
        cap = QLabel(caption)
        cap.setObjectName("overlayMetricCaption")
        number = QLabel(value)
        number.setObjectName("overlayMetricValue")
        layout.addWidget(cap, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(number, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.row.addWidget(holder)
        self._metric_slots.append(layout)
        return number

    # -- escala y posición ------------------------------------------------
    def _px(self, value):
        return max(1, round(value * self.scale))

    def _load_scale(self):
        try:
            value = float(self.settings.value("overlay/scale", 1.0))
        except (TypeError, ValueError):
            value = 1.0
        return max(theme.OVERLAY_MIN_SCALE, min(theme.OVERLAY_MAX_SCALE, value))

    def _apply_scale(self, scale, emit=True):
        self.scale = max(
            theme.OVERLAY_MIN_SCALE, min(theme.OVERLAY_MAX_SCALE, float(scale))
        )
        self.setFixedSize(
            round(theme.OVERLAY_BASE_WIDTH * self.scale),
            round(theme.OVERLAY_BASE_HEIGHT * self.scale),
        )

        self.row.setContentsMargins(
            self._px(16), self._px(12), self._px(12), self._px(12)
        )
        self.brand_gap.changeSize(
            self._px(12), 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )
        for layout in self._metric_slots:
            layout.setContentsMargins(self._px(9), 0, self._px(9), 0)
            layout.setSpacing(self._px(2))

        button_size = self._px(25)
        self.hide_button.setFixedSize(button_size, button_size)

        brand_font = QFont(theme.FONT_FAMILY)
        brand_font.setPixelSize(max(8, self._px(11)))
        brand_font.setWeight(QFont.Weight.Bold)
        brand_font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing, max(0.4, self.scale * 1.1)
        )
        self.brand_label.setFont(brand_font)

        self.setStyleSheet(theme.overlay_stylesheet(self.scale))
        self._place_grip()
        if emit:
            self.scale_changed.emit(self.scale)

    def _place_grip(self):
        size = self._px(15)
        self.grip.setFixedSize(size, size)
        self.grip.move(
            self.width() - size - self._px(3),
            self.height() - size - self._px(3),
        )
        self.grip.raise_()

    def set_scale(self, scale):
        self._apply_scale(scale)
        self._clamp_to_screen()
        self._schedule_save()

    def _clamp_to_screen(self):
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 8
        max_x = max(area.left() + margin, area.right() - self.width() - margin)
        max_y = max(area.top() + margin, area.bottom() - self.height() - margin)
        x = max(area.left() + margin, min(self.x(), max_x))
        y = max(area.top() + margin, min(self.y(), max_y))
        self.move(x, y)

    def place_default(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 24, area.top() + 80)
        self._clamp_to_screen()

    def reset_position(self):
        self.place_default()
        self._schedule_save()

    def _restore_position(self):
        position = self.settings.value("overlay/pos")
        if isinstance(position, QPoint):
            self.move(position)
            self._clamp_to_screen()
        else:
            self.place_default()

    def _schedule_save(self):
        self._save_timer.start()

    def save_now(self):
        self.settings.setValue("overlay/scale", self.scale)
        self.settings.setValue("overlay/pos", self.pos())
        self.settings.setValue("overlay/visible", self.isVisible())
        self.settings.sync()

    # -- arrastre y redimensión -------------------------------------------
    def _in_grip_zone(self, point):
        margin = self._px(22)
        return (
            point.x() >= self.width() - margin
            and point.y() >= self.height() - margin
        )

    def _cursor_for(self, point):
        if self._in_grip_zone(point):
            return Qt.CursorShape.SizeFDiagCursor
        return Qt.CursorShape.ArrowCursor

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        point = event.position().toPoint()
        if self._in_grip_zone(point):
            self._mode = "resize"
            self._resize_origin = event.globalPosition().toPoint()
            self._resize_start_size = self.size()
        else:
            self._mode = "move"
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
        self.setCursor(self._cursor_for(point))
        event.accept()

    def mouseMoveEvent(self, event):
        point = event.position().toPoint()
        if event.buttons() & Qt.MouseButton.LeftButton:
            if self._mode == "move" and self._drag_offset is not None:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                self._schedule_save()
                event.accept()
                return
            if self._mode == "resize" and self._resize_origin is not None:
                delta = event.globalPosition().toPoint() - self._resize_origin
                width = self._resize_start_size.width() + delta.x()
                height = self._resize_start_size.height() + delta.y()
                target = max(
                    width / theme.OVERLAY_BASE_WIDTH,
                    height / theme.OVERLAY_BASE_HEIGHT,
                )
                target = max(
                    theme.OVERLAY_MIN_SCALE,
                    min(theme.OVERLAY_MAX_SCALE, target),
                )
                if abs(target - self.scale) > 0.001:
                    self._apply_scale(target)
                    self._clamp_to_screen()
                    self._schedule_save()
                event.accept()
                return

        self.setCursor(self._cursor_for(point))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mode is not None:
            self._mode = None
            self._drag_offset = None
            self._resize_origin = None
            self.setCursor(self._cursor_for(event.position().toPoint()))
            self._schedule_save()
        event.accept()

    def leaveEvent(self, event):
        if self._mode is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "grip"):
            self._place_grip()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for name, value in theme.OVERLAY_PRESETS:
            action = menu.addAction(f"{name} · {round(value * 100)} %")
            action.setCheckable(True)
            action.setChecked(abs(self.scale - value) < 0.01)
            action.triggered.connect(
                lambda checked=False, selected=value: self.set_scale(selected)
            )
        menu.addSeparator()
        reset = menu.addAction("Restablecer posición")
        reset.triggered.connect(self.reset_position)
        hide_action = menu.addAction("Ocultar overlay")
        hide_action.triggered.connect(self.hide)
        menu.exec(event.globalPos())

    # -- estado ------------------------------------------------------------
    def set_stats(self, wins, losses, streak):
        self.win_value.setText(str(wins))
        self.loss_value.setText(str(losses))
        self.streak_value.setText(str(streak))

    def set_running(self, running):
        self.state.setText("● CAPTURANDO" if running else "● DETENIDO")
        self.state.setProperty("running", running)
        _repolish(self.state)

    def showEvent(self, event):
        super().showEvent(event)
        self.visibility_changed.emit(True)
        self._schedule_save()

    def hideEvent(self, event):
        self.visibility_changed.emit(False)
        self._schedule_save()
        super().hideEvent(event)


class LimitStepper(QWidget):
    """Selector numérico compacto con botones − y +."""

    valueChanged = Signal(int)

    def __init__(self, minimum=1, maximum=20, value=3, parent=None):
        super().__init__(parent)
        self._minimum = minimum
        self._maximum = maximum
        self._value = max(minimum, min(maximum, value))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.minus = QPushButton("−")
        self.minus.setObjectName("stepperButton")
        self.minus.setToolTip("Reducir el límite")
        self.minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minus.clicked.connect(lambda: self.setValue(self._value - 1))

        self.display = QLabel()
        self.display.setObjectName("stepperValue")
        self.display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display.setToolTip("Usa − y + para ajustar el límite")

        self.plus = QPushButton("+")
        self.plus.setObjectName("stepperButton")
        self.plus.setToolTip("Aumentar el límite")
        self.plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.plus.clicked.connect(lambda: self.setValue(self._value + 1))

        layout.addWidget(self.minus)
        layout.addWidget(self.display)
        layout.addWidget(self.plus)
        self._refresh()

    def value(self):
        return self._value

    def setValue(self, value):
        value = max(self._minimum, min(self._maximum, int(value)))
        if value == self._value:
            return
        self._value = value
        self._refresh()
        self.valueChanged.emit(value)

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self._refresh()

    def _refresh(self):
        self.display.setText(f"{self._value} derrotas")
        self.minus.setEnabled(self.isEnabled() and self._value > self._minimum)
        self.plus.setEnabled(self.isEnabled() and self._value < self._maximum)


class OverTiltWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OverTilt")
        self.app_icon = QIcon(str(Path(__file__).parent / "assets" / "overtilt.png"))
        self.setWindowIcon(self.app_icon)
        self.setMinimumSize(820, 700)
        self.resize(900, 720)

        self.settings = QSettings()
        self.theme_name = self.settings.value("appearance/theme", "light")
        if self.theme_name not in ("light", "dark"):
            self.theme_name = "light"
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

        # Ventana independiente para que siga visible al minimizar el panel principal.
        self.overlay = OverlayWindow(self.settings)

        self._build_ui()
        self._restore_preferences()
        self._apply_theme(self.theme_name, persist=False)

        self.overlay.scale_changed.connect(self._on_overlay_scale_changed)
        self.overlay.visibility_changed.connect(self._on_overlay_visibility_changed)
        self._on_overlay_scale_changed(self.overlay.scale)
        self._on_overlay_visibility_changed(self.overlay.isVisible())

        if self.settings.value("overlay/visible", False, type=bool):
            QTimer.singleShot(0, self._show_overlay_at_start)

    # -- interfaz ----------------------------------------------------------
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(32, 26, 32, 26)
        outer.setSpacing(18)

        header = QHBoxLayout()
        brand = QHBoxLayout()
        brand.setSpacing(12)
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
        brand_text.setSpacing(1)
        name = QLabel("OVERTILT")
        name.setObjectName("brand")
        brand_font = QFont(theme.FONT_FAMILY)
        brand_font.setPixelSize(16)
        brand_font.setWeight(QFont.Weight.Bold)
        brand_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
        name.setFont(brand_font)
        tagline = QLabel("COMPAÑERO DE SESIÓN")
        tagline.setObjectName("tagline")
        tagline_font = QFont(theme.FONT_FAMILY)
        tagline_font.setPixelSize(9)
        tagline_font.setWeight(QFont.Weight.DemiBold)
        tagline_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        tagline.setFont(tagline_font)
        brand_text.addWidget(name)
        brand_text.addWidget(tagline)
        brand.addWidget(logo)
        brand.addLayout(brand_text)
        header.addLayout(brand)
        header.addStretch()

        theme_switch = QFrame()
        theme_switch.setObjectName("themeSwitch")
        theme_layout = QHBoxLayout(theme_switch)
        theme_layout.setContentsMargins(3, 3, 3, 3)
        theme_layout.setSpacing(2)

        self.theme_group = QButtonGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_buttons = {}

        for theme_name, label, tooltip in (
            ("light", "Claro", "Usar el tema claro"),
            ("dark", "Oscuro", "Usar el tema oscuro"),
        ):
            button = QPushButton(label)
            button.setObjectName("themeOption")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(tooltip)
            button.setProperty("themeName", theme_name)
            self.theme_group.addButton(button)
            self.theme_buttons[theme_name] = button
            theme_layout.addWidget(button)

        self.theme_group.buttonClicked.connect(self._on_theme_clicked)
        header.addWidget(theme_switch, alignment=Qt.AlignmentFlag.AlignVCenter)
        header.addSpacing(10)

        pill = QFrame()
        pill.setObjectName("statusPill")
        pill.setMinimumWidth(220)
        pill_layout = QHBoxLayout(pill)
        pill_layout.setContentsMargins(12, 6, 14, 6)
        pill_layout.setSpacing(7)
        self.status_dot = QLabel()
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setFixedSize(8, 8)
        self.status_label = QLabel("Listo para empezar")
        self.status_label.setObjectName("statusLabel")
        pill_layout.addStretch(1)
        pill_layout.addWidget(self.status_dot)
        pill_layout.addWidget(self.status_label)
        pill_layout.addStretch(1)
        header.addWidget(pill, alignment=Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(header)

        intro = QVBoxLayout()
        intro.setSpacing(4)
        title = QLabel("Tu sesión, bajo control.")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Seguimiento sereno de resultados y pausas más saludables.")
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
        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(22, 17, 22, 17)
        settings_layout.setSpacing(12)

        limit_row = QHBoxLayout()
        limit_row.setSpacing(16)
        limit_info = QVBoxLayout()
        limit_info.setSpacing(2)
        limit_title = QLabel("Límite de derrotas")
        limit_title.setObjectName("sectionTitle")
        limit_hint = QLabel("Te avisaremos al alcanzar esta racha consecutiva.")
        limit_hint.setObjectName("hint")
        limit_info.addWidget(limit_title)
        limit_info.addWidget(limit_hint)
        limit_row.addLayout(limit_info)
        limit_row.addStretch()

        self.loss_limit = LimitStepper(1, 20, 3)
        self.loss_limit.valueChanged.connect(self._on_loss_limit_changed)
        limit_row.addWidget(
            self.loss_limit, alignment=Qt.AlignmentFlag.AlignVCenter
        )
        settings_layout.addLayout(limit_row)

        overlay_row = QHBoxLayout()
        overlay_row.setSpacing(8)
        overlay_title = QLabel("Tamaño del overlay")
        overlay_title.setObjectName("fieldLabel")
        overlay_row.addWidget(overlay_title)
        overlay_row.addSpacing(6)

        self.overlay_group = QButtonGroup(self)
        self.overlay_group.setExclusive(True)
        for preset_name, preset_value in theme.OVERLAY_PRESETS:
            button = QPushButton(preset_name)
            button.setObjectName("presetButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.overlay_group.addButton(button, round(preset_value * 100))
            overlay_row.addWidget(button)
        self.overlay_group.idClicked.connect(self._set_overlay_scale_from_id)

        self.overlay_scale_label = QLabel("100 %")
        self.overlay_scale_label.setObjectName("scaleValue")
        overlay_row.addSpacing(4)
        overlay_row.addWidget(self.overlay_scale_label)
        overlay_row.addStretch()

        reset_position = QPushButton("Restablecer posición")
        reset_position.setObjectName("ghostButton")
        reset_position.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_position.clicked.connect(self._reset_overlay_position)
        overlay_row.addWidget(reset_position)
        settings_layout.addLayout(overlay_row)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        settings_layout.addWidget(divider)

        progress_head = QHBoxLayout()
        progress_title = QLabel("Progreso hacia la pausa")
        progress_title.setObjectName("muted")
        self.progress_text = QLabel("0 / 3")
        self.progress_text.setObjectName("progressText")
        progress_head.addWidget(progress_title)
        progress_head.addStretch()
        progress_head.addWidget(self.progress_text)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 3)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        settings_layout.addLayout(progress_head)
        settings_layout.addWidget(self.progress_bar)
        outer.addWidget(settings)

        lower = QHBoxLayout()
        lower.setSpacing(14)
        activity = QFrame()
        activity.setObjectName("panel")
        activity.setMinimumHeight(142)
        activity_layout = QVBoxLayout(activity)
        activity_layout.setContentsMargins(22, 17, 22, 17)
        activity_layout.setSpacing(10)
        activity_title = QLabel("Actividad reciente")
        activity_title.setObjectName("sectionTitle")
        self.activity_placeholder = QLabel(
            "Los resultados detectados aparecerán aquí."
        )
        self.activity_placeholder.setObjectName("muted")
        self.activity_placeholder.setWordWrap(True)
        self.activity_rows_layout = QVBoxLayout()
        self.activity_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.activity_rows_layout.setSpacing(8)
        activity_layout.addWidget(activity_title)
        activity_layout.addWidget(self.activity_placeholder)
        activity_layout.addLayout(self.activity_rows_layout)
        activity_layout.addStretch()

        ocr = QFrame()
        ocr.setObjectName("panel")
        ocr.setMinimumHeight(142)
        ocr_layout = QVBoxLayout(ocr)
        ocr_layout.setContentsMargins(22, 17, 22, 17)
        ocr_layout.setSpacing(10)
        ocr_title = QLabel("Lectura del OCR")
        ocr_title.setObjectName("sectionTitle")
        self.ocr_label = QLabel("Esperando a iniciar la captura…")
        self.ocr_label.setObjectName("ocrText")
        self.ocr_label.setWordWrap(True)
        self.ocr_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        ocr_layout.addWidget(ocr_title)
        ocr_layout.addWidget(self.ocr_label)
        ocr_layout.addStretch()

        lower.addWidget(activity, 1)
        lower.addWidget(ocr, 1)
        outer.addLayout(lower, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.start_button = QPushButton("Iniciar detección")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.clicked.connect(self.start_detection)
        self.stop_button = QPushButton("Detener")
        self.stop_button.setObjectName("secondaryButton")
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_detection)
        self.reset_button = QPushButton("Reiniciar sesión")
        self.reset_button.setObjectName("secondaryButton")
        self.reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_button.clicked.connect(self.reset_session)
        self.overlay_button = QPushButton("Mostrar overlay")
        self.overlay_button.setObjectName("secondaryButton")
        self.overlay_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overlay_button.clicked.connect(self.toggle_overlay)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addStretch()
        actions.addWidget(self.overlay_button)
        actions.addWidget(self.reset_button)
        outer.addLayout(actions)

        self.start_button.setFocus()

    def _stat_card(self, row, title, value, tone):
        card = QFrame()
        card.setObjectName("statCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(7)
        dot = QLabel("●")
        dot.setObjectName("statDot")
        dot.setProperty("tone", tone)
        caption = QLabel(title)
        caption.setObjectName("statCaption")
        head.addWidget(dot)
        head.addWidget(caption)
        head.addStretch()
        number = QLabel(value)
        number.setObjectName("statValue")
        layout.addLayout(head)
        layout.addWidget(number)
        row.addWidget(card)
        return number

    # -- preferencias ------------------------------------------------------
    def _restore_preferences(self):
        limit = self.settings.value("session/loss_limit", 3, type=int)
        self.loss_limit.setValue(max(1, min(20, limit)))
        self._update_progress()

    # -- tema --------------------------------------------------------------
    def _on_theme_clicked(self, button):
        self._apply_theme(button.property("themeName"))

    def _apply_theme(self, name, persist=True):
        if name not in ("light", "dark"):
            name = "light"
        self.theme_name = name

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.main_stylesheet(theme.get_palette(name)))

        # Refrescar estados dinámicos que dependen de propiedades.
        _repolish(self.status_dot)
        _repolish(self.ocr_label)

        self._sync_theme_buttons()
        if persist:
            self.settings.setValue("appearance/theme", name)

    def _sync_theme_buttons(self):
        for name, button in self.theme_buttons.items():
            button.setChecked(name == self.theme_name)

    def _on_loss_limit_changed(self, value):
        self.settings.setValue("session/loss_limit", value)
        self._update_progress()

    def _update_progress(self):
        limit = self.loss_limit.value()
        self.progress_bar.setMaximum(limit)
        self.progress_bar.setValue(min(self.streak, limit))
        self.progress_text.setText(f"{min(self.streak, limit)} / {limit}")

    def _set_overlay_scale_from_id(self, value):
        self.overlay.set_scale(value / 100)
        if not self.overlay.isVisible():
            self.overlay.show()
            self.overlay.raise_()

    def _on_overlay_scale_changed(self, scale):
        self.overlay_scale_label.setText(f"{round(scale * 100)} %")
        match = None
        for button in self.overlay_group.buttons():
            preset_value = self.overlay_group.id(button) / 100
            if abs(preset_value - scale) < 0.01:
                match = button
                break
        if match is not None:
            match.setChecked(True)
        else:
            self.overlay_group.setExclusive(False)
            for button in self.overlay_group.buttons():
                button.setChecked(False)
            self.overlay_group.setExclusive(True)

    def _on_overlay_visibility_changed(self, visible):
        self.overlay_button.setText(
            "Ocultar overlay" if visible else "Mostrar overlay"
        )

    def _reset_overlay_position(self):
        self.overlay.reset_position()
        if not self.overlay.isVisible():
            self.overlay.show()
            self.overlay.raise_()

    def _show_overlay_at_start(self):
        self.overlay.show()
        self.overlay.raise_()

    # -- detección ---------------------------------------------------------
    def start_detection(self):
        if self.detector_thread and self.detector_thread.isRunning():
            return
        self.detector_thread = DetectorThread(self.loss_limit.value())
        self.detector_thread.status_changed.connect(self.set_status)
        self.detector_thread.ocr_changed.connect(self._on_ocr_changed)
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
        self.status_dot.setProperty("active", active)
        _repolish(self.status_dot)
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
        self._update_progress()

    def add_result(self, result, wins, losses, streak):
        self.update_stats(wins, losses, streak)
        if result == "derrota":
            self.defeat_sound.play()
        label = "Victoria" if result == "victoria" else "Derrota"
        tone = "win" if result == "victoria" else "loss"
        self._add_activity_row(label, tone, time.strftime("%H:%M:%S"))

    def _add_activity_row(self, label, tone, time_text):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        dot = QLabel("●")
        dot.setObjectName("activityDot")
        dot.setProperty("tone", tone)
        name = QLabel(label)
        name.setObjectName("activityResult")
        when = QLabel(time_text)
        when.setObjectName("activityTime")
        layout.addWidget(dot)
        layout.addWidget(name)
        layout.addStretch()
        layout.addWidget(when)

        self.activity_rows_layout.insertWidget(0, row)
        self.activity_rows.insert(0, row)
        self.activity_placeholder.hide()

        while len(self.activity_rows) > 5:
            old = self.activity_rows.pop()
            self.activity_rows_layout.removeWidget(old)
            old.deleteLater()

    def _clear_activity(self):
        for row in self.activity_rows:
            self.activity_rows_layout.removeWidget(row)
            row.deleteLater()
        self.activity_rows.clear()
        self.activity_placeholder.show()

    def _on_ocr_changed(self, text):
        self._set_ocr_text(text, False)

    def _set_ocr_text(self, text, error):
        self.ocr_label.setText(text)
        self.ocr_label.setProperty("error", error)
        _repolish(self.ocr_label)

    def show_rest_alert(self, streak):
        dialog = RestDialog(streak, self)
        dialog.show()
        # Deja terminar primero el sonido de derrota si ambos eventos coinciden.
        QTimer.singleShot(450, self.rest_sound.play)

    def show_error(self, message):
        self.set_status("Error del detector")
        self._set_ocr_text(message, True)

    def reset_session(self):
        if self.detector_thread and self.detector_thread.isRunning():
            self.stop_detection()
            self.detector_thread.wait(2000)
            self.on_detection_finished()
        self.wins = self.losses = self.streak = 0
        self._clear_activity()
        self.update_stats(0, 0, 0)
        self._set_ocr_text("Sesión reiniciada. Lista para empezar.", False)
        self.set_status("Listo para empezar")

    def toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show()
            self.overlay.raise_()

    def closeEvent(self, event):
        if self.detector_thread and self.detector_thread.isRunning():
            self.detector_thread.requestInterruption()
            self.detector_thread.wait(2500)
        self.settings.setValue("session/loss_limit", self.loss_limit.value())
        self.overlay.save_now()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("OverTilt")
    app.setApplicationName("OverTilt")
    app.setStyle("Fusion")
    app.setFont(QFont(theme.FONT_FAMILY, 10))
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "overtilt.png")))

    settings = QSettings()
    saved_theme = settings.value("appearance/theme", "light")
    if saved_theme not in ("light", "dark"):
        saved_theme = "light"
    app.setStyleSheet(theme.main_stylesheet(theme.get_palette(saved_theme)))

    window = OverTiltWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
