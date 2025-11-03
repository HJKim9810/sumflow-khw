from PIL import Image, ImageOps, ImageEnhance
import numpy as np

def preprocess_pillow(pil_img: Image.Image, mode="sauvola") -> Image.Image:
    img = pil_img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = ImageEnhance.Sharpness(img).enhance(1.1)
    if mode == "sauvola":
        try:
            from skimage.filters import threshold_sauvola
            arr = np.array(img)
            th  = threshold_sauvola(arr, 25)
            img = Image.fromarray(((arr > th)*255).astype("uint8"))
        except Exception:
            img = img.point(lambda x: 255 if x > 180 else 0)
    else:
        img = img.point(lambda x: 255 if x > 180 else 0)
    img = ImageOps.expand(img, border=8, fill=255)
    return img