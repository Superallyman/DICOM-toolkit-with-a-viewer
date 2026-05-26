import { buildStudyViewerUrl } from '../../src/utils/env';

export default function OHIFWrapper({ studyInstanceUID }: { studyInstanceUID: string }) {
  return (
    <iframe
      src={buildStudyViewerUrl(studyInstanceUID)}
      title="OHIF Viewer"
      className="w-full h-[80vh]"
    />
  );
}
