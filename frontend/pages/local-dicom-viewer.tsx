import { RepeatIcon, ExternalLinkIcon } from "@chakra-ui/icons";
import { Box, Button, Flex, Heading, HStack, IconButton, Tooltip } from "@chakra-ui/react";
import { useState } from "react";
import Navbar from "../components/Navbar";
import { buildLocalViewerUrl } from "../src/utils/env";

export default function LocalDicomViewerPage() {
  const [viewerSession, setViewerSession] = useState(0);
  const localViewerUrl = buildLocalViewerUrl();
  const embeddedViewerUrl = `${localViewerUrl}?session=${viewerSession}`;

  return (
    <Box bg="gray.900" minH="100vh">
      <Navbar />

      <Flex
        px={{ base: 3, md: 6 }}
        pb={6}
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
              onClick={() => setViewerSession((session) => session + 1)}
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

      <Box px={{ base: 3, md: 6 }} pb={6}>
        <Box
          key={viewerSession}
          as="iframe"
          src={embeddedViewerUrl}
          title="OHIF Local DICOM Viewer"
          width="100%"
          height="calc(100vh - 180px)"
          minH="620px"
          border="1px solid"
          borderColor="gray.700"
          borderRadius="md"
          bg="black"
        />
      </Box>
    </Box>
  );
}
