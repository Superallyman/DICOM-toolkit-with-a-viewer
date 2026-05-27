// src/utils/env.ts
/**
 * Frontend-safe env helpers. Reads NEXT_PUBLIC_* vars.
 * Falls back to localhost:8000 when not set.
 */

const rawBase =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") || "http://localhost:8000";
const rawViewerBase =
  process.env.NEXT_PUBLIC_OHIF_BASE_URL?.replace(/\/+$/, "") || `${rawBase}/v1/viewer`;

export const API_BASE_URL = rawBase;      // e.g. http://localhost:8000
export const API_PREFIX = "/v1";          // your API prefix
export const API_URL = `${API_BASE_URL}${API_PREFIX}`; // e.g. http://localhost:8000/v1
export const OHIF_BASE_URL = rawViewerBase;

type ViewerUrlInput = {
  studyInstanceUID: string;
  seriesInstanceUID?: string;
  sopInstanceUID?: string;
};

/** Build the canonical OHIF launch URL used by the app shell. */
export const buildViewerUrl = ({
  studyInstanceUID,
  seriesInstanceUID,
  sopInstanceUID,
}: ViewerUrlInput) => {
  const params = new URLSearchParams();
  params.set("StudyInstanceUIDs", studyInstanceUID);
  if (seriesInstanceUID) params.set("SeriesInstanceUID", seriesInstanceUID);
  if (sopInstanceUID) params.set("SOPInstanceUID", sopInstanceUID);

  return `${OHIF_BASE_URL}/viewer?${params.toString()}`;
};

export const buildStudyViewerUrl = (studyInstanceUID: string) =>
  buildViewerUrl({ studyInstanceUID });

export const buildLocalViewerUrl = () => `${OHIF_BASE_URL}/local`;
