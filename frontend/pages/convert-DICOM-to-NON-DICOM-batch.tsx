// pages/batch-upload.tsx
import {
  Box, Button, Divider, Text, VStack, useToast, HStack, Select, Progress, Spinner
} from "@chakra-ui/react";
import { useState } from "react";
import { useDropzone } from "react-dropzone";
import JSZip from "jszip";
import Navbar from "../components/Navbar";
import { getValidAccessToken } from "../src/utils/auth";
import { API_URL, buildStudyViewerUrl } from "../src/utils/env";
const supportedFormats = ["jpeg", "png", "pdf", "mp4"];

const BatchUpload = () => {
  const [files, setFiles] = useState<File[]>([]);
  const [fileFormats, setFileFormats] = useState<string[]>([]);
  const [uploadProgress, setUploadProgress] = useState<number[]>([]);
  const [results, setResults] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const toast = useToast();
  const zip = new JSZip();

  const onDrop = (acceptedFiles: File[]) => {
    setFiles(acceptedFiles);
    setFileFormats(new Array(acceptedFiles.length).fill("jpeg"));
    setUploadProgress(new Array(acceptedFiles.length).fill(0));
  };

  const { getRootProps, getInputProps } = useDropzone({ onDrop });

  const handleFormatChange = (index: number, format: string) => {
    const newFormats = [...fileFormats];
    newFormats[index] = format;
    setFileFormats(newFormats);
  };

  const handleBatchConvert = async () => {
    setIsLoading(true);
    const formData = new FormData();

    files.forEach((file) => formData.append("files", file));
    fileFormats.forEach((format) => formData.append("formats", format));
    formData.append("quality", "95");

    const token = await getValidAccessToken();
    if (!token) {
      toast({ title: "Session expired. Please log in again.", status: "error" });
      return;
    }

    try {
      const response = await fetch(`${API_URL}/conversions/dicom-export/batch`, {
        method: "POST",
        body: formData,
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Batch conversion failed.");
      }

      const data = await response.json();
      setResults(data);
      toast({ title: "Batch conversion complete", status: "success", duration: 3000 });

      for (const fileResult of data) {
        for (const output of fileResult.outputs || []) {
          if (output.status === "success") {
            const res = await fetch(output.download_url);
            const blob = await res.blob();
            zip.file(`${fileResult.input_file}_${output.format}`, blob);
          }
        }
      }
    } catch (error: any) {
      toast({ title: "Error", description: error.message, status: "error" });
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownloadZip = async () => {
    const content = await zip.generateAsync({ type: "blob" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(content);
    a.download = "converted_files.zip";
    a.click();
  };

  return (
    <Box bg="gray.900" minH="100vh" color="white">
      <Navbar />
      <Box p={4} maxW="900px" mx="auto">
        <VStack spacing={4} align="stretch">
          <Box
            {...getRootProps()}
            border="2px dashed teal"
            p={10}
            borderRadius="md"
            textAlign="center"
            cursor="pointer"
            bg="gray.700"
          >
            <input {...getInputProps()} />
            <Text>Drag & drop DICOM files here or click to browse</Text>
          </Box>

          {files.map((file, index) => (
            <Box key={index} p={3} borderWidth={1} borderRadius="md" bg="gray.800">
              <HStack justify="space-between">
                <Text>{file.name}</Text>
                <Select
                  value={fileFormats[index]}
                  onChange={(e) => handleFormatChange(index, e.target.value)}
                  w="150px"
                >
                  {supportedFormats.map((format) => (
                    <option key={format} value={format} style={{ backgroundColor: '#1a202c' }}>
                      {format.toUpperCase()}
                    </option>
                  ))}
                </Select>
              </HStack>
              <Progress value={uploadProgress[index]} size="xs" mt={2} colorScheme="teal" />
            </Box>
          ))}

          <Button
            onClick={handleBatchConvert}
            isDisabled={files.length === 0 || isLoading}
            colorScheme="teal"
          >
            {isLoading ? <Spinner size="sm" /> : "Convert Batch"}
          </Button>

          {results.length > 0 && (
            <Box mt={6} bg="gray.800" p={4} borderRadius="md">
              <Text fontWeight="bold" mb={2}>Conversion Results</Text>
              <Divider my={2} />
              {results.map((result, index) => {
                const studyUID = result?.dicom_headers?.StudyInstanceUID || result.study_instance_uid;
                return (
                  <Box key={index} p={3} borderWidth={1} borderRadius="md" bg="gray.700" mb={3}>
                    <Text>📄 File: {result.input_file}</Text>
                    <Text>🧬 Study UID: {studyUID || "N/A"}</Text>
                    {(result.outputs || []).map((output: any, i: number) => (
                      <Box key={i} ml={4} mt={2}>
                        <Text>Status: {output.status}</Text>
                        {output.status === "success" && (
                          <>
                            <a href={output.download_url} target="_blank" rel="noopener noreferrer">
                              🔗 Download ({output.format})
                            </a>
                            <Button
                              as="a"
                              href={output.download_url}
                              target="_blank"
                              colorScheme="yellow"
                              mt={2}
                              display="flex"
                              justifyContent="center"
                            >
                          Download DICOM file ({output.format})
                            </Button>
                            {studyUID && (
                              <Button
                                as="a"
                                href={buildStudyViewerUrl(studyUID)}
                                target="_blank"
                                size="sm"
                                colorScheme="green"
                                mt={1}
                                display="flex"
                                justifyContent="center"
                              >
                                View in OHIF
                              </Button>
                            )}
                          </>
                        )}
                        {output.status === "failed" && (
                          <Text color="red.400">❌ Error: {output.error}</Text>
                        )}
                      </Box>
                    ))}
                  </Box>
                );
              })}
              <Button mt={4} onClick={handleDownloadZip} colorScheme="blue">
                Download All as ZIP
              </Button>
            </Box>
          )}
        </VStack>
      </Box>
    </Box>
  );
};

export default BatchUpload;
