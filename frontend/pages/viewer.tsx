import { useRouter } from "next/router";
import { useEffect } from "react";
import { buildStudyViewerUrl } from "../src/utils/env";

const ViewerPage = () => {
  const router = useRouter();
  const { studyUID } = router.query;

  useEffect(() => {
  if (typeof studyUID === "string") {
    window.location.href = buildStudyViewerUrl(studyUID);

  }
}, [studyUID]);


  return (
    <div style={{ padding: "2rem" }}>
      <h2>Launching OHIF Viewer...</h2>
      <p>Please wait while we load your study.</p>
    </div>
  );
};

export default ViewerPage;
