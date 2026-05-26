import React, { useState } from 'react';
import StudyList from './StudyList';
import { API_URL, buildStudyViewerUrl } from '../../src/utils/env';

const inferInputFormat = (file: File) => {
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (extension === 'jpg') return 'jpeg';
  return extension || 'jpeg';
};

export default function DicomUploaderViewer() {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [studyUID, setStudyUID] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setSelectedFiles(Array.from(e.target.files));
    }
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;
    setIsUploading(true);
    setError(null);

    const formData = new FormData();
    selectedFiles.forEach(file => formData.append('files', file));
    const inputFormats = selectedFiles.map(inferInputFormat).join(',');

    try {
      const response = await fetch(`${API_URL}/conversions/media-import/batch?input_formats=${encodeURIComponent(inputFormats)}`, {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();
      if (result.length > 0) {
        const firstUID = result[0].dicom_headers?.StudyInstanceUID;
        setStudyUID(firstUID);
      }
    } catch (err: any) {
      setError('Upload failed: ' + err.message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleStudySelect = (uid: string) => {
    setStudyUID(uid);
  };

  return (
    <div className="p-4 space-y-4">
      <h1 className="text-xl font-bold">DICOM Upload + Viewer</h1>

      <div className="space-y-2">
        <input type="file" multiple onChange={handleFileChange} className="block" />
        <button
          onClick={handleUpload}
          className="bg-blue-600 text-white p-2 rounded"
          disabled={isUploading}
        >
          {isUploading ? 'Uploading...' : 'Upload Files'}
        </button>
        {error && <p className="text-red-500">{error}</p>}
      </div>

      <div className="pt-4">
        <StudyList onSelect={handleStudySelect} />
      </div>

      {studyUID && (
        <div className="pt-4">
          <h2 className="text-lg font-semibold">Embedded Viewer</h2>
          <iframe
            src={buildStudyViewerUrl(studyUID)}
            title="OHIF Viewer"
            className="w-full h-[80vh] border"
          />
        </div>
      )}
    </div>
  );
}
