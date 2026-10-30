"""Sistema de diseño de OverTilt: paleta, tipografía y hojas de estilo."""

from __future__ import annotations

from dataclasses import dataclass

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"

# --- Overlay -----------------------------------------------------------------
OVERLAY_BASE_WIDTH = 390
OVERLAY_BASE_HEIGHT = 116
OVERLAY_MIN_SCALE = 0.75
OVERLAY_MAX_SCALE = 1.75
OVERLAY_PRESETS = (
    ("Compacto", 0.80),
    ("Normal", 1.00),
    ("Grande", 1.25),
    ("Extra", 1.50),
)


@dataclass(frozen=True)
class Palette:
    """Colores de un tema cerrado de la interfaz principal."""

    background: str
    surface: str
    surface_alt: str
    surface_pressed: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_soft: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    primary_text: str
    win: str
    loss: str
    streak: str
    disabled: str
    disabled_border: str
    disabled_surface: str
    progress_bg: str
    ocr_text: str
    primary_disabled: str
    primary_disabled_text: str


LIGHT = Palette(
    background="#F4F6F4",
    surface="#FFFFFF",
    surface_alt="#EDF2EF",
    surface_pressed="#E2EAE6",
    border="#DDE5E1",
    border_strong="#C9D5CF",
    text="#1F2A2A",
    text_muted="#677774",
    text_soft="#8A9995",
    accent="#3E7A6A",
    accent_hover="#326456",
    accent_pressed="#295448",
    accent_soft="#E4F0EA",
    primary_text="#FFFFFF",
    win="#4E8267",
    loss="#B26B63",
    streak="#A9843F",
    disabled="#A9B5B1",
    disabled_border="#E3EAE7",
    disabled_surface="#F7F9F8",
    progress_bg="#E8EEEB",
    ocr_text="#4C5C58",
    primary_disabled="#DCE6E1",
    primary_disabled_text="#93A29D",
)

DARK = Palette(
    background="#11181A",
    surface="#172022",
    surface_alt="#1E2A2C",
    surface_pressed="#253235",
    border="#293738",
    border_strong="#3A4A4C",
    text="#E7EFEC",
    text_muted="#9CAEA9",
    text_soft="#7C8F8A",
    accent="#7CBFAA",
    accent_hover="#93D3BE",
    accent_pressed="#67A992",
    accent_soft="#223630",
    primary_text="#0E1714",
    win="#83C4A7",
    loss="#DB9A93",
    streak="#D7BA80",
    disabled="#647470",
    disabled_border="#2E3C3E",
    disabled_surface="#141C1E",
    progress_bg="#243133",
    ocr_text="#B9CAC4",
    primary_disabled="#243330",
    primary_disabled_text="#6F807B",
)


def get_palette(name: str) -> Palette:
    """Devuelve la paleta del tema indicado; claro si no se reconoce."""
    return DARK if name == "dark" else LIGHT


def main_stylesheet(p: Palette) -> str:
    """Hoja de estilo de la aplicación principal y sus diálogos."""
    return f"""
        QMainWindow {{ background-color: {p.background}; }}

        QWidget {{
            color: {p.text};
            font-family: "{FONT_FAMILY}";
            font-size: 13px;
        }}

        QLabel {{ background: transparent; }}

        QFrame#statCard, QFrame#panel {{
            background: {p.surface};
            border: 1px solid {p.border};
            border-radius: 12px;
        }}

        QLabel#logo {{ background: transparent; }}

        QLabel#brand {{ color: {p.text}; }}
        QLabel#tagline {{ color: {p.text_soft}; }}

        QFrame#statusPill {{
            background: {p.surface};
            border: 1px solid {p.border};
            border-radius: 15px;
        }}
        QLabel#statusDot {{
            background: {p.disabled};
            border-radius: 4px;
            min-width: 8px;
            max-width: 8px;
            min-height: 8px;
            max-height: 8px;
        }}
        QLabel#statusDot[active="true"] {{ background: {p.accent}; }}
        QLabel#statusLabel {{ color: {p.text_muted}; font-size: 12px; font-weight: 600; }}

        QFrame#themeSwitch {{
            background: {p.surface};
            border: 1px solid {p.border};
            border-radius: 15px;
        }}
        QPushButton#themeOption {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 11px;
            padding: 5px 12px;
            font-size: 11px;
            font-weight: 600;
            color: {p.text_muted};
        }}
        QPushButton#themeOption:hover {{
            background: {p.surface_alt};
            color: {p.text};
        }}
        QPushButton#themeOption:checked {{
            background: {p.accent};
            border-color: {p.accent};
            color: {p.primary_text};
        }}
        QPushButton#themeOption:focus {{
            border-color: {p.accent_pressed};
        }}

        QLabel#pageTitle {{ color: {p.text}; font-size: 26px; font-weight: 600; }}
        QLabel#subtitle {{ color: {p.text_muted}; font-size: 13px; }}
        QLabel#muted {{ color: {p.text_muted}; font-size: 12px; }}
        QLabel#hint {{ color: {p.text_soft}; font-size: 11px; }}
        QLabel#sectionTitle {{ color: {p.text}; font-size: 13px; font-weight: 600; }}
        QLabel#fieldLabel {{ color: {p.text}; font-size: 12px; font-weight: 600; }}
        QLabel#scaleValue {{ color: {p.accent}; font-size: 12px; font-weight: 600; }}

        QLabel#statCaption {{ color: {p.text_muted}; font-size: 10px; font-weight: 600; }}
        QLabel#statValue {{ color: {p.text}; font-size: 30px; font-weight: 600; }}
        QLabel#statDot {{ font-size: 9px; }}
        QLabel#statDot[tone="win"] {{ color: {p.win}; }}
        QLabel#statDot[tone="loss"] {{ color: {p.loss}; }}
        QLabel#statDot[tone="streak"] {{ color: {p.streak}; }}

        QFrame#divider {{ background: {p.border}; border: none; max-height: 1px; }}

        QProgressBar {{
            background: {p.progress_bg};
            border: none;
            border-radius: 4px;
            min-height: 8px;
            max-height: 8px;
        }}
        QProgressBar::chunk {{ background: {p.accent}; border-radius: 4px; }}
        QLabel#progressText {{ color: {p.accent}; font-size: 12px; font-weight: 600; }}

        QLabel#stepperValue {{
            background: {p.surface};
            border: 1px solid {p.border_strong};
            border-radius: 8px;
            padding: 0px 12px;
            color: {p.text};
            font-size: 13px;
            font-weight: 600;
            min-width: 104px;
            min-height: 34px;
            max-height: 36px;
        }}
        QLabel#stepperValue:disabled {{
            color: {p.disabled};
            background: {p.disabled_surface};
            border-color: {p.disabled_border};
        }}

        QPushButton#stepperButton {{
            min-width: 34px;
            max-width: 34px;
            min-height: 36px;
            max-height: 36px;
            padding: 0px;
            font-size: 16px;
            font-weight: 600;
            background: {p.surface};
            border: 1px solid {p.border_strong};
            border-radius: 8px;
            color: {p.text_muted};
        }}
        QPushButton#stepperButton:hover {{
            background: {p.surface_alt};
            color: {p.text};
        }}
        QPushButton#stepperButton:pressed {{ background: {p.surface_pressed}; }}
        QPushButton#stepperButton:disabled {{
            color: {p.disabled};
            background: {p.disabled_surface};
            border-color: {p.disabled_border};
        }}

        QPushButton {{
            background: {p.surface};
            border: 1px solid {p.border_strong};
            border-radius: 8px;
            padding: 9px 18px;
            font-weight: 600;
            color: {p.text};
        }}
        QPushButton:hover {{ background: {p.surface_alt}; }}
        QPushButton:pressed {{ background: {p.surface_pressed}; }}
        QPushButton:focus {{ border-color: {p.accent}; }}
        QPushButton:disabled {{
            color: {p.disabled};
            border-color: {p.disabled_border};
            background: {p.disabled_surface};
        }}

        QPushButton#primaryButton {{
            background: {p.accent};
            border-color: {p.accent};
            color: {p.primary_text};
        }}
        QPushButton#primaryButton:hover {{
            background: {p.accent_hover};
            border-color: {p.accent_hover};
        }}
        QPushButton#primaryButton:pressed {{
            background: {p.accent_pressed};
            border-color: {p.accent_pressed};
        }}
        QPushButton#primaryButton:focus {{
            background: {p.accent_hover};
            border-color: {p.accent_pressed};
        }}
        QPushButton#primaryButton:disabled {{
            background: {p.primary_disabled};
            border-color: {p.primary_disabled};
            color: {p.primary_disabled_text};
        }}

        QPushButton#presetButton {{
            background: {p.disabled_surface};
            border: 1px solid {p.border};
            border-radius: 7px;
            padding: 6px 12px;
            font-size: 12px;
            font-weight: 600;
            color: {p.text_muted};
        }}
        QPushButton#presetButton:hover {{
            background: {p.surface_alt};
            color: {p.text};
        }}
        QPushButton#presetButton:checked {{
            background: {p.accent_soft};
            border-color: {p.accent};
            color: {p.accent_pressed};
        }}

        QPushButton#ghostButton {{
            background: transparent;
            border: none;
            color: {p.text_muted};
            padding: 6px 10px;
            font-size: 12px;
        }}
        QPushButton#ghostButton:hover {{
            background: {p.accent_soft};
            color: {p.accent_pressed};
        }}

        QLabel#activityResult {{ font-size: 12px; font-weight: 600; }}
        QLabel#activityTime {{ color: {p.text_soft}; font-size: 11px; }}
        QLabel#activityDot {{ font-size: 9px; }}
        QLabel#activityDot[tone="win"] {{ color: {p.win}; }}
        QLabel#activityDot[tone="loss"] {{ color: {p.loss}; }}

        QLabel#ocrText {{
            color: {p.ocr_text};
            font-family: "{MONO_FAMILY}";
            font-size: 11px;
        }}
        QLabel#ocrText[error="true"] {{ color: {p.loss}; }}

        QDialog#restDialog {{ background: {p.surface}; }}
        QLabel#dialogBadge {{
            background: {p.accent_soft};
            color: {p.accent};
            border-radius: 22px;
            font-size: 14px;
            font-weight: 700;
        }}
        QLabel#dialogTitle {{ color: {p.text}; font-size: 19px; font-weight: 600; }}
        QLabel#dialogBody {{ color: {p.text_muted}; font-size: 13px; }}

        QMenu {{
            background: {p.surface};
            border: 1px solid {p.border};
            border-radius: 8px;
            padding: 6px;
        }}
        QMenu::item {{
            color: {p.text};
            padding: 7px 26px 7px 14px;
            border-radius: 6px;
        }}
        QMenu::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
        QMenu::item:disabled {{ color: {p.disabled}; }}
        QMenu::separator {{
            height: 1px;
            background: {p.border};
            margin: 6px 10px;
        }}

        QToolTip {{
            background: {p.surface};
            color: {p.text};
            border: 1px solid {p.border};
            padding: 6px 8px;
        }}
    """


def overlay_stylesheet(scale: float) -> str:
    """Hoja de estilo del overlay, escalada según su tamaño."""

    def px(value: float) -> int:
        return max(1, round(value * scale))

    def font_px(value: float) -> int:
        return max(8, round(value * scale))

    return f"""
        QWidget#overlayRoot {{ background: transparent; }}

        QFrame#overlayPanel {{
            background: rgba(16, 24, 25, 224);
            border: 1px solid rgba(163, 196, 184, 42);
            border-radius: {px(15)}px;
        }}

        QLabel#overlayBrand {{ color: #EDF4F1; }}
        QLabel#overlayState {{
            color: #93A6A0;
            font-size: {font_px(8)}px;
            font-weight: 600;
        }}
        QLabel#overlayState[running="true"] {{ color: #9ACBB9; }}

        QLabel#overlayMetricCaption {{
            color: #8FA39D;
            font-size: {font_px(8)}px;
            font-weight: 600;
        }}
        QLabel#overlayMetricValue {{
            color: #EDF4F1;
            font-size: {font_px(22)}px;
            font-weight: 600;
        }}
        QWidget[tone="win"] QLabel#overlayMetricValue {{ color: #9ACBB9; }}
        QWidget[tone="loss"] QLabel#overlayMetricValue {{ color: #E5A19A; }}
        QWidget[tone="streak"] QLabel#overlayMetricValue {{ color: #DCBE84; }}

        QPushButton#overlayHide {{
            background: rgba(255, 255, 255, 14);
            color: #D5E0DC;
            border: none;
            padding: 0px;
            border-radius: {px(12)}px;
            font-size: {px(17)}px;
            font-weight: 600;
        }}
        QPushButton#overlayHide:hover {{
            background: rgba(229, 161, 154, 130);
            color: #FFFFFF;
        }}
        QPushButton#overlayHide:pressed {{
            background: rgba(229, 161, 154, 190);
        }}
    """
