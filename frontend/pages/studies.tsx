// pages/studies.tsx
import { useEffect, useState } from "react";
import axios from "axios";
import {
  Box,
  Heading,
  Text,
  Button,
  VStack,
  HStack,
  Divider,
  Input,
  InputGroup,
  InputLeftElement,
  Icon,
  Spinner,
  Badge,
} from "@chakra-ui/react";
import ThumbnailsGrid from "../components/ThumbnailsGrid";
import { SearchIcon } from "@chakra-ui/icons";
import Navbar from "../components/Navbar";
import { API_URL, buildStudyViewerUrl } from "../src/utils/env";

/**
 * Minimal DICOMweb JSON item type:
 * Each tag key maps to an object that may contain a Value array.
 * We only read from .Value[0] (or the whole array), so this is sufficient.
 */
type DicomJsonItem = Record<string, { Value?: any[] } | undefined>;

// helpers to read DICOM JSON
const v = (item: DicomJsonItem, tag: string) =>
  (item?.[tag]?.Value ?? [])[0] ?? "";
const arr = (item: DicomJsonItem, tag: string) =>
  ((item?.[tag]?.Value ?? []) as string[]);

interface Thumbnail {
  sopInstanceUID: string;
  thumbnailUrl: string;
  viewerUrl: string;
}

interface Study {
  StudyInstanceUID: string;
  PatientName: string;
  StudyDate: string;
  AccessionNumber: string;
  StudyDescription: string;
  ModalitiesInStudy: string[];
}

interface StudyWithThumbs extends Study {
  thumbnails?: Thumbnail[];
}

export default function StudiesPage() {
  const [studies, setStudies] = useState<StudyWithThumbs[]>([]);
  const [filteredStudies, setFilteredStudies] = useState<StudyWithThumbs[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [loadingThumbs, setLoadingThumbs] = useState(false);

  // ensure page-wide dark background (prevents any white band)
  useEffect(() => {
    const prev = document.body.style.backgroundColor;
    document.body.style.backgroundColor = "#111827"; // gray.900
    return () => {
      document.body.style.backgroundColor = prev;
    };
  }, []);

  useEffect(() => {
    const fetchStudiesAndThumbs = async () => {
      try {
        const { data: mapped } = await axios.get<Study[]>(
          `${API_URL}/studies`,
          {
            params: {
              limit: 101,
              offset: 0,
            },
          }
        );

        setLoadingThumbs(true);
        const enriched = await Promise.all(
          mapped.map(async (study) => {
            const thumbs = await fetchThumbnails(study.StudyInstanceUID);
            return { ...study, thumbnails: thumbs };
          })
        );

        setStudies(enriched);
        setFilteredStudies(enriched);
      } catch (err) {
        console.error("Failed to fetch studies:", err);
      } finally {
        setLoadingThumbs(false);
      }
    };

    fetchStudiesAndThumbs();
  }, []);

  useEffect(() => {
    const term = searchTerm.toLowerCase();
    const filtered = studies.filter((s) =>
      [s.PatientName, s.StudyDescription, s.AccessionNumber].some((f) =>
        (f || "").toLowerCase().includes(term)
      )
    );
    setFilteredStudies(filtered);
  }, [searchTerm, studies]);

  // Open the mounted OHIF viewer served by FastAPI
  const launchViewer = (studyUID: string) => {
    window.open(buildStudyViewerUrl(studyUID), "_blank", "noopener,noreferrer");
  };

  return (
    <Box bg="gray.900" minH="100vh">
      <Navbar />

      <Box maxW="7xl" mx="auto" px={{ base: 4, md: 6 }} py={6}>
        <Heading size="lg" mb={5} color="gray.100">
          📋 Available Studies
        </Heading>

        <InputGroup mb={6} maxW="lg">
          <InputLeftElement pointerEvents="none">
            <Icon as={SearchIcon} color="gray.400" />
          </InputLeftElement>
          <Input
            type="text"
            placeholder="Search by Patient, Description, or Accession #"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            bg="gray.800"
            color="gray.100"
            borderColor="gray.700"
            _placeholder={{ color: "gray.500" }}
            _hover={{ borderColor: "gray.600" }}
            _focus={{
              borderColor: "teal.400",
              boxShadow: "0 0 0 1px var(--chakra-colors-teal-400)",
            }}
          />
        </InputGroup>

        <VStack align="stretch" spacing={5}>
          {filteredStudies.map((study) => (
            <Box
              key={study.StudyInstanceUID}
              bg="gray.800"
              border="1px solid"
              borderColor="gray.700"
              borderRadius="lg"
              p={5}
            >
              <HStack justify="space-between" align="start" flexWrap="wrap" gap={4}>
                <VStack align="start" spacing={1}>
                  <Text color="gray.200">
                    <b>Patient:</b> {study.PatientName || "Anonymous"}
                  </Text>
                  <Text color="gray.200">
                    <b>Date:</b> {study.StudyDate || "N/A"}
                  </Text>
                  <Text color="gray.200">
                    <b>Description:</b> {study.StudyDescription || "N/A"}
                  </Text>
                  <HStack>
                    <Text color="gray.200">
                      <b>Modality:</b>
                    </Text>
                    {study.ModalitiesInStudy?.length ? (
                      <HStack spacing={2}>
                        {study.ModalitiesInStudy.map((m) => (
                          <Badge
                            key={m}
                            colorScheme="purple"
                            variant="subtle"
                            px={2}
                            py={0.5}
                          >
                            {m}
                          </Badge>
                        ))}
                      </HStack>
                    ) : (
                      <Text color="gray.400">N/A</Text>
                    )}
                  </HStack>
                  <Text color="gray.200">
                    <b>Accession #:</b> {study.AccessionNumber || "N/A"}
                  </Text>
                </VStack>

                <Button
                  colorScheme="teal"
                  bg="teal.500"
                  _hover={{ bg: "teal.400" }}
                  onClick={() => launchViewer(study.StudyInstanceUID)}
                >
                  🖥️ Launch Viewer
                </Button>
              </HStack>

              <Divider my={4} borderColor="gray.700" />

              {loadingThumbs ? (
                <Spinner size="sm" color="gray.400" />
              ) : (
                <ThumbnailsGrid thumbnails={study.thumbnails || []} />
              )}
            </Box>
          ))}
        </VStack>

        {filteredStudies.length === 0 && (
          <Text mt={6} color="gray.400">
            No matching studies found.
          </Text>
        )}
      </Box>
    </Box>
  );
}

/**
 * Build thumbnails using your DICOMWeb routes
 */
const fetchThumbnails = async (studyUID: string): Promise<Thumbnail[]> => {
  try {
    // 1) Get series for the study (typed)
    const { data: series } = await axios.get<DicomJsonItem[]>(
      `${API_URL}/dicomweb/studies/${encodeURIComponent(
        studyUID
      )}/series`,
      { headers: { Accept: "application/dicom+json" } }
    );

    const allThumbs: Thumbnail[] = [];

    // 2) For each series, fetch instances and construct thumbnail URLs
    for (const s of series) {
      const seriesUID = v(s, "0020000E");
      if (!seriesUID) continue;

      const { data: instances } = await axios.get<DicomJsonItem[]>(
        `${API_URL}/dicomweb/studies/${encodeURIComponent(
          studyUID
        )}/series/${encodeURIComponent(seriesUID)}/instances`,
        { headers: { Accept: "application/dicom+json" } }
      );

      for (const inst of instances) {
        const sop = v(inst, "00080018");
        if (!sop) continue;

        allThumbs.push({
          sopInstanceUID: sop,
          thumbnailUrl: `${API_URL}/dicomweb/thumbnails/${encodeURIComponent(
            studyUID
          )}/${encodeURIComponent(seriesUID)}/${encodeURIComponent(sop)}`,
          viewerUrl: buildStudyViewerUrl(studyUID),
        });
      }
    }

    return allThumbs;
  } catch (err) {
    console.warn("Failed to load thumbnails:", err);
    return [];
  }
};
