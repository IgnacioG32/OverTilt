import argparse
import os
import re
import shutil
import time
import tkinter as tk
from collections import deque
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from mss import mss


# Rutas habituales del instalador de Tesseract en Windows.
RUTAS_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)
_tesseract_configurado = False


def localizar_tesseract():
    """Busca el ejecutable de Tesseract y devuelve su ruta, o None si no existe."""
    candidatos = [
        os.environ.get("TESSERACT_CMD"),
        shutil.which("tesseract"),
        *RUTAS_TESSERACT,
    ]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidatos.append(
            str(Path(local_appdata) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
        )

    for candidato in candidatos:
        if candidato and Path(candidato).is_file():
            return str(Path(candidato))
    return None


def configurar_tesseract():
    """Configura pytesseract una sola vez y falla con un mensaje accionable."""
    global _tesseract_configurado
    if _tesseract_configurado:
        return pytesseract.pytesseract.tesseract_cmd

    ruta = localizar_tesseract()
    if ruta is None:
        raise RuntimeError(
            "No se encontró Tesseract OCR. Instálalo desde "
            "https://github.com/UB-Mannheim/tesseract/wiki o define la variable "
            "de entorno TESSERACT_CMD con la ruta completa a tesseract.exe."
        )

    pytesseract.pytesseract.tesseract_cmd = ruta
    _tesseract_configurado = True
    return ruta


class DetectorResultado:
    """Evita contar varias veces un mismo resultado que permanece en pantalla."""

    def __init__(self, lecturas_para_confirmar=2, tamano_ventana=5, lecturas_para_rearmar=4):
        self.lecturas_para_confirmar = lecturas_para_confirmar
        self.historial = deque(maxlen=tamano_ventana)
        self.lecturas_para_rearmar = lecturas_para_rearmar
        self.lecturas_sin_resultado = 0
        self.armado = True

    @staticmethod
    def buscar_resultado(texto):
        texto = texto.upper()
        palabras = re.findall(r"[A-Z]+", texto)
        objetivos = {
            "VICTORIA": "victoria",
            "VICTORY": "victoria",
            "DERROTA": "derrota",
            "DEFEAT": "derrota",
        }
        for palabra in palabras:
            if palabra in objetivos:
                return objetivos[palabra]
            # Tesseract suele confundir un par de letras en la tipografía inclinada.
            if len(palabra) >= 5:
                coincidencia = max(
                    (SequenceMatcher(None, palabra, objetivo).ratio(), resultado)
                    for objetivo, resultado in objetivos.items()
                )
                # El banner de derrota suele producir errores como DERROTR o DERRGTH.
                # El recorte está limitado al banner, así que se admite una similitud menor.
                if coincidencia[0] >= 0.66:
                    return coincidencia[1]
        return None

    def actualizar(self, texto):
        resultado = self.buscar_resultado(texto)
        self.historial.append(resultado)
        if resultado is None:
            self.lecturas_sin_resultado += 1
            if self.lecturas_sin_resultado >= self.lecturas_para_rearmar:
                self.armado = True
            return None

        self.lecturas_sin_resultado = 0
        coincidencias = sum(item == resultado for item in self.historial)
        if self.armado and coincidencias >= self.lecturas_para_confirmar:
            self.armado = False
            return resultado
        return None


class ContadorSesion:
    def __init__(self, limite_derrotas):
        self.limite_derrotas = limite_derrotas
        self.victorias = 0
        self.derrotas = 0
        self.racha_derrotas = 0
        self.aviso_mostrado = False

    def registrar(self, resultado):
        if resultado == "victoria":
            self.victorias += 1
            self.racha_derrotas = 0
            self.aviso_mostrado = False
            return False

        self.derrotas += 1
        self.racha_derrotas += 1
        if (
            self.racha_derrotas >= self.limite_derrotas
            and not self.aviso_mostrado
        ):
            self.aviso_mostrado = True
            return True
        return False


def mostrar_aviso_descanso(ventana, racha_derrotas):
    """Muestra un aviso no modal para que la captura continúe ejecutándose."""
    aviso = tk.Toplevel(ventana)
    aviso.title("OverTilt - Tómate un descanso")
    aviso.attributes("-topmost", True)
    aviso.resizable(False, False)
    aviso.protocol("WM_DELETE_WINDOW", aviso.destroy)

    mensaje = (
        f"Llevas {racha_derrotas} derrotas consecutivas.\n"
        "Considera dejar de jugar un rato y tomarte un descanso."
    )
    tk.Label(aviso, text=mensaje, padx=24, pady=18, justify="center").pack()
    tk.Button(aviso, text="Entendido", command=aviso.destroy).pack(pady=(0, 14))

    aviso.update_idletasks()
    ancho = aviso.winfo_width()
    alto = aviso.winfo_height()
    x = (aviso.winfo_screenwidth() - ancho) // 2
    y = (aviso.winfo_screenheight() - alto) // 3
    aviso.geometry(f"+{x}+{y}")
    # Se cierra solo después de 15 segundos; el usuario también puede cerrarlo antes.
    aviso.after(15000, lambda: aviso.destroy() if aviso.winfo_exists() else None)
    return aviso


def crear_region(monitor):
    # Región calibrada con MSS para 1920x1080; se escala en otras resoluciones.
    escala_x = monitor["width"] / 1920
    escala_y = monitor["height"] / 1080
    left = round(669 * escala_x)
    top = round(431 * escala_y)
    width = round(621 * escala_x)
    height = round(214 * escala_y)

    # Mantiene la región dentro del monitor incluso con resoluciones poco habituales.
    left = min(left, monitor["width"] - 1)
    top = min(top, monitor["height"] - 1)
    width = min(width, monitor["width"] - left)
    height = min(height, monitor["height"] - top)
    return {
        "top": monitor["top"] + top,
        "left": monitor["left"] + left,
        "width": width,
        "height": height,
    }


def analizar_frame(frame_bgra):
    configurar_tesseract()
    frame_bgr = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2BGR)
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

    # Colores usados por el texto de resultado en la interfaz del juego.
    lower_blue = np.array([85, 100, 100])
    upper_blue = np.array([135, 255, 255])
    mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)

    lower_red1 = np.array([0, 120, 120])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 120, 120])
    upper_red2 = np.array([180, 255, 255])
    mask_red = cv2.inRange(hsv, lower_red1, upper_red1) + cv2.inRange(
        hsv, lower_red2, upper_red2
    )

    # Overwatch muestra el texto de victoria en amarillo/dorado.
    lower_yellow = np.array([15, 100, 120])
    upper_yellow = np.array([40, 255, 255])
    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)

    combined_mask = cv2.bitwise_or(cv2.bitwise_or(mask_blue, mask_red), mask_yellow)

    # El bbox de MSS ya está calibrado alrededor del banner. No recortamos por
    # color: el mapa puede compartir el color del texto u ocultar algunos trazos.
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    enlarged_gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    adaptive_gray = cv2.adaptiveThreshold(
        enlarged_gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        41,
        7,
    )

    # Mantiene la máscara de color como una lectura paralela, no como filtro obligatorio.
    color_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    color_gray = cv2.bitwise_and(color_gray, color_gray, mask=combined_mask)
    enlarged_color = cv2.resize(color_gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    color_binary = cv2.threshold(
        enlarged_color, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )[1]

    config = r"--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ¡!"
    text_gray = pytesseract.image_to_string(adaptive_gray, config=config).upper().strip()
    text_color = pytesseract.image_to_string(color_binary, config=config).upper().strip()
    texts = []
    if text_gray:
        texts.append(f"GRIS: {text_gray}")
    if text_color:
        texts.append(f"COLOR: {text_color}")
    text = "\n".join(texts)

    # La vista de depuración muestra la variante independiente del color.
    return frame_bgr, combined_mask, adaptive_gray, text


def capturar_y_analizar(limite_derrotas=3, mostrar_vista_previa=True, depurar_ocr=False):
    contador = ContadorSesion(limite_derrotas)
    detector = DetectorResultado()
    ventana = tk.Tk()
    ventana.withdraw()

    try:
        with mss() as sct:
            monitor = sct.monitors[1]
            bbox = crear_region(monitor)
            print(f"[+] Capturando la región central: {bbox}")
            if mostrar_vista_previa:
                print("[+] Pulsa 'q' en la vista previa para terminar.")
            else:
                print("[+] Pulsa Ctrl+C en la consola para terminar.")
            print(
                f"[+] El aviso de descanso aparecerá tras "
                f"{limite_derrotas} derrotas consecutivas."
            )
            print("[SESIÓN] Victorias: 0 | Derrotas: 0 | Racha: 0\n")
            ultimo_debug = 0.0

            while True:
                frame_bgra = np.array(sct.grab(bbox))
                frame_bgr, combined_mask, ocr_img, texto = analizar_frame(frame_bgra)
                resultado = detector.actualizar(texto)

                ahora = time.monotonic()
                if depurar_ocr and ahora - ultimo_debug >= 1.5:
                    print(f"[OCR EN VIVO] {texto.strip() or '(sin texto)'}")
                    ultimo_debug = ahora

                if resultado:
                    mostrar_aviso = contador.registrar(resultado)
                    if resultado == "victoria":
                        print("\n[RESULTADO] ¡Victoria detectada!")
                    else:
                        print("\n[RESULTADO] Derrota detectada.")

                    print(
                        f"[SESIÓN] Victorias: {contador.victorias} | "
                        f"Derrotas: {contador.derrotas} | "
                        f"Racha de derrotas: {contador.racha_derrotas}\n",
                        flush=True,
                    )

                    if mostrar_aviso:
                        mostrar_aviso_descanso(ventana, contador.racha_derrotas)

                # Atiende la ventana de aviso sin bloquear el bucle de captura/OCR.
                ventana.update_idletasks()
                ventana.update()

                if mostrar_vista_previa:
                    cv2.imshow("OverTilt - región capturada", frame_bgr)
                    cv2.imshow("OverTilt - filtro de color", combined_mask)
                    cv2.imshow("OverTilt - imagen enviada al OCR", ocr_img)
                    if cv2.waitKey(500) & 0xFF == ord("q"):
                        break
                else:
                    time.sleep(0.5)
    finally:
        cv2.destroyAllWindows()
        ventana.destroy()

    print(
        f"\n[FIN DE SESIÓN] Victorias: {contador.victorias} | "
        f"Derrotas: {contador.derrotas}"
    )


def probar_imagen(ruta):
    frame = cv2.imread(ruta)
    if frame is None:
        raise SystemExit(f"No se pudo abrir la imagen: {ruta}")
    frame_bgra = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
    original, mascara, ocr_img, texto = analizar_frame(frame_bgra)
    resultado = DetectorResultado.buscar_resultado(texto)
    print(f"[OCR] Texto reconocido: {texto.strip() or '(ninguno)'}")
    print(f"[DETECCIÓN] {resultado or 'sin resultado'}")
    cv2.imshow("Imagen de prueba", original)
    cv2.imshow("Máscara de color", mascara)
    cv2.imshow("Imagen enviada al OCR", ocr_img)
    print("Pulsa una tecla en una ventana para cerrar.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(
        description="Cuenta victorias y derrotas de Overwatch mediante OCR."
    )
    parser.add_argument(
        "--limite-derrotas",
        type=int,
        default=3,
        help="Racha de derrotas que activa el aviso de descanso (por defecto: 3).",
    )
    parser.add_argument(
        "--sin-vista-previa",
        action="store_true",
        help="Oculta las ventanas de depuración y captura en segundo plano.",
    )
    parser.add_argument(
        "--depurar-ocr",
        action="store_true",
        help="Imprime periódicamente el texto que Tesseract lee durante la captura.",
    )
    parser.add_argument(
        "--imagen-prueba",
        help="Analiza una imagen guardada y muestra lo que reconoce Tesseract.",
    )
    args = parser.parse_args()

    try:
        configurar_tesseract()
    except RuntimeError as error:
        parser.exit(1, f"Error: {error}\n")

    if args.imagen_prueba:
        probar_imagen(args.imagen_prueba)
        return

    if args.limite_derrotas < 1:
        parser.error("--limite-derrotas debe ser al menos 1")

    capturar_y_analizar(
        limite_derrotas=args.limite_derrotas,
        mostrar_vista_previa=not args.sin_vista_previa,
        depurar_ocr=args.depurar_ocr,
    )


if __name__ == "__main__":
    main()
