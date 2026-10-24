from PIL import Image
from pathlib import Path

imagen = Image.open("rostros_nclub.png")

ids = ["VIP001", "REG001", "INV001", "EMP001", "EXT001"]

ancho, alto = imagen.size

for columna, person_id in enumerate(ids):
    for fila in range(3):

        x1 = round(columna * ancho / 5) + 5
        x2 = round((columna + 1) * ancho / 5) - 5

        y1 = round(fila * alto / 3) + 5
        y2 = round((fila + 1) * alto / 3) - 5

        rostro = imagen.crop((x1, y1, x2, y2))

        # Dos fotografías para registro y una para prueba
        tipo = "registro" if fila < 2 else "pruebas"

        carpeta = Path("dataset") / tipo / person_id
        carpeta.mkdir(parents=True, exist_ok=True)

        destino = carpeta / f"foto{fila + 1}.png"
        rostro.save(destino)

        print(f"Guardada: {destino}")

print("\n¡15 fotografías organizadas correctamente!")