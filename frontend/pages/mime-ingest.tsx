import {
  Box,
  Button,
  Container,
  Heading,
  HStack,
  Input,
  Link as ChakraLink,
  Stack,
  Text,
  useToast,
  VStack,
  Code,
  Divider,
  Badge,
  Accordion,
  AccordionItem,
  AccordionButton,
  AccordionPanel,
  AccordionIcon,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Spinner,
  Switch,
  FormControl,
  FormLabel,
} from "@chakra-ui/react";
import Head from "next/head";
import { useCallback, useEffect, useState } from "react";
import Navbar from "../components/Navbar";
import { buildViewerUrl } from "../src/utils/env";
import api from "../src/utils/axiosInstance";

// ---------- Types that match backend payload ---------------------
type ExtractedItem = {
  filename: string;
  output_file: string;
  download_url: string; // must be a string; never boolean
  ohif_url?: string;
  study_uid?: string;
  series_uid?: string;
  sop_uid?: string;
  metadata: Record<string, unknown>;
};

type FileResult = {
  original_filename?: string;
  input_file?: string; // kept for back-compat; UI never treats this as boolean
  items: ExtractedItem[];
};

type IngestResponse = {
  status: "ok";
  total_dicoms: number;
  files: FileResult[];
};

type JobResponse = {
  id: string;
  job_type: string;
  status: string;
  result_payload?: IngestResponse;
  error?: string;
};
// -----------------------------------------------------------------

export default function MimeIngest() {
  const [files, setFiles] = useState<FileList | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [result, setResult] = useState<IngestResponse | null>(null);
  const [jobResult, setJobResult] = useState<JobResponse | null>(null);
  const [wrapAsSC, setWrapAsSC] = useState<boolean>(false);
  const [processAsync, setProcessAsync] = useState<boolean>(true);
  const toast = useToast();

  const handleFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFiles(e.target.files);
  };

  const callApi = useCallback(
    async (formData: FormData, wrap: boolean): Promise<IngestResponse> => {
      const wrapParam = wrap ? "true" : "false";
      const url = `/mime/ingest?wrap_non_dicom=${wrapParam}`;
      const res = await api.post<IngestResponse>(url, formData);
      return res.data;
    },
    []
  );

  const callJobApi = useCallback(
    async (formData: FormData, wrap: boolean): Promise<JobResponse> => {
      const wrapParam = wrap ? "true" : "false";
      const url = `/mime-ingest/jobs?wrap_non_dicom=${wrapParam}`;
      const res = await api.post<JobResponse>(url, formData);
      return res.data;
    },
    []
  );

  const loadJob = useCallback(async (jobId: string): Promise<JobResponse> => {
    const { data } = await api.get<JobResponse>(`/jobs/${jobId}`, {
      headers: { "X-Skip-Loader": "1" },
    });
    return data;
  }, []);

  useEffect(() => {
    if (!jobResult || !["queued", "running"].includes(jobResult.status)) return;

    const timer = window.setInterval(async () => {
      try {
        const next = await loadJob(jobResult.id);
        setJobResult(next);
        if (next.status === "succeeded" && next.result_payload) {
          setResult(next.result_payload);
        }
      } catch (e: any) {
        toast({
          status: "error",
          title: "Job status refresh failed",
          description: e?.message || "Unable to refresh job status",
        });
        window.clearInterval(timer);
      }
    }, 2500);

    return () => window.clearInterval(timer);
  }, [jobResult, loadJob, toast]);

  const onSubmit = useCallback(async () => {
    if (!files || files.length === 0) {
      toast({
        status: "warning",
        title: "Please choose at least one .mime file",
      });
      return;
    }
    setIsLoading(true);
    setResult(null);
    setJobResult(null);
    try {
      const fd = new FormData();
      Array.from(files).forEach((f) => fd.append("files", f));
      if (processAsync) {
        const job = await callJobApi(fd, wrapAsSC);
        setJobResult(job);
        toast({
          status: "success",
          title: "MIME ingest job queued",
          description: `Job ${job.id}`,
        });
      } else {
        const data = await callApi(fd, wrapAsSC);
        setResult(data);
      }
    } catch (e: any) {
      toast({
        status: "error",
        title: "Ingest failed",
        description: e?.message || "Please check the server logs",
      });
    } finally {
      setIsLoading(false);
    }
  }, [files, callApi, callJobApi, processAsync, toast, wrapAsSC]);

 const handleOpenOhif = (it: ExtractedItem) => {
   if (!it.study_uid) {
     toast({
       status: "info",
       title: "No Study UID for OHIF",
       description: "This item is not a DICOM or lacks a viewer URL.",
     });
     return;
   }

   // 1) Use the URL from the backend if present (already deep-linked)
   let url = it.ohif_url;

   // 2) Otherwise, construct a Viewer URL that points directly to the image
   if (!url) {
     url = buildViewerUrl({
       studyInstanceUID: it.study_uid,
       seriesInstanceUID: it.series_uid,
       sopInstanceUID: it.sop_uid,
     });
   }

   window.open(url, "_blank", "noopener,noreferrer");
 };


  const safeFileKey = (f: FileResult, idx: number): string => {
    // Ensure key is always a string (never boolean)
    return (f.original_filename ?? f.input_file ?? `mime-${idx}`) as string;
  };

  const safeHref = (url: string | undefined): string => {
    // Defensive: always return a string (ChakraLink href expects string)
    return typeof url === "string" ? url : "#";
  };

  return (
    <>
      <Head>
        <title>MIME Ingest</title>
      </Head>
      <Navbar />
      <Container maxW="6xl" py={8}>
        <Heading size="lg" mb={4}>
          MIME to DICOM Ingest
        </Heading>
        <Text color="gray.400" mb={4}>
          Upload .mime files. DICOM attachments are extracted and prepared for
          OHIF viewer. Non-DICOM parts can be saved as files or optionally
          wrapped into Secondary Capture DICOMs.
        </Text>

        <VStack align="stretch" spacing={4}>
          <HStack align="center" justifyContent="space-between">
            <Input
              type="file"
              multiple
              accept=".mime,.eml"
              onChange={handleFiles}
            />
            <FormControl display="flex" alignItems="center" w="auto">
              <FormLabel htmlFor="wrap-sc" mb="0" mr={3} color="gray.300">
                Wrap non-DICOM as SC
              </FormLabel>
              <Switch
                id="wrap-sc"
                isChecked={wrapAsSC}
                onChange={(e) => setWrapAsSC(e.target.checked)}
              />
            </FormControl>
            <FormControl display="flex" alignItems="center" w="auto">
              <FormLabel htmlFor="async-ingest" mb="0" mr={3} color="gray.300">
                Background job
              </FormLabel>
              <Switch
                id="async-ingest"
                isChecked={processAsync}
                onChange={(e) => setProcessAsync(e.target.checked)}
              />
            </FormControl>
            <Button onClick={onSubmit} isLoading={isLoading} colorScheme="blue">
              Ingest
            </Button>
          </HStack>
        </VStack>

        <Divider my={6} />

        {isLoading ? (
          <HStack>
            <Spinner />
            <Text color="gray.400">Processing...</Text>
          </HStack>
        ) : jobResult ? (
          <Box bg="gray.900" p={4} rounded="md" borderWidth={1} borderColor="gray.700">
            <Text color="gray.200">Queued job: {jobResult.id}</Text>
            <Text color="gray.400">Status: {jobResult.status}</Text>
            {jobResult.status === "failed" ? (
              <Text color="red.300">{jobResult.error || "Job failed"}</Text>
            ) : null}
            {["queued", "running"].includes(jobResult.status) ? (
              <HStack mt={3}>
                <Spinner size="sm" />
                <Text color="gray.400">Waiting for worker...</Text>
              </HStack>
            ) : null}
            <ChakraLink href={`/jobs?jobId=${jobResult.id}`} color="teal.300">
              View processing jobs
            </ChakraLink>
          </Box>
        ) : result ? (
          <Stack spacing={6}>
            {result.files.map((f, fileIdx) => (
              <Box
                key={safeFileKey(f, fileIdx)}
                bg="gray.900"
                p={4}
                rounded="md"
                border="1px solid"
                borderColor="gray.700"
              >
                <Heading size="sm" mb={3} color="gray.100">
                  {
                    (f.original_filename ??
                      f.input_file ??
                      "MIME file") as string
                  }
                </Heading>

                {f.items.length === 0 ? (
                  <Text color="gray.400">
                    No extractable attachments found.
                  </Text>
                ) : (
                  <Accordion allowToggle>
                    {f.items.map((it, idx) => (
                      <AccordionItem
                        key={`${it.filename}-${idx}`}
                        borderColor="gray.700"
                      >
                        <h2>
                          <AccordionButton>
                            <Box as="span" flex="1" textAlign="left">
                              <HStack spacing={3}>
                                <Text>{it.filename}</Text>
                                {it.study_uid ? (
                                  <Badge colorScheme="green">DICOM</Badge>
                                ) : (
                                  <Badge colorScheme="yellow">Non-DICOM</Badge>
                                )}
                              </HStack>
                            </Box>
                            <AccordionIcon />
                          </AccordionButton>
                        </h2>
                        <AccordionPanel pb={4}>
                          <HStack spacing={3} mb={3}>
                            {it.study_uid ? (
                              <Button
                                size="sm"
                                colorScheme="blue"
                                variant="solid"
                                onClick={() => handleOpenOhif(it)}
                              >
                                View in OHIF
                              </Button>
                            ) : null}

                            <ChakraLink
                              href={safeHref(it.download_url)}
                              isExternal
                              _hover={{ textDecoration: "none" }}
                            >
                              <Button
                                variant="outline"
                                borderColor="gray.500"
                                color="gray.100"
                              >
                                {it.study_uid
                                  ? "Download DICOM"
                                  : "Download file"}
                              </Button>
                            </ChakraLink>
                          </HStack>

                          <Table size="sm" variant="simple">
                            <Thead>
                              <Tr>
                                <Th>Field</Th>
                                <Th>Value</Th>
                              </Tr>
                            </Thead>
                            <Tbody>
                              {Object.entries(it.metadata || {}).map(
                                ([k, v]) => (
                                  <Tr key={k}>
                                    <Td>{k}</Td>
                                    <Td>
                                      <Code fontSize="xs">
                                        {typeof v === "string"
                                          ? v
                                          : JSON.stringify(v)}
                                      </Code>
                                    </Td>
                                  </Tr>
                                )
                              )}
                              {it.study_uid ? (
                                <>
                                  <Tr>
                                    <Td>StudyInstanceUID</Td>
                                    <Td>
                                      <Code fontSize="xs">{it.study_uid}</Code>
                                    </Td>
                                  </Tr>
                                  <Tr>
                                    <Td>SeriesInstanceUID</Td>
                                    <Td>
                                      <Code fontSize="xs">{it.series_uid}</Code>
                                    </Td>
                                  </Tr>
                                  <Tr>
                                    <Td>SOPInstanceUID</Td>
                                    <Td>
                                      <Code fontSize="xs">{it.sop_uid}</Code>
                                    </Td>
                                  </Tr>
                                </>
                              ) : null}
                            </Tbody>
                          </Table>
                        </AccordionPanel>
                      </AccordionItem>
                    ))}
                  </Accordion>
                )}
              </Box>
            ))}
          </Stack>
        ) : null}
      </Container>
    </>
  );
}
