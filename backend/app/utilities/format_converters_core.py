from reportlab.pdfgen import canvas  # Import added
from fastapi import HTTPException, UploadFile
from pydicom.pixel_data_handlers.util import apply_voi_lut
import os
import pydicom
from PIL import Image,ImageSequence
from pydicom import dcmwrite
from tifffile import imwrite
import numpy as np
import cv2
import logging
import shutil
from pydicom.uid import (
    ExplicitVRLittleEndian,
    generate_uid,
    PYDICOM_IMPLEMENTATION_UID
)
import fitz  # PyMuPDF for PDF manipulation
from app.utilities.utilities import decode_pixel_data, ensure_directory_exists
import uuid
from datetime import datetime

from pydicom.dataset import Dataset, FileDataset

logger = logging.getLogger(__name__)




def save_temp_file(upload_file: UploadFile, output_folder: str) -> str:
    """
    Save an uploaded file temporarily to the output folder.
    """
    try:
        input_path = os.path.join(output_folder, upload_file.filename)
        with open(input_path, "wb") as f:
            shutil.copyfileobj(upload_file.file, f)
        logging.info(f"Temporary file saved: {input_path}")
        return input_path
    except Exception as e:
        logging.error(f"Error saving temporary file: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save temporary file.")


def normalize_pixel_data(pixel_array):
    """
    Normalize pixel data to uint8 format.
    """
    if pixel_array.dtype.kind == "f":  # Floating-point data
        pixel_array = (
            255 * (pixel_array - np.min(pixel_array)) / (np.max(pixel_array) - np.min(pixel_array))
        ).astype(np.uint8)
    return pixel_array


def dicom_to_format(dicom_file: UploadFile, output_folder: str, format: str, quality: int = 95) -> str:
    """
    Convert DICOM to the specified format.
    """
    try:
        # Save uploaded DICOM file temporarily
        input_path = save_temp_file(dicom_file, output_folder)

        # Read DICOM file
        dicom = pydicom.dcmread(input_path, force=True)
        if not hasattr(dicom, "PixelData"):
            logging.error("DICOM file does not contain PixelData. Conversion aborted.")
            raise HTTPException(status_code=400, detail="DICOM file does not contain PixelData.")
        
        # Suppress Photometric Interpretation warnings and handle mismatch
        if dicom.PhotometricInterpretation == "RGB" and "JFIF" in dicom.PixelData.decode("latin-1"):
            logging.warning(
                f"Fixing Photometric Interpretation mismatch for {dicom.get('SOPInstanceUID', 'Unknown')}: "
                f"Setting to 'YBR_FULL_422'."
            )
            dicom.PhotometricInterpretation = "YBR_FULL_422"

        # Apply VOI LUT and normalize pixel data
        pixel_array = apply_voi_lut(dicom.pixel_array, dicom)
        pixel_array = normalize_pixel_data(pixel_array)

        logging.info(f"Converting {dicom_file.filename} to {format.upper()}")

        # Conversion logic
        output_path = os.path.join(output_folder, dicom_file.filename.replace(".dcm", f".{format}"))

        if format in ["jpeg", "png"]:
            image = Image.fromarray(pixel_array)
            image.save(output_path, format.upper(), quality=quality)

        elif format == "pdf":
            image = Image.fromarray(pixel_array)
            temp_image_path = os.path.join(output_folder, "temp_image.jpg")
            image.save(temp_image_path, "JPEG")

            pdf = canvas.Canvas(output_path)
            pdf.drawImage(temp_image_path, 50, 600, width=500, height=500)
            pdf.save()
            os.remove(temp_image_path)

        elif format == "tiff":
            imwrite(output_path, pixel_array)

        elif format == "mp4":
            if len(pixel_array.shape) < 3 or pixel_array.shape[0] < 2:
                logging.error("MP4 conversion requires multi-frame DICOM files.")
                raise HTTPException(status_code=400, detail="MP4 conversion requires multi-frame DICOM files.")
            height, width = pixel_array[0].shape
            video_writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), 10, (width, height))
            for frame in pixel_array:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                video_writer.write(rgb_frame)
            video_writer.release()

        else:
            logging.error(f"Unsupported format: {format}")
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

        logging.info(f"Successfully converted {dicom_file.filename} to {format.upper()} at {output_path}")
        return output_path

    except Exception as e:
        logging.error(f"Error converting {dicom_file.filename} to {format.upper()}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to convert DICOM to {format.upper()}.")



def generate_uids():
    study_uid = generate_uid()
    series_uid = generate_uid()
    sop_uid = generate_uid()
    return study_uid, series_uid, sop_uid

def set_dicom_headers(dicom: FileDataset, dicom_headers: dict):
    """
    Apply DICOM metadata headers safely.
    Only known tags are added.
    """
    for key, value in dicom_headers.items():
        try:
            setattr(dicom, key, value)
        except Exception as e:
            logger.warning(f"Skipping invalid DICOM attribute '{key}': {e}")

def convert_image_to_dicom(image_path: str, output_path: str, dicom_headers: dict = None):
    """
    Converts a standard image (e.g., PNG, JPEG) to a DICOM file.
    """
    if dicom_headers is None:
        dicom_headers = {}

    image = Image.open(image_path)
    study_uid, series_uid, sop_uid = generate_uids()

    filename = os.path.basename(output_path)
    file_meta = Dataset()
    file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.7"  # Secondary Capture Image Storage
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    file_meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID

    dt = datetime.now()

    dicom = FileDataset(filename, {}, file_meta=file_meta, preamble=b"\0" * 128)
    dicom.is_little_endian = True
    dicom.is_implicit_VR = False

    # Required tags for OHIF compatibility
    dicom.PatientName = dicom_headers.get("PatientName", "Anonymous")
    dicom.PatientID = dicom_headers.get("PatientID", "PID" + dt.strftime("%H%M%S"))
    dicom.StudyInstanceUID = study_uid
    dicom.SeriesInstanceUID = series_uid
    dicom.SOPInstanceUID = sop_uid
    dicom.SOPClassUID = file_meta.MediaStorageSOPClassUID
    dicom.StudyDate = dicom_headers.get("StudyDate", dt.strftime("%Y%m%d"))
    dicom.StudyTime = dicom_headers.get("StudyTime", dt.strftime("%H%M%S"))
    dicom.SeriesDate = dicom_headers.get("SeriesDate", dt.strftime("%Y%m%d"))
    dicom.SeriesTime = dicom_headers.get("SeriesTime", dt.strftime("%H%M%S"))
    dicom.StudyID = dicom_headers.get("StudyID", "SID" + dt.strftime("%H%M%S"))
    dicom.SeriesNumber = dicom_headers.get("SeriesNumber", "1")
    dicom.InstanceNumber = dicom_headers.get("InstanceNumber", "1")
    dicom.Modality = dicom_headers.get("Modality", "OT")
    dicom.Manufacturer = dicom_headers.get("Manufacturer", "DICOM Converter")
    dicom.PatientSex = dicom_headers.get("PatientSex", "O")
    dicom.StudyDescription = dicom_headers.get("StudyDescription", "Imported Study")
    dicom.SeriesDescription = dicom_headers.get("SeriesDescription", "Converted Series")

    # Apply remaining custom headers
    set_dicom_headers(dicom, dicom_headers)

    frames = []
    for i, frame in enumerate(ImageSequence.Iterator(image)):
        frame = frame.convert("RGB")
        arr = np.array(frame)
        frames.append(arr)

    if len(frames) == 1:
        pixel_array = frames[0]
    else:
        pixel_array = np.stack(frames)

    if pixel_array.ndim == 3 and pixel_array.shape[-1] == 3:
        dicom.SamplesPerPixel = 3
        dicom.PhotometricInterpretation = "RGB"
        dicom.PlanarConfiguration = 0
    else:
        dicom.SamplesPerPixel = 1
        dicom.PhotometricInterpretation = "MONOCHROME2"

    dicom.Rows, dicom.Columns = pixel_array.shape[0], pixel_array.shape[1]
    dicom.BitsAllocated = 8
    dicom.BitsStored = 8
    dicom.HighBit = 7
    dicom.PixelRepresentation = 0

    dicom.PixelData = pixel_array.tobytes()
    dicom.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

    dcmwrite(output_path, dicom)

    return study_uid, series_uid, sop_uid, dicom





def convert_pdf_to_dicom(input_path: str, output_path: str, dicom_headers: dict):
    """
    Convert a PDF file to a DICOM file with custom headers.
    """
    try:
        pdf_document = fitz.open(input_path)
        if pdf_document.page_count < 1:
            raise Exception("No pages found in the PDF.")

        page = pdf_document[0]
        pix = page.get_pixmap()
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
        pixel_array = np.array(image)

        # Generate UIDs
        study_uid = dicom_headers.get("StudyInstanceUID", generate_uid())
        series_uid = dicom_headers.get("SeriesInstanceUID", generate_uid())
        sop_uid = generate_uid()
        sop_class_uid = "1.2.840.10008.5.1.4.1.1.7"  # Secondary Capture Image Storage

        # Create DICOM object
        dicom = Dataset()
        dicom.file_meta = Dataset()
        dicom.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        dicom.file_meta.MediaStorageSOPClassUID = sop_class_uid
        dicom.file_meta.MediaStorageSOPInstanceUID = sop_uid
        dicom.file_meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID

        dicom.is_little_endian = True
        dicom.is_implicit_VR = False

        # Image attributes
        dicom.Rows, dicom.Columns = pixel_array.shape
        dicom.PixelData = pixel_array.tobytes()
        dicom.PhotometricInterpretation = "MONOCHROME2"
        dicom.BitsAllocated = 8
        dicom.BitsStored = 8
        dicom.HighBit = 7
        dicom.PixelRepresentation = 0

        # UIDs
        dicom.SOPClassUID = sop_class_uid
        dicom.SOPInstanceUID = sop_uid
        dicom.StudyInstanceUID = study_uid
        dicom.SeriesInstanceUID = series_uid

        # Set additional DICOM headers
        set_dicom_headers(dicom, dicom_headers)

        # ✅ Ensure folder exists before saving
        parent_dir = os.path.dirname(output_path)
        assert parent_dir, f"Invalid output_path: {output_path} has no parent directory"
        os.makedirs(parent_dir, exist_ok=True)

        print("output path is", output_path)

        # Save the DICOM file
        dicom.save_as(output_path, write_like_original=False)
        logging.info(f"Successfully converted PDF {input_path} to DICOM {output_path}")

    except Exception as e:
        logging.error(f"Error converting PDF {input_path} to DICOM: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error converting PDF to DICOM: {str(e)}")




def convert_video_to_dicom(input_path: str, output_path: str, dicom_headers: dict):
    """
    Convert a video file (e.g., MP4) to a DICOM file with custom headers.
    """
    try:
        video_capture = cv2.VideoCapture(input_path)
        frames = []

        while True:
            ret, frame = video_capture.read()
            if not ret:
                break
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frames.append(gray_frame)

        video_capture.release()

        if not frames:
            raise Exception("No frames extracted from the video.")

        # Generate UIDs
        study_uid = dicom_headers.get("StudyInstanceUID", generate_uid())
        series_uid = dicom_headers.get("SeriesInstanceUID", generate_uid())
        sop_uid = generate_uid()
        sop_class_uid = "1.2.840.10008.5.1.4.1.1.7"  # Secondary Capture Image Storage

        # Create DICOM dataset
        dicom = Dataset()
        dicom.file_meta = Dataset()
        dicom.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        dicom.file_meta.MediaStorageSOPClassUID = sop_class_uid
        dicom.file_meta.MediaStorageSOPInstanceUID = sop_uid
        dicom.file_meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID

        dicom.is_little_endian = True
        dicom.is_implicit_VR = False

        # Populate DICOM image fields
        dicom.Rows, dicom.Columns = frames[0].shape
        dicom.PixelData = np.stack(frames, axis=0).tobytes()
        dicom.NumberOfFrames = len(frames)
        dicom.SamplesPerPixel = 1
        dicom.PhotometricInterpretation = "MONOCHROME2"
        dicom.BitsAllocated = 8
        dicom.BitsStored = 8
        dicom.HighBit = 7
        dicom.PixelRepresentation = 0

        # Set Identifiers
        dicom.SOPClassUID = sop_class_uid
        dicom.SOPInstanceUID = sop_uid
        dicom.StudyInstanceUID = study_uid
        dicom.SeriesInstanceUID = series_uid

        # Set additional headers
        set_dicom_headers(dicom, dicom_headers)

        # ✅ Ensure folder exists before saving
        parent_dir = os.path.dirname(output_path)
        assert parent_dir, f"Invalid output_path: {output_path} has no parent directory"
        os.makedirs(parent_dir, exist_ok=True)


        print("output path is", output_path)

        dicom.save_as(output_path, write_like_original=False)
        logging.info(f"✅ Converted video {input_path} to DICOM {output_path}")

    except Exception as e:
        logging.error(f"❌ Error converting video {input_path} to DICOM: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error converting video to DICOM: {str(e)}")


    


def set_dicom_headers(dicom: Dataset, headers: dict):
    """
    Set DICOM headers into the given dataset.

    Args:
        dicom (Dataset): The DICOM dataset to update.
        headers (dict): Dictionary of DICOM headers to set.

    Raises:
        ValueError: If a header cannot be set.
    """
    failed_headers = []
    for key, value in headers.items():
        try:
            setattr(dicom, key, value)
        except Exception as e:
            logging.warning(f"Could not set header {key}: {str(e)}")
            failed_headers.append(key)
    if failed_headers:
        logging.warning(f"Failed to set the following DICOM headers: {failed_headers}")


# MIME type to format mapping
MIME_TYPE_MAP = {
    "image/jpeg": "jpeg",
    "image/png": "png",
    "application/pdf": "pdf",
    "image/tiff": "tiff",
    "video/mp4": "mp4",
}

def resolve_format(format_or_mime: str) -> str:
    """
    Normalize a MIME type or format string to a supported format.
    """
    fmt = format_or_mime.lower()
    if fmt in MIME_TYPE_MAP.values():
        return fmt
    elif fmt in MIME_TYPE_MAP:
        return MIME_TYPE_MAP[fmt]
    else:
        raise ValueError(f"Unsupported format or MIME type: {format_or_mime}")

# Reverse mapping from format to MIME type
FORMAT_TO_MIME = {v: k for k, v in MIME_TYPE_MAP.items()}
