import React, { useEffect, useState, useRef, useCallback } from "react";
import {
  Box, Button, Input, Select, Table, Thead, Tbody, Tr, Th, Td, Badge,
  Spinner, Text, Heading, Tabs, TabList, TabPanels, Tab, TabPanel,
  SimpleGrid, Stat, StatLabel, StatNumber, HStack, Accordion, AccordionItem,
  AccordionButton, AccordionPanel, AccordionIcon, Progress,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalCloseButton, ModalBody, ModalFooter,
  useToast, Tag, VStack, Code, Skeleton, SkeletonText, Switch
} from "@chakra-ui/react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";
import api from "../src/utils/axiosInstance";
import { format } from "date-fns";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import Navbar from "../components/Navbar";
import { getToken, parseToken } from "../src/utils/auth";
import { useRouter } from "next/router";

interface EventLog {
  id: string;
  event_type: string;
  message: string;
  success: boolean;
  timestamp: string;
  study_uid?: string;
}

type DeidStatus = "pass" | "review" | "fail";

interface DeidIssue {
  field: string;
  tag?: string;
  reason: string;
  suggested?: string;
  confidence?: number;
}

interface DeidAudit {
  status: DeidStatus;
  issues: DeidIssue[];
  summary?: string;
  scannedCount?: number;
}

const useDebouncedValue = <T,>(value: T, delay = 400) => {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
};

const AdminDashboard = () => {
  const [logs, setLogs] = useState<EventLog[]>([]);
  const [filteredLogs, setFilteredLogs] = useState<EventLog[]>([]);
  const [eventTypeFilter, setEventTypeFilter] = useState<string>("");
  const [successFilter, setSuccessFilter] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const debouncedSearch = useDebouncedValue(search, 450);

  const [loading, setLoading] = useState<boolean>(true);
  const [sortBy, setSortBy] = useState<"timestamp" | "event_type">("timestamp");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState<number>(1);
  const [hasMore, setHasMore] = useState<boolean>(true);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(false);
  const lastUpdatedRef = useRef<Date | null>(null);

  const [inflight, setInflight] = useState(0); // global network indicator
  const controllerRef = useRef<AbortController | null>(null); // cancel in-flight fetch
  const observer = useRef<IntersectionObserver | null>(null);
  const router = useRouter();

  const [auditOpen, setAuditOpen] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditResult, setAuditResult] = useState<DeidAudit | null>(null);
  const [auditStudyUID, setAuditStudyUID] = useState<string | null>(null);
  const [auditCache, setAuditCache] = useState<Record<string, DeidAudit>>({});
  const toast = useToast();

  // --- auth gate
  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
    } else {
      try {
        parseToken(token);
      } catch {
        router.push("/login");
      }
    }
  }, []);

  // --- axios interceptors -> top progress bar
  useEffect(() => {
    const req = api.interceptors.request.use((config) => {
      setInflight((n) => n + 1);
      return config;
    });
    const res = api.interceptors.response.use(
      (r) => {
        setInflight((n) => Math.max(0, n - 1));
        return r;
      },
      (err) => {
        setInflight((n) => Math.max(0, n - 1));
        return Promise.reject(err);
      }
    );
    return () => {
      api.interceptors.request.eject(req);
      api.interceptors.response.eject(res);
    };
  }, []);

  const fetchLogs = async (_pageNumber: number) => {
    try {
      // Abort any previous fetch for snappier UI when changing filters/search
      if (controllerRef.current) controllerRef.current.abort();
      controllerRef.current = new AbortController();

      const res = await api.get<EventLog[]>("/admin/events", {
        params: {
          limit: 500,
          event_type: eventTypeFilter || undefined,
          success: successFilter !== "" ? successFilter === "true" : undefined,
          search: debouncedSearch || undefined,
        },
        signal: controllerRef.current.signal as any,
      });

      const newLogs = res.data;
      if (newLogs.length === 0) setHasMore(false);
      setLogs((prev) => [...prev, ...newLogs]);
      lastUpdatedRef.current = new Date();
    } catch (err: any) {
      if (err?.name !== "CanceledError" && err?.message !== "canceled") {
        console.error("Error fetching logs", err);
        toast({
          title: "Failed to fetch logs",
          description: err?.message || "Unexpected error",
          status: "error",
          isClosable: true,
        });
      }
    } finally {
      setLoading(false);
    }
  };

  const runDeidAudit = async (studyUID: string) => {
    try {
      setAuditError(null);
      setAuditLoading(true);
      setAuditStudyUID(studyUID);
      setAuditOpen(true);

      if (auditCache[studyUID]) {
        setAuditResult(auditCache[studyUID]);
        setAuditLoading(false);
        return;
      }

      const res = await api.get<DeidAudit>("/ai/deid/audit", {
        params: { study_uid: studyUID },
      });

      const data = res.data || { status: "pass", issues: [] };
      setAuditResult(data);
      setAuditCache((prev) => ({ ...prev, [studyUID]: data }));
    } catch (err: any) {
      setAuditError(err?.response?.data?.detail || "Audit failed");
      toast({
        title: "De-ID audit failed",
        description: err?.message || "Unexpected error",
        status: "error",
        isClosable: true,
      });
    } finally {
      setAuditLoading(false);
    }
  };

  // Infinite-load trigger
  useEffect(() => {
    fetchLogs(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  // Reset list when filters/search change (debounced search)
  useEffect(() => {
    setLogs([]);
    setPage(1);
    setHasMore(true);
    setLoading(true);
    fetchLogs(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventTypeFilter, successFilter, debouncedSearch]);

  // Optional auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(() => {
      // refresh first page — replace list (not append)
      setLoading(true);
      setLogs([]);
      setPage(1);
      setHasMore(true);
      fetchLogs(1);
    }, 15000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, eventTypeFilter, successFilter, debouncedSearch]);

  // Client-side filtering/sorting
  useEffect(() => {
    let filtered = [...logs];
    if (eventTypeFilter) filtered = filtered.filter((log) => log.event_type === eventTypeFilter);
    if (successFilter) filtered = filtered.filter((log) => log.success === (successFilter === "true"));
    if (debouncedSearch.trim()) {
      const s = debouncedSearch.toLowerCase();
      filtered = filtered.filter((log) =>
        (log.message && log.message.toLowerCase().includes(s)) ||
        (log.study_uid && log.study_uid.toLowerCase().includes(s))
      );
    }
    if (sortBy) {
      filtered.sort((a, b) => {
        const aVal = a[sortBy] as any;
        const bVal = b[sortBy] as any;
        return sortOrder === "asc" ? (aVal > bVal ? 1 : -1) : (aVal < bVal ? 1 : -1);
      });
    }
    setFilteredLogs(filtered);
  }, [logs, eventTypeFilter, successFilter, debouncedSearch, sortBy, sortOrder]);

  // Group by Study UID (fallback "General")
  const groupedByStudyUID: Record<string, EventLog[]> = filteredLogs.reduce((acc, log) => {
    const key = log.study_uid || "General";
    if (!acc[key]) acc[key] = [];
    acc[key].push(log);
    return acc;
  }, {} as Record<string, EventLog[]>);

  const lastLogRef = useCallback(
    (node: HTMLTableRowElement | null) => {
      if (loading) return;
      if (observer.current) observer.current.disconnect();
      observer.current = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && hasMore) {
          setPage((prev) => prev + 1);
        }
      });
      if (node) observer.current.observe(node);
    },
    [loading, hasMore]
  );

  const downloadCSV = () => {
    const rows = [["Study UID", "Timestamp", "Event Type", "Message", "Success"]];
    filteredLogs.forEach((log) =>
      rows.push([log.study_uid || "", log.timestamp, log.event_type, log.message, log.success ? "true" : "false"])
    );
    const blob = new Blob([rows.map((r) => r.join(",")).join("\n")], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "event_logs.csv";
    a.click();
  };

  const downloadPDF = () => {
    const doc = new jsPDF();
    doc.setFontSize(18);
    doc.text("Grouped Event Logs", 14, 22);
    autoTable(doc, {
      startY: 30,
      head: [["Study UID", "Timestamp", "Event Type", "Message", "Success"]],
      body: filteredLogs.map((log) => [
        log.study_uid || "",
        format(new Date(log.timestamp), "yyyy-MM-dd HH:mm:ss"),
        log.event_type,
        log.message,
        log.success ? "Success" : "Failed",
      ]),
    });
    doc.save("event_logs.pdf");
  };

  const chartData = [
    { name: "Success", count: logs.filter((l) => l.success).length },
    { name: "Failed", count: logs.filter((l) => !l.success).length },
  ];

  const statusColor = (s: DeidStatus) => (s === "pass" ? "green" : s === "review" ? "yellow" : "red");

  return (
    <Box p={4} bg="gray.900" minH="100vh" color="white">
      {/* Top network progress bar */}
      {inflight > 0 && (
        <Progress size="xs" isIndeterminate position="fixed" top="0" left="0" right="0" zIndex="tooltip" colorScheme="teal" />
      )}

      <Navbar />
      <Heading size="lg" mb={6}>
        Admin Dashboard
      </Heading>

      {/* Stats — skeleton while first load */}
      <SimpleGrid columns={{ base: 1, md: 3 }} spacing={4} mb={6}>
        <Stat p={4} bg="gray.800" borderRadius="md">
          <StatLabel>Total Logs</StatLabel>
          <Skeleton isLoaded={!loading}>
            <StatNumber>{logs.length}</StatNumber>
          </Skeleton>
        </Stat>
        <Stat p={4} bg="gray.800" borderRadius="md">
          <StatLabel>Success %</StatLabel>
          <Skeleton isLoaded={!loading}>
            <StatNumber>
              {logs.length ? ((logs.filter((l) => l.success).length / logs.length) * 100).toFixed(1) : 0}%
            </StatNumber>
          </Skeleton>
        </Stat>
        <Stat p={4} bg="gray.800" borderRadius="md">
          <StatLabel>Failed %</StatLabel>
          <Skeleton isLoaded={!loading}>
            <StatNumber>
              {logs.length ? ((logs.filter((l) => !l.success).length / logs.length) * 100).toFixed(1) : 0}%
            </StatNumber>
          </Skeleton>
        </Stat>
      </SimpleGrid>

      <Tabs isFitted variant="enclosed">
        <TabList mb="1em">
          <Tab>Analytics</Tab>
          <Tab>
            Logs
            {lastUpdatedRef.current && (
              <Text as="span" fontSize="xs" color="gray.400" ml={2}>
                {`(updated ${format(lastUpdatedRef.current, "HH:mm:ss")})`}
              </Text>
            )}
          </Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <Box bg="gray.800" p={4} borderRadius="md" h="320px">
              {loading ? (
                <Skeleton height="100%" borderRadius="md" />
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={chartData}>
                    <XAxis dataKey="name" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="count" fill="#38B2AC" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Box>
          </TabPanel>

          <TabPanel>
            <Box bg="gray.800" p={4} borderRadius="md" mb={4}>
              <HStack spacing={4} mb={4} flexWrap="wrap">
                <Select
                  placeholder="Filter by Event Type"
                  value={eventTypeFilter}
                  onChange={(e) => setEventTypeFilter(e.target.value)}
                >
                  {[...new Set(logs.map((l) => l.event_type))].map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </Select>
                <Select
                  placeholder="Filter by Status"
                  value={successFilter}
                  onChange={(e) => setSuccessFilter(e.target.value)}
                >
                  <option value="true">Success</option>
                  <option value="false">Failed</option>
                </Select>
                <Input placeholder="Search..." value={search} onChange={(e) => setSearch(e.target.value)} />
                <Button colorScheme="blue" onClick={downloadCSV}>
                  Export CSV
                </Button>
                <Button colorScheme="pink" onClick={downloadPDF}>
                  Export PDF
                </Button>

                <HStack ml="auto" spacing={3}>
                  <Switch isChecked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)}>
                    Auto-refresh
                  </Switch>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setLoading(true);
                      setLogs([]);
                      setPage(1);
                      setHasMore(true);
                      fetchLogs(1);
                    }}
                  >
                    Refresh
                  </Button>
                </HStack>
              </HStack>

              {/* Table / groups — skeleton rows on initial load */}
              {loading ? (
                <VStack align="stretch" spacing={3}>
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Box key={i} p={4} bg="gray.700" borderRadius="md">
                      <Skeleton height="18px" mb={3} />
                      <SkeletonText noOfLines={4} spacing="3" />
                    </Box>
                  ))}
                </VStack>
              ) : (
                <Accordion allowMultiple defaultIndex={[0]}>
                  {Object.entries(groupedByStudyUID).map(([studyUID, group]) => (
                    <AccordionItem key={studyUID}>
                      <h2>
                        <AccordionButton>
                          <Box flex="1" textAlign="left">
                            Study UID: <strong>{studyUID}</strong> ({group.length} logs)
                          </Box>

                          {studyUID !== "General" ? (
                            <HStack spacing={3} mr={3}>
                              {auditCache[studyUID] && (
                                <Badge colorScheme={statusColor(auditCache[studyUID].status)}>
                                  {auditCache[studyUID].status.toUpperCase()}
                                </Badge>
                              )}
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={(e) => {
                                  e.preventDefault();
                                  runDeidAudit(studyUID);
                                }}
                              >
                                Run De-ID Audit
                              </Button>
                            </HStack>
                          ) : (
                            <Button
                              size="sm"
                              variant="outline"
                              mr={3}
                              onClick={(e) => {
                                e.preventDefault();
                                const uid = window.prompt("Enter StudyInstanceUID to audit");
                                if (uid) runDeidAudit(uid.trim());
                              }}
                            >
                              Run De-ID Audit…
                            </Button>
                          )}

                          <AccordionIcon />
                        </AccordionButton>
                      </h2>
                      <AccordionPanel>
                        <Table size="sm">
                          <Thead>
                            <Tr>
                              <Th>Timestamp</Th>
                              <Th>Study UID</Th>
                              <Th>Type</Th>
                              <Th>Message</Th>
                              <Th>Status</Th>
                            </Tr>
                          </Thead>
                          <Tbody>
                            {group.map((log, idx) => (
                              <Tr key={log.id + "-" + idx} ref={idx === group.length - 1 ? lastLogRef : null}>
                                <Td>{format(new Date(log.timestamp), "yyyy-MM-dd HH:mm:ss")}</Td>
                                <Td title={log.study_uid || ""}>
                                  {log.study_uid ? (
                                    <HStack spacing={2}>
                                      <Code>{log.study_uid}</Code>
                                      <Button
                                        size="xs"
                                        onClick={() => navigator.clipboard.writeText(log.study_uid!)}
                                      >
                                        Copy
                                      </Button>
                                      <Button
                                        size="xs"
                                        variant="outline"
                                        onClick={() => runDeidAudit(log.study_uid!)}
                                      >
                                        Audit
                                      </Button>
                                    </HStack>
                                  ) : (
                                    <span>-</span>
                                  )}
                                </Td>
                                <Td>{log.event_type}</Td>
                                <Td>{log.message}</Td>
                                <Td>
                                  <Badge colorScheme={log.success ? "green" : "red"}>
                                    {log.success ? "✔" : "✖"}
                                  </Badge>
                                </Td>
                              </Tr>
                            ))}
                          </Tbody>
                        </Table>
                      </AccordionPanel>
                    </AccordionItem>
                  ))}
                </Accordion>
              )}
            </Box>
          </TabPanel>
        </TabPanels>
      </Tabs>

      {/* Audit Modal */}
      <Modal isOpen={auditOpen} onClose={() => setAuditOpen(false)} size="xl" isCentered>
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader>De-ID Audit {auditStudyUID ? `— ${auditStudyUID}` : ""}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {auditLoading && (
              <VStack align="stretch" spacing={3}>
                <Skeleton height="18px" />
                <SkeletonText noOfLines={5} spacing="3" />
              </VStack>
            )}

            {!auditLoading && auditError && <Text color="red.300">{auditError}</Text>}

            {!auditLoading && !auditError && auditResult && (
              <VStack align="stretch" spacing={4}>
                <HStack>
                  <Text fontWeight="bold">Status:</Text>
                  <Badge colorScheme={statusColor(auditResult.status)}>
                    {auditResult.status.toUpperCase()}
                  </Badge>
                </HStack>

                {typeof auditResult.scannedCount === "number" && (
                  <Text>Scanned tags: {auditResult.scannedCount}</Text>
                )}

                {auditResult.summary && <Text>{auditResult.summary}</Text>}

                {auditResult.issues?.length ? (
                  <Box>
                    <Heading size="sm" mb={2}>
                      Issues
                    </Heading>
                    <Table size="sm" variant="simple">
                      <Thead>
                        <Tr>
                          <Th>Field</Th>
                          <Th>Tag</Th>
                          <Th>Reason</Th>
                          <Th>Suggested</Th>
                        </Tr>
                      </Thead>
                      <Tbody>
                        {auditResult.issues.map((iss, idx) => (
                          <Tr key={idx}>
                            <Td>
                              <Code colorScheme="gray">{iss.field}</Code>
                            </Td>
                            <Td>{iss.tag || "-"}</Td>
                            <Td>{iss.reason}</Td>
                            <Td>{iss.suggested ? <Tag variant="subtle">{iss.suggested}</Tag> : "-"}</Td>
                          </Tr>
                        ))}
                      </Tbody>
                    </Table>
                  </Box>
                ) : (
                  <Text>No PHI-like text detected 🎉</Text>
                )}
              </VStack>
            )}
          </ModalBody>
          <ModalFooter>
            <Button onClick={() => setAuditOpen(false)}>Close</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </Box>
  );
};

export default AdminDashboard;
