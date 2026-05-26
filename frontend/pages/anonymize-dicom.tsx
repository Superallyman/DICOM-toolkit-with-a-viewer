import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import {
  Box, Button, Checkbox, Heading, Input, Textarea, VStack, Alert, AlertTitle,
  Text, Link, HStack, Select, Spinner, Divider, FormLabel, Tooltip
} from "@chakra-ui/react";
import Navbar from "../components/Navbar";
import { getToken, parseToken } from "../src/utils/auth";
import { API_URL, buildStudyViewerUrl } from "../src/utils/env";

const RULE_PRESETS: Record<string, string> = {
  "": "",
  "Minimal (empty name, hash ID)": JSON.stringify(
    { PatientName: "empty", PatientID: "hash" },
    null, 2
  ),
  "Aggressive (remove most identifiers)": JSON.stringify(
    {
      PatientName: "empty",
      PatientID: "hash",
      OtherPatientIDs: "remove",
      PatientBirthDate: "remove",
      PatientAddress: "remove",
      PatientTelephoneNumbers: "remove",
      IssuerOfPatientID: "remove",
      ReferringPhysicianName: "empty",
      InstitutionName: "remove"
    },
    null, 2
  ),
};

export default function AnonymizeDicomPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [deletePrivateTags, setDeletePrivateTags] = useState(true);
  const [rulesJson, setRulesJson] = useState("");
  const [preset, setPreset] = useState("");
  const [banner, setBanner] = useState("Ready.");
  const [isLoading, setIsLoading] = useState(false);

  const [downloadUrl, setDownloadUrl] = useState("");
  const [metadata, setMetadata] = useState<any>(null);
  const [studyUID, setStudyUID] = useState<string | null>(null);

  // Optional advanced: allow setting a server-side output dir (leave empty)
  const [outputDir, setOutputDir] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    try {
      parseToken(token);
    } catch {
      router.push("/login");
    }
  }, [router]);

  const handlePresetChange = (value: string) => {
    setPreset(value);
    setRulesJson(RULE_PRESETS[value] ?? "");
  };

  const validateRules = (): string | null => {
    if (!rulesJson.trim()) return null;
    try {
      JSON.parse(rulesJson);
      return null;
    } catch (e: any) {
      return e.message || "Invalid JSON";
    }
  };

  const handleAnonymize = async () => {
    if (!file) {
      setBanner("Please choose a DICOM file first.");
      return;
    }
    const rulesErr = validateRules();
    if (rulesErr) {
      setBanner(`Rules JSON error: ${rulesErr}`);
      return;
    }

    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }

    try {
      setIsLoading(true);
      setBanner("Uploading and anonymizing…");

      const form = new FormData();
      form.append("file", file);
      form.append("delete_private_tags", String(deletePrivateTags));
      if (rulesJson.trim()) form.append("rules_json", rulesJson);

      const qs = outputDir.trim()
        ? `?output_dir=${encodeURIComponent(outputDir.trim())}`
        : "";

      const res = await fetch(`${API_URL}/deid/anonymize${qs}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: form,
      });

      if (!res.ok) {
        const txt = await res.text();
        setBanner(`Anonymize failed: ${res.status} ${res.statusText} — ${txt}`);
        setIsLoading(false);
        return;
      }

      const data = await res.json();
      setDownloadUrl(data.download_url || "");
      setMetadata(data.metadata || null);
      setStudyUID(data.study_instance_uid || null);
      setBanner("Anonymization complete.");
    } catch (err) {
      console.error(err);
      setBanner("Network error or server unreachable.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleViewInOHIF = () => {
    if (!studyUID) return;
    window.open(buildStudyViewerUrl(studyUID), "_blank", "noopener,noreferrer");
  };

  return (
    <Box bg="gray.900" color="white" minH="100vh" p={6}>
      <Navbar />
      <Alert status="info" bg="gray.800" borderColor="gray.700" borderWidth={1} rounded="md" my={4}>
        <AlertTitle>{banner}</AlertTitle>
      </Alert>

      <Box bg="gray.800" borderColor="gray.700" borderWidth={1} rounded="md" p={6} my={4}>
        <VStack spacing={5} align="stretch">
          <Heading size="lg">Anonymize DICOM</Heading>

          <Box>
            <FormLabel>Select a DICOM file</FormLabel>
            <Input
              type="file"
              accept=".dcm,.dicom,application/dicom"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </Box>

          <HStack align="start" spacing={6}>
            <Box flex={1}>
              <FormLabel>Rule preset</FormLabel>
              <Select
                value={preset}
                onChange={(e) => handlePresetChange(e.target.value)}
              >
                {Object.keys(RULE_PRESETS).map((k) => (
                  <option key={k} value={k} style={{ backgroundColor: "#1a202c" }}>
                    {k || "None"}
                  </option>
                ))}
              </Select>
            </Box>

            <Box flex={2}>
              <FormLabel>
                Custom rules JSON{" "}
                <Tooltip label='e.g. { "PatientName": "empty", "PatientID": "hash" }'>
                  <Text as="span" color="gray.400">(optional)</Text>
                </Tooltip>
              </FormLabel>
              <Textarea
                placeholder='{"PatientName":"empty","PatientID":"hash"}'
                rows={8}
                value={rulesJson}
                onChange={(e) => setRulesJson(e.target.value)}
                fontFamily="mono"
              />
              {rulesJson && validateRules() && (
                <Text color="red.300" mt={1}>JSON error: {validateRules()}</Text>
              )}
            </Box>
          </HStack>

          <HStack spacing={6}>
            <Checkbox
              isChecked={deletePrivateTags}
              onChange={(e) => setDeletePrivateTags(e.target.checked)}
            >
              Delete private tags
            </Checkbox>

            <Tooltip
              label="Optional. Only set if you want the server to save the anonymized file to a specific path (e.g., its persistent_output directory) so the viewer can see it."
            >
              <Box>
                <FormLabel m={0} fontSize="sm">Server output directory (optional)</FormLabel>
                <Input
                  placeholder="e.g. C:\path\to\persistent_output"
                  value={outputDir}
                  onChange={(e) => setOutputDir(e.target.value)}
                  width="420px"
                />
              </Box>
            </Tooltip>
          </HStack>

          <Button colorScheme="teal" onClick={handleAnonymize} isDisabled={isLoading || !file}>
            {isLoading ? <Spinner size="sm" /> : "Anonymize"}
          </Button>
        </VStack>
      </Box>

      {!!downloadUrl && (
        <Box bg="gray.800" borderColor="gray.700" borderWidth={1} rounded="md" p={6} my={4}>
          <VStack spacing={4} align="stretch">
            <Heading size="md">Result</Heading>
            <Text>
              ✅ <b>Anonymized DICOM ready.</b>
            </Text>
            <HStack>
              <Text>Download:</Text>
              <Link href={downloadUrl} target="_blank" color="teal.300" isExternal>
                {downloadUrl}
              </Link>
            </HStack>

            <Divider />

            {studyUID && (
              <Button colorScheme="green" onClick={handleViewInOHIF}>
                View in OHIF
              </Button>
            )}

            {metadata && (
              <>
                <Heading size="sm" mt={2}>Extracted Metadata</Heading>
                <Textarea readOnly rows={12} value={JSON.stringify(metadata, null, 2)} />
              </>
            )}
          </VStack>
        </Box>
      )}
    </Box>
  );
}
