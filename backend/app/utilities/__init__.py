"""Lazy exports for utility helpers.

Keeping this package lightweight lets focused modules, such as URL helpers,
be imported without pulling in optional API/imaging dependencies.
"""

_UTILITY_EXPORTS = {
    "ensure_directory_exists",
    "generate_study_instance_uid",
    "embed_dicom_header",
    "save_file_to_output_dir",
    "decode_pixel_data",
    "extract_metadata",
    "generate_download_url",
    "validate_dicom_headers",
    "detect_mime_type_from_extension",
    "detect_mime_type_from_content",
    "generate_thumbnail",
}

__all__ = sorted(_UTILITY_EXPORTS)


def __getattr__(name: str):
    if name in _UTILITY_EXPORTS:
        from . import utilities

        return getattr(utilities, name)
    raise AttributeError(f"module 'app.utilities' has no attribute {name!r}")
