import json

import cv2
import mss
import numpy as np


VENTANA = "Calibrador Overwatch 1080p"

# Estado del recuadro que dibuja el usuario.
ref_pt = []
selecting = False
image_copy = None


def click_and_crop(event, x, y, flags, param):
    global ref_pt, selecting

    if event == cv2.EVENT_LBUTTONDOWN:
        ref_pt = [(x, y)]
        selecting = True

    elif event == cv2.EVENT_MOUSEMOVE and selecting:
        img_temp = image_copy.copy()
        cv2.rectangle(img_temp, ref_pt[0], (x, y), (0, 255, 0), 2)
        cv2.imshow(VENTANA, img_temp)

    elif event == cv2.EVENT_LBUTTONUP:
        ref_pt.append((x, y))
        selecting = False

        # Dibujar rectángulo final
        cv2.rectangle(image_copy, ref_pt[0], ref_pt[1], (0, 255, 0), 2)
        cv2.imshow(VENTANA, image_copy)


def main():
    global image_copy, ref_pt

    # 1. Cargar una captura de pantalla a 1080p o capturar el escritorio actual
    # Si tienes una imagen guardada: image = cv2.imread("captura_1080p.png")
    # De lo contrario, tomamos una captura directa de la pantalla:
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Monitor principal 1080p
        sct_img = sct.grab(monitor)
        image = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)

    image_copy = image.copy()
    cv2.namedWindow(VENTANA)
    cv2.setMouseCallback(VENTANA, click_and_crop)

    print("[+] Haz clic e ingresa un recuadro sobre las letras de VICTORIA / DERROTA.")
    print("[+] Presiona 'C' para confirmar y guardar las coordenadas.")
    print("[+] Presiona 'R' para reiniciar la selección.")

    while True:
        cv2.imshow(VENTANA, image_copy)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("r"):
            image_copy = image.copy()
            ref_pt = []
        elif key == ord("c") and len(ref_pt) == 2:
            break

    cv2.destroyAllWindows()

    if len(ref_pt) != 2:
        raise SystemExit("No se seleccionó ningún recuadro. Vuelve a ejecutar el calibrador.")

    # 2. Calcular los valores exactos para mss
    x1, y1 = ref_pt[0]
    x2, y2 = ref_pt[1]

    left = min(x1, x2)
    top = min(y1, y2)
    width = abs(x2 - x1)
    height = abs(y2 - y1)

    bbox_config = {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
    }

    print("\n--------------------------------------------------")
    print("¡COORDENADAS CALIBRADAS PARA MSS (1080p)! :")
    print(json.dumps(bbox_config, indent=4))
    print("--------------------------------------------------")
    print(
        "Copia estos valores en crear_region() de Overtilt.py "
        "(la referencia interna es 1920x1080)."
    )


if __name__ == "__main__":
    main()
