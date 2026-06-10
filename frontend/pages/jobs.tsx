//pages/jobs.tsx

import { AddIcon, ExternalLinkIcon, RepeatIcon } from "@chakra-ui/icons";
import {
  Badge,
  Box,
  Button,
  Code,
  Grid,
  GridItem,
  HStack,
  Heading,
  Link as ChakraLink,
  Spinner,
  Stack,
  Switch,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import { useRouter } from "next/router";
import { useCallback, useEffect, useMemo, useState } from "react";
import Navbar from "../components/Navbar";
import api from "../src/utils/axiosInstance";

type JobStatus = "queued" | "running" | "succeeded" | "failed" | string;

type Job = {
  id: string;
  job_type: string;
  status: JobStatus;
  priority: number;
  input_payload: Record<string, unknown>;
  result_payload?: Record<string, unknown>;
  error?: string;
  created_at?: string;
  updated_at?: string;
};

type ResultItem = {
  filename?: string;
  download_url?: string;
  ohif_url?: string;
  study_uid?: string;
};

const activeStatuses = new Set(["queued", "running"]);

const statusColor = (status: string) => {
  if (status === "succeeded") return "green";
  if (status === "failed") return "red";
  if (status === "running") return "blue";
  return "yellow";
};

const formatDate = (value?: string) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const extractResultItems = (payload?: Record<string, unknown>): ResultItem[] => {
  if (!payload) return [];

  if (Array.isArray(payload.files)) {
    return payload.files.flatMap((file) => {
      if (!isRecord(file) || !Array.isArray(file.items)) return [];
      return file.items.filter(isRecord).map((item) => ({
        filename: typeof item.filename === "string" ? item.filename : undefined,
        download_url:
          typeof item.download_url === "string" ? item.download_url : undefined,
        ohif_url: typeof item.ohif_url === "string" ? item.ohif_url : undefined,
        study_uid: typeof item.study_uid === "string" ? item.study_uid : undefined,
      }));
    });
  }

  const downloadUrl =
    typeof payload.download_url === "string" ? payload.download_url : undefined;
  const ohifUrl = typeof payload.ohif_url === "string" ? payload.ohif_url : undefined;
  const filename =
    typeof payload.filename === "string"
      ? payload.filename
      : typeof payload.output_file === "string"
        ? payload.output_file
        : undefined;

  return downloadUrl || ohifUrl ? [{ filename, download_url: downloadUrl, ohif_url: ohifUrl }] : [];
};

export default function JobsPage() {
  const router = useRouter();
  const highlightedJobId =
    typeof router.query.jobId === "string" ? router.query.jobId : "";
  const [jobs, setJobs] = useState<Job[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState("");

  const loadJobs = useCallback(async (showSpinner = true) => {
    if (showSpinner) setIsLoading(true);
    setError("");
    try {
      const { data } = await api.get<Job[]>("/jobs", {
        params: { limit: 100 },
        headers: showSpinner ? undefined : { "X-Skip-Loader": "1" },
      });
      setJobs(data);
    } catch (err: any) {
      setError(err?.message || "Failed to load jobs");
    } finally {
      if (showSpinner) setIsLoading(false);
    }
  }, []);

  const enqueueHealthCheck = async () => {
    setIsCreating(true);
    try {
      await api.post("/jobs", {
        job_type: "health.ping",
        input_payload: { source: "jobs-page" },
        priority: 10,
      });
      await loadJobs(false);
    } finally {
      setIsCreating(false);
    }
  };

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!autoRefresh || !jobs.some((job) => activeStatuses.has(job.status))) return;
    const timer = window.setInterval(() => loadJobs(false), 2500);
    return () => window.clearInterval(timer);
  }, [autoRefresh, jobs, loadJobs]);

  const counts = useMemo(
    () =>
      jobs.reduce<Record<string, number>>((acc, job) => {
        acc[job.status] = (acc[job.status] || 0) + 1;
        return acc;
      }, {}),
    [jobs]
  );

  const renderResultActions = (job: Job) => {
    const items = extractResultItems(job.result_payload);
    if (job.status !== "succeeded" || items.length === 0) {
      return <Text color="gray.500">-</Text>;
    }

    return (
      <Stack spacing={2} align="start">
        {items.slice(0, 3).map((item, index) => (
          <HStack key={`${item.filename || job.id}-${index}`} spacing={2}>
            {item.ohif_url ? (
              <ChakraLink href={item.ohif_url} isExternal>
                <Button
                  size="xs"
                  colorScheme="blue"
                  leftIcon={<ExternalLinkIcon />}
                  variant="solid"
                >
                  OHIF
                </Button>
              </ChakraLink>
            ) : null}
            {item.download_url ? (
              <ChakraLink href={item.download_url} isExternal>
                <Button size="xs" variant="outline" borderColor="gray.500">
                  Download
                </Button>
              </ChakraLink>
            ) : null}
            <Text color="gray.400" fontSize="xs" noOfLines={1} maxW="44">
              {item.filename || item.study_uid || "result"}
            </Text>
          </HStack>
        ))}
        {items.length > 3 ? (
          <Text color="gray.500" fontSize="xs">
            +{items.length - 3} more result items
          </Text>
        ) : null}
      </Stack>
    );
  };

  return (
    <Box bg="gray.900" color="white" minH="100vh">
      <Navbar />
      <Box maxW="7xl" mx="auto" px={{ base: 4, md: 6 }} py={6}>
        <Stack spacing={5}>
          <HStack justify="space-between" align="center" flexWrap="wrap" gap={3}>
            <Box>
              <Heading size="lg">Processing Jobs</Heading>
              <Text color="gray.400" fontSize="sm">
                Background conversions, MIME ingest tasks, and worker health checks.
              </Text>
            </Box>
            <HStack>
              <HStack spacing={2}>
                <Switch
                  id="job-auto-refresh"
                  isChecked={autoRefresh}
                  onChange={(event) => setAutoRefresh(event.target.checked)}
                />
                <Text color="gray.300" fontSize="sm">
                  Auto-refresh
                </Text>
              </HStack>
              <Button
                size="sm"
                leftIcon={<RepeatIcon />}
                onClick={() => loadJobs()}
                variant="outline"
              >
                Refresh
              </Button>
              <Button
                size="sm"
                leftIcon={<AddIcon />}
                colorScheme="teal"
                isLoading={isCreating}
                onClick={enqueueHealthCheck}
              >
                Health Check
              </Button>
            </HStack>
          </HStack>

          <Grid templateColumns={{ base: "1fr 1fr", md: "repeat(4, 1fr)" }} gap={3}>
            {["queued", "running", "succeeded", "failed"].map((status) => (
              <GridItem
                key={status}
                borderWidth={1}
                borderColor="gray.700"
                bg="gray.800"
                px={4}
                py={3}
              >
                <Text color="gray.400" fontSize="xs" textTransform="uppercase">
                  {status}
                </Text>
                <Text fontSize="2xl" fontWeight="semibold">
                  {counts[status] || 0}
                </Text>
              </GridItem>
            ))}
          </Grid>

          {isLoading ? (
            <HStack>
              <Spinner color="teal.300" />
              <Text color="gray.400">Loading jobs...</Text>
            </HStack>
          ) : error ? (
            <Text color="red.300">{error}</Text>
          ) : jobs.length === 0 ? (
            <Text color="gray.400">No jobs found.</Text>
          ) : (
            <Box overflowX="auto" borderWidth={1} borderColor="gray.700">
              <Table size="sm" variant="simple">
                <Thead bg="gray.800">
                  <Tr>
                    <Th color="gray.300">Status</Th>
                    <Th color="gray.300">Type</Th>
                    <Th color="gray.300">Created</Th>
                    <Th color="gray.300">Input</Th>
                    <Th color="gray.300">Results</Th>
                    <Th color="gray.300">Error</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {jobs.map((job) => {
                    const isHighlighted = highlightedJobId === job.id;
                    return (
                      <Tr
                        key={job.id}
                        bg={isHighlighted ? "teal.900" : undefined}
                        borderLeft={isHighlighted ? "4px solid" : undefined}
                        borderLeftColor={isHighlighted ? "teal.300" : undefined}
                      >
                        <Td>
                          <VStack align="start" spacing={1}>
                            <Badge colorScheme={statusColor(job.status)}>
                              {job.status}
                            </Badge>
                            <Text color="gray.500" fontSize="xs">
                              Priority {job.priority}
                            </Text>
                          </VStack>
                        </Td>
                        <Td>
                          <VStack align="start" spacing={1}>
                            <Text>{job.job_type}</Text>
                            <Code colorScheme="gray" fontSize="xs">
                              {job.id}
                            </Code>
                          </VStack>
                        </Td>
                        <Td>
                          <VStack align="start" spacing={1}>
                            <Text>{formatDate(job.created_at)}</Text>
                            <Text color="gray.500" fontSize="xs">
                              Updated {formatDate(job.updated_at)}
                            </Text>
                          </VStack>
                        </Td>
                        <Td>
                          <Code
                            colorScheme="gray"
                            display="block"
                            fontSize="xs"
                            maxW="72"
                            overflowX="auto"
                            whiteSpace="pre-wrap"
                          >
                            {JSON.stringify(job.input_payload || {}, null, 2)}
                          </Code>
                        </Td>
                        <Td>{renderResultActions(job)}</Td>
                        <Td color={job.error ? "red.300" : "gray.500"}>
                          {job.error || "-"}
                        </Td>
                      </Tr>
                    );
                  })}
                </Tbody>
              </Table>
            </Box>
          )}
        </Stack>
      </Box>
    </Box>
  );
}
