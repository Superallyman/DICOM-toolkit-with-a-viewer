import { useState, useEffect } from "react";
import { useRouter } from "next/router";
import {
  Box, Button, Input, Select, Textarea, Alert, AlertTitle,
  Heading, VStack, Link, Text, Spinner
} from "@chakra-ui/react";
import Navbar from "../components/Navbar";
import MediaPreview from "../components/viewer/media-preview";
import { getToken, parseToken } from "../src/utils/auth";
import { API_URL, buildStudyViewerUrl } from "../src/utils/env";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [format, setFormat] = useState("jpeg");
  const [convertedUrl, setConvertedUrl] = useState("");
  const [metadata, setMetadata] = useState<any>(null);
  const [studyUID, setStudyUID] = useState<string | null>(null);
  const [banner, setBanner] = useState("API is running normally.");
  const [mimeType, setMimeType] = useState("");
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
    } else {
      try {
        parseToken(token);
        setLoading(false);
      } catch {
        router.push("/login");
      }
    }
  }, [router]);

  const detectMimeType = (filename: string): string => {
    const ext = filename.split(".").pop()?.toLowerCase();
    const map: Record<string, string> = {
      jpg: "image/jpeg",
      jpeg: "image/jpeg",
      png: "image/png",
      pdf: "application/pdf",
      mp4: "video/mp4",
      tiff: "image/tiff",
      dcm: "application/dicom",
      dicom: "application/dicom",
    };
    return (ext && map[ext]) || "application/octet-stream";
  };

  const handleUpload = async () => {
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("format", format);

    const token = getToken();
    if (!token) {
      setBanner("Authentication required. Please login again.");
      router.push("/login");
      return;
    }

    try {
      const res = await fetch(`${API_URL}/conversions/dicom-export`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          // Do NOT set Content-Type with FormData
        },
        body: formData,
      });

      if (!res.ok) {
        const errorText = await res.text();
        setBanner(`Upload failed: ${res.status} ${res.statusText} — ${errorText}`);
        return;
      }

      const data = await res.json();

      // Download URL for converted asset (jpeg/png/pdf/mp4/etc.)
      setConvertedUrl(data.download_url || "");
      if (data.download_url) setMimeType(detectMimeType(data.download_url));

      // Metadata (your backend returns flat DICOM keywords)
      setMetadata(data.metadata ?? null);

      // Get StudyInstanceUID robustly
      const uidFromMeta =
        data?.metadata?.StudyInstanceUID ||
        data?.metadata?.dicom_headers?.StudyInstanceUID || // fallback if wrapped
        null;

      const finalUID = uidFromMeta || data?.study_instance_uid || null;
      setStudyUID(finalUID);

      setBanner("Upload and conversion successful.");
    } catch (error) {
      console.error("Upload error:", error);
      setBanner("Upload failed: Network error or server unreachable.");
    }
  };

  const handleViewInOHIF = () => {
    if (!studyUID) return;
    window.open(buildStudyViewerUrl(studyUID), "_blank", "noopener,noreferrer");
  };

  if (loading) {
    return <Spinner size="xl" color="teal.300" />;
  }

  return (
    <Box bg="gray.900" color="white" minH="100vh" p={6}>
      <Navbar />
      <Alert status="info" bg="gray.800" borderColor="gray.700" borderWidth={1} rounded="md" my={4}>
        <AlertTitle>{banner}</AlertTitle>
      </Alert>

      <Box bg="gray.800" borderColor="gray.700" borderWidth={1} rounded="md" p={6} my={4}>
        <VStack spacing={4} align="stretch">
          <Heading size="md">Select a DICOM file:</Heading>
          <Input
            type="file"
            accept=".dcm,.dicom,application/dicom"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <Heading size="md">Select output format:</Heading>
          <Select value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="jpeg" style={{ backgroundColor: "#1a202c" }}>
              JPEG
            </option>
            <option value="png" style={{ backgroundColor: "#1a202c" }}>
              PNG
            </option>
            <option value="pdf" style={{ backgroundColor: "#1a202c" }}>
              PDF
            </option>
            <option value="tiff" style={{ backgroundColor: "#1a202c" }}>
              TIFF
            </option>
            <option value="mp4" style={{ backgroundColor: "#1a202c" }}>
              MP4
            </option>
          </Select>
          <Button colorScheme="teal" onClick={handleUpload}>
            Convert
          </Button>
        </VStack>
      </Box>

      {convertedUrl && (
        <Box bg="gray.800" borderColor="gray.700" borderWidth={1} rounded="md" p={6} my={4}>
          <VStack spacing={4} align="stretch">
            <Heading size="md">Preview:</Heading>
            <MediaPreview url={convertedUrl} type={mimeType} />
            <Text fontWeight="bold">Download Converted File:</Text>
            <Link href={convertedUrl} target="_blank" color="teal.300" isExternal>
              {convertedUrl}
            </Link>

            {studyUID && (
              <Button colorScheme="green" onClick={handleViewInOHIF}>
                View in OHIF
              </Button>
            )}
          </VStack>
        </Box>
      )}

      {metadata && (
        <Box bg="gray.800" borderColor="gray.700" borderWidth={1} rounded="md" p={6} my={4}>
          <VStack spacing={4} align="stretch">
            <Heading size="md">Extracted Metadata:</Heading>
            <Textarea readOnly rows={10} value={JSON.stringify(metadata, null, 2)} />
          </VStack>
        </Box>
      )}
    </Box>
  );
}
