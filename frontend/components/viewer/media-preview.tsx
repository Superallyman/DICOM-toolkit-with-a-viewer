import { Box, Image, Text } from "@chakra-ui/react";

interface MediaPreviewProps {
  url: string;
  type: string;
}

export default function MediaPreview({ url, type }: MediaPreviewProps) {
  if (type.startsWith("image/")) {
    return (
      <Box borderRadius="md" overflow="hidden" boxShadow="md" maxW="full">
        <Image src={url} alt="Converted Image" maxH="400px" mx="auto" />
      </Box>
    );
  }

  if (type === "video/mp4") {
    return (
      <Box maxW="full">
        <video controls style={{ maxHeight: "400px", width: "100%" }}>
          <source src={url} type="video/mp4" />
          Your browser does not support the video tag.
        </video>
      </Box>
    );
  }

  if (type === "application/pdf") {
    return (
      <Box as="iframe" src={url} width="100%" height="500px" borderRadius="md" border="1px solid" borderColor="gray.700" />
    );
  }

  return (
    <Text color="gray.400">No preview available for this format.</Text>
  );
}
