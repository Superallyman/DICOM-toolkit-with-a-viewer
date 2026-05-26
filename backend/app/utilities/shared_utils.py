# app/utilities/shared_utils.py
import numpy as np
from pydicom.pixel_data_handlers.util import apply_voi_lut
from fastapi import HTTPException
import logging
from pydicom.dataset import Dataset
from PIL import Image


def decode_pixel_data(dicom: Dataset) -> Image.Image:
    """
    Decode pixel data from a DICOM file, handling compressed formats.
    """
    try:
        # Ensure compressed data is decoded
        dicom.decode()

        # Fix potential Photometric Interpretation mismatch
        if dicom.PhotometricInterpretation == "RGB" and "JFIF" in dicom.PixelData.decode("latin-1"):
            logging.warning(
                f"Fixing Photometric Interpretation mismatch for {dicom.get('SOPInstanceUID', 'Unknown')}: "
                f"Setting to 'YBR_FULL_422'."
            )
            dicom.PhotometricInterpretation = "YBR_FULL_422"

        # Apply VOI LUT if present
        pixel_array = apply_voi_lut(dicom.pixel_array, dicom)

        # Normalize floating-point pixel data
        if pixel_array.dtype.kind == 'f':  # Check if dtype is floating-point
            pixel_array = (255 * (pixel_array - np.min(pixel_array)) / (np.max(pixel_array) - np.min(pixel_array))).astype(np.uint8)

        # Handle YBR_FULL_422 photometric interpretation
        if dicom.PhotometricInterpretation == 'YBR_FULL_422':
            return Image.fromarray(pixel_array, mode='YCbCr').convert('RGB')
        else:
            return Image.fromarray(pixel_array)
    except Exception as e:
        logging.error(f"Error decoding pixel data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to decode pixel data.")