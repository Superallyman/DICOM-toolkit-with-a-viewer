// components/viewer/DicomViewer.tsx
import { buildStudyViewerUrl } from "../../src/utils/env";

interface Props {
  studyInstanceUID: string;
}

export default function DicomViewer({ studyInstanceUID }: Props) {
  return (
    <div className="pt-4">
      <h2 className="text-lg font-semibold">Embedded Viewer</h2>
      <iframe
        src={buildStudyViewerUrl(studyInstanceUID)}
        title="OHIF Viewer"
        className="w-full h-[80vh] border"
      />
    </div>
  );
}
