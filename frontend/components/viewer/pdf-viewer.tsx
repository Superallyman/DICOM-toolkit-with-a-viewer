export default function PdfViewer({ fileUrl }: { fileUrl: string }) {
  return (
    <iframe
      src={`https://mozilla.github.io/pdf.js/web/viewer.html?file=${encodeURIComponent(fileUrl)}`}
      width="100%"
      height="500px"
      className="border rounded shadow-lg"
    ></iframe>
  );
}
