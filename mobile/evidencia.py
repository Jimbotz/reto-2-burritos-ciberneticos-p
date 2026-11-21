from hashlib import sha256
from io import BytesIO
from math import asin, cos, radians, sin, sqrt

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from .catalogos import coords


register_heif_opener()
MAX_IMAGEN = 12 * 1024 * 1024


def distancia_m(lat1, lon1, lat2, lon2):
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 12_742_000 * asin(sqrt(min(1.0, a)))


def gps_exif(imagen):
    try:
        gps = imagen.getexif().get_ifd(34853)
        if gps.get(1) not in ("N", "S") or gps.get(3) not in ("E", "W"):
            return None
        lat, lon = [sum(float(value) / 60**i for i, value in enumerate(gps[k])) for k in (2, 4)]
        return coords(lat if gps[1] == "N" else -lat, lon if gps[3] == "E" else -lon)
    except (AttributeError, KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


def normalizar_foto(archivo):
    contenido = archivo.read(MAX_IMAGEN + 1)
    if not contenido or len(contenido) > MAX_IMAGEN:
        raise ValueError("Cada imagen debe pesar entre 1 byte y 12 MB.")
    try:
        with Image.open(BytesIO(contenido)) as imagen:
            if imagen.format not in ("JPEG", "PNG", "WEBP", "HEIF"):
                raise ValueError("Sube una foto JPG, PNG, WebP o HEIC.")
            if imagen.width * imagen.height > 30_000_000 or min(imagen.size) < 128:
                raise ValueError("La foto debe tener al menos 128 px por lado y hasta 30 megapíxeles.")
            ubicacion = gps_exif(imagen)
            # Reduce la decodificación de JPEG de alta resolución antes de corregir la orientación.
            if imagen.format == "JPEG":
                imagen.draft("RGB", (2048, 2048))
            foto = ImageOps.exif_transpose(imagen).convert("RGB")
            foto.thumbnail((2048, 2048))
            salida = BytesIO()
            foto.save(salida, format="JPEG", quality=88)
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError("La foto no se pudo abrir. Tómala de nuevo.") from error
    return salida.getvalue(), sha256(contenido).hexdigest(), ubicacion
