import { RepeatIcon, ExternalLinkIcon } from "@chakra-ui/icons";
import { Box, Button, Flex, Heading, HStack, IconButton, Spinner, Tooltip } from "@chakra-ui/react";
import { useEffect, useMemo, useState } from "react";
import Navbar from "../components/Navbar";
import { buildLocalViewerUrl } from "../src/utils/env";

export default function LocalDicomViewerPage() {
  const [viewerSession, setViewerSession] = useState(() => Date.now());
  const [viewerReady, setViewerReady] = useState(false);
  const localViewerUrl = buildLocalViewerUrl();
  const embeddedViewerUrl = useMemo(() => {
    const separator = localViewerUrl.includes("?") ? "&" : "?";
    return `${localViewerUrl}${separator}session=${viewerSession}`;
  }, [localViewerUrl, viewerSession]);

  useEffect(() => {
    let cancelled = false;

    const resetViewerRuntimeCache = async () => {
      try {
        if ("serviceWorker" in navigator) {
          const registrations = await navigator.serviceWorker.getRegistrations();
          await Promise.all(registrations.map((registration) => registration.unregister()));
        }

        if ("caches" in window) {
          const cacheNames = await caches.keys();
          await Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName)));
        }
      } finally {
        if (!cancelled) {
          setViewerSession(Date.now());
          setViewerReady(true);
        }
      }
    };

    resetViewerRuntimeCache();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") {
        setViewerSession(Date.now());
      }
    };

    document.addEventListener("visibilitychange", refreshWhenVisible);
    window.addEventListener("pageshow", refreshWhenVisible);

    return () => {
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      window.removeEventListener("pageshow", refreshWhenVisible);
    };
  }, []);

  return (
    <Box bg="gray.900" h="100dvh" overflow="hidden" display="flex" flexDirection="column">
      <Navbar />

      <Flex
        flexShrink={0}
        px={{ base: 3, md: 6 }}
        pb={3}
        gap={4}
        align={{ base: "stretch", md: "center" }}
        justify="space-between"
        direction={{ base: "column", md: "row" }}
      >
        <Heading size="md" color="gray.100">
          Local DICOM Viewer
        </Heading>
        <HStack spacing={2} alignSelf={{ base: "stretch", md: "auto" }}>
          <Tooltip label="Load another study" hasArrow openDelay={300}>
            <IconButton
              aria-label="Load another local DICOM study"
              icon={<RepeatIcon />}
              colorScheme="teal"
              onClick={() => setViewerSession(Date.now())}
              flex={{ base: 1, md: "initial" }}
            />
          </Tooltip>
          <Tooltip label="Open full screen" hasArrow openDelay={300}>
            <Button
              as="a"
              href={localViewerUrl}
              target="_blank"
              rel="noopener noreferrer"
              colorScheme="teal"
              leftIcon={<ExternalLinkIcon />}
              flex={{ base: 1, md: "initial" }}
            >
              Full Screen
            </Button>
          </Tooltip>
        </HStack>
      </Flex>

      <Box px={{ base: 3, md: 6 }} pb={3} flex="1" minH={0}>
        {viewerReady ? (
          <Box
            key={viewerSession}
            as="iframe"
            src={embeddedViewerUrl}
            title="OHIF Local DICOM Viewer"
            width="100%"
            height="100%"
            border="1px solid"
            borderColor="gray.700"
            borderRadius="md"
            bg="black"
            display="block"
          />
        ) : (
          <Flex h="100%" align="center" justify="center" bg="black">
            <Spinner color="teal.300" size="xl" />
          </Flex>
        )}
      </Box>
    </Box>
  );
}
