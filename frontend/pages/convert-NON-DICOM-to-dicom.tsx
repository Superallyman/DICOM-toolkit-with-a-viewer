// pages/convert-to-dicom.tsx
import {
  Box, Button, Input, Spinner, Text, VStack, useToast, HStack,
  Divider, Textarea, useColorModeValue, Modal, ModalOverlay,
  ModalContent, ModalHeader, ModalCloseButton, ModalBody, Image, useDisclosure
} from "@chakra-ui/react";
import { useState } from "react";
import JSZip from "jszip";
import { saveAs } from "file-saver";
import { useDropzone } from "react-dropzone";
import Navbar from "../components/Navbar";
import { useRouter } from "next/router";
import { getValidAccessToken } from "../src/utils/auth";
import { API_URL, buildStudyViewerUrl } from "../src/utils/env";
const ITEMS_PER_PAGE = 5;

const ConvertToDICOM = () => {
  const [files, setFiles] = useState<File[]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [zipLoading, setZipLoading] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [progress, setProgress] = useState<number[]>([]);
  const [currentPage, setCurrentPage] = useState(1);

  const toast = useToast();
  const router = useRouter();
  const bgColor = useColorModeValue("gray.100", "gray.700");

  const onDrop = (acceptedFiles: File[]) => {
    const newFiles = [...files, ...acceptedFiles];
    setFiles(newFiles);
    setHeaders([...headers, ...acceptedFiles.map(() => '{"PatientName": "Test"}')]);
    setProgress([...progress, ...acceptedFiles.map(() => 0)]);
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop });

  const handleConvert = async () => {
    const formData = new FormData();
    if (files.length === 0) return;
    files.forEach((file) => formData.append("files", file));
    formData.append("dicom_headers", JSON.stringify(headers.map(h => JSON.parse(h))));

    const inputFormats = files.map(f => f.name.split(".").pop()).join(",");
    const token = await getValidAccessToken();
    if (!token) {
      toast({ title: "Session expired. Please log in again.", status: "error" });
      router.push("/login");
      return;
    }

    const url = `${API_URL}/conversions/media-import/batch?input_formats=${encodeURIComponent(inputFormats)}`;

    try {
      setIsLoading(true);
      const response = await fetch(url, {
        method: "POST",
        body: formData,
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Conversion failed.");
      }

      const data = await response.json();
      setResults(data);
      toast({ title: "Conversion complete", status: "success", duration: 3000 });
    } catch (error: any) {
      toast({ title: "Error", description: error.message, status: "error" });
    } finally {
      setIsLoading(false);
    }
  };

  const handleZipDownload = async () => {
    setZipLoading(true);
    const zip = new JSZip();
    const successfulResults = results.filter(r => r.status === "success");

    for (const result of successfulResults) {
      const fileResp = await fetch(result.download_url);
      const blob = await fileResp.blob();
      zip.file(result.output_file.split("/").pop() || result.input_file, blob);
    }

    const content = await zip.generateAsync({ type: "blob" });
    saveAs(content, "converted_dicom_files.zip");
    setZipLoading(false);
  };

  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const paginatedFiles = files.slice(startIndex, endIndex);
  const totalPages = Math.ceil(files.length / ITEMS_PER_PAGE);

  return (
    <Box minH="100vh" bg="gray.900" color="white">
      <Navbar />
      <Box p={4} maxW="3xl" mx="auto">
        <VStack spacing={4} align="stretch">
          <Box p={10} bg="gray.700" borderRadius="lg" {...getRootProps()} border="2px dashed teal" textAlign="center">
            <input {...getInputProps()} />
            {isDragActive ? <Text>Drop files here...</Text> : <Text>Drag and drop or click to select files</Text>}
          </Box>

          {paginatedFiles.map((file, index) => (
            <Box key={index + startIndex} p={6} borderWidth={1} borderRadius="md" bg="gray.700">
              <Text fontWeight="bold">{file.name}</Text>
              <Textarea
                mt={2}
                placeholder='{"PatientName": "John Doe"}'
                value={headers[index + startIndex]}
                onChange={(e) => {
                  const newHeaders = [...headers];
                  newHeaders[index + startIndex] = e.target.value;
                  setHeaders(newHeaders);
                }}
              />
            </Box>
          ))}

          {totalPages > 1 && (
            <HStack justify="center">
              <Button onClick={() => setCurrentPage(p => Math.max(p - 1, 1))} disabled={currentPage === 1}>Previous</Button>
              <Text>Page {currentPage} of {totalPages}</Text>
              <Button onClick={() => setCurrentPage(p => Math.min(p + 1, totalPages))} disabled={currentPage === totalPages}>Next</Button>
            </HStack>
          )}

          <Button onClick={handleConvert} isDisabled={files.length === 0 || isLoading} colorScheme="teal">
            {isLoading ? <Spinner size="sm" /> : "Convert to DICOM"}
          </Button>

          {results.length > 0 && (
            <Box mt={6}>
              <Text fontWeight="bold">Conversion Results</Text>
              <Divider my={2} />
              {results.map((result, index) => (
                <Box key={index} p={3} borderWidth={1} borderRadius="md" bg="gray.700">
                  <Text>File: {result.input_file}</Text>
                  {result.status === "success" ? (
                    <>
                      <Text>Status: ✅ Success</Text>
                      <Text>Study UID: {result.dicom_headers?.StudyInstanceUID}</Text>
                      <a href={result.download_url} target="_blank" rel="noopener noreferrer">
                        Download DICOM
                      </a>
                      <Button
                      as="a"
                          href={result.download_url}
                          target="_blank"
                          colorScheme="yellow"
                          mt={2}
                          display="flex"
                          justifyContent="center"
                        >
                          Download DICOM file
                     </Button>
                      {result.dicom_headers?.StudyInstanceUID && (
                        <Button
                          as="a"
                          href={buildStudyViewerUrl(result.dicom_headers.StudyInstanceUID)}
                          target="_blank"
                          colorScheme="green"
                          mt={2}
                          display="flex"
                          justifyContent="center"
                        >
                          View in OHIF
                        </Button>
                      )}

                    </>
                  ) : (
                    <Text color="red.500">❌ Error: {result.error}</Text>
                  )}
                </Box>
              ))}
              <Button mt={4} colorScheme="blue" onClick={handleZipDownload} isDisabled={zipLoading}>
                {zipLoading ? <Spinner size="sm" /> : "Download All as ZIP"}
              </Button>
            </Box>
          )}
        </VStack>
      </Box>
    </Box>
  );
};

export default ConvertToDICOM;
