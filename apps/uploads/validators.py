from django.core.exceptions import ValidationError

from PIL import Image

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024

#: Pillow's name for each accepted image format -> the extension it is saved with. No SVG: it can carry scripts.
IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}


def _check_size(file, limit, what):
    if file.size > limit:
        mb = limit // (1024 * 1024)
        raise ValidationError(
            {"file": ValidationError(f"{what} can be at most {mb} MB.", code="too_large", params={"mb": mb})}
        )


def image_extension(file) -> str:
    """The extension a real JPG, PNG, WebP or GIF image is saved with; the name it came with is not trusted."""
    _check_size(file, MAX_IMAGE_BYTES, "An image")
    try:
        with Image.open(file) as image:
            found = image.format
            image.verify()
    except Exception as exc:
        raise ValidationError(
            {"file": ValidationError("That file is not an image we can read.", code="unreadable")}
        ) from exc
    finally:
        file.seek(0)
    if found not in IMAGE_FORMATS:
        raise ValidationError({"file": ValidationError("Upload a JPG, PNG, WebP or GIF image.", code="wrong_type")})
    return IMAGE_FORMATS[found]


def pdf_extension(file) -> str:
    _check_size(file, MAX_PDF_BYTES, "A PDF")
    header = file.read(5)
    file.seek(0)
    if header != b"%PDF-":
        raise ValidationError({"file": ValidationError("That file is not a PDF.", code="not_pdf")})
    return "pdf"


#: What may be uploaded, and how each is checked.
KINDS = {"image": image_extension, "pdf": pdf_extension}
