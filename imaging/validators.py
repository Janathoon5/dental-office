from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_UPLOAD_MB = 10
# HEIC isn't listed here: Pillow can't decode it without the optional
# pillow-heif plugin, which isn't installed, so a real .heic upload would
# always fail the content-sniff below despite being a valid image.
ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png']

_extension_validator = FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)


def validate_dental_image(uploaded_file):
    """Shared by the staff and patient upload forms so the same rules apply
    to X-rays and patient-submitted photos alike."""
    _extension_validator(uploaded_file)

    if uploaded_file.size > MAX_IMAGE_UPLOAD_MB * 1024 * 1024:
        raise ValidationError(f'Image must be smaller than {MAX_IMAGE_UPLOAD_MB}MB.')

    # Content-sniff so a renamed non-image file can't pass on extension alone.
    # Pillow raises more than just UnidentifiedImageError on hostile/corrupt
    # input (e.g. DecompressionBombError on a tiny file with a spoofed huge
    # resolution, OSError/SyntaxError on a truncated file) — all of those mean
    # "reject the upload", not "500 the request".
    try:
        Image.open(uploaded_file).verify()
    except UnidentifiedImageError:
        raise ValidationError('This file is not a valid image.')
    except Exception:
        raise ValidationError('This file could not be read as an image.')
    finally:
        uploaded_file.seek(0)
