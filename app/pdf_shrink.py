"""Make supplier datasheet PDFs smaller before they are stored.

European catalogue PDFs are often several MB because of full-resolution
product photos. Photos are scaled down to at most MAX_PX on the long side and
saved as JPEG at QUALITY; page contents are compressed. Text and drawings
stay sharp (they are vectors). The original is kept when shrinking doesn't
help or anything goes wrong.
"""
import io

from PIL import Image
from pypdf import PdfReader, PdfWriter

MAX_PX = 1600
QUALITY = 65
MIN_PIXELS = 250 * 250  # leave icons and small logos alone


def shrink_pdf(data: bytes) -> bytes:
    try:
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
        for page in writer.pages:
            for img in page.images:
                try:
                    xobj = img.indirect_reference.get_object() if img.indirect_reference else None
                    if xobj is not None and ("/SMask" in xobj or "/Mask" in xobj):
                        continue  # has transparency: re-encoding as JPEG would lose it
                    im = img.image
                    if im.width * im.height < MIN_PIXELS:
                        continue
                    if im.mode not in ("RGB", "L"):
                        im = im.convert("RGB")
                    if max(im.size) > MAX_PX:
                        im.thumbnail((MAX_PX, MAX_PX), Image.LANCZOS)
                    img.replace(im, quality=QUALITY)
                except Exception:
                    continue  # unusual image format: keep it as it is
            page.compress_content_streams()
        out = io.BytesIO()
        writer.write(out)
        smaller = out.getvalue()
        # Must still open, and be worth it
        if len(PdfReader(io.BytesIO(smaller)).pages) and len(smaller) < len(data) * 0.95:
            return smaller
    except Exception:
        pass
    return data
