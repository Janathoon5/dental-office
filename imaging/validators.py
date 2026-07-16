from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_UPLOAD_MB = 10
ALLOWED_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'heic']

_extension_validator = FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS)


def validate_dental_image(uploaded_file):
    """Shared by the staff and patient upload forms so the same rules apply
    to X-rays and patient-submitted photos alike."""
    _extension_validator(uploaded_file)

    if uploaded_file.size > MAX_IMAGE_UPLOAD_MB * 1024 * 1024:
        raise ValidationError(f'Image must be smaller than {MAX_IMAGE_UPLOAD_MB}MB.')

    # Content-sniff so a renamed non-image file can't pass on extension alone.
    try:
        Image.open(uploaded_file).verify()
    except UnidentifiedImageError:
        raise ValidationError('This file is not a valid image.')
    finally:
        uploaded_file.seek(0)
