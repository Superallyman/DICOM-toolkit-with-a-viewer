import { Box, Heading, Text, VStack } from "@chakra-ui/react";
import Navbar from "../components/Navbar";

export default function Home() {
  return (
    <Box minH="100vh" bg="gray.900" color="white">
      <Navbar />

      <VStack spacing={4} justify="center" align="center" h="calc(100vh - 80px)">
        <Heading size="2xl" textAlign="center">
          Welcome to the DICOM Toolkit App
        </Heading>
        <Text fontSize="lg" color="gray.300">
          The App is ready.
        </Text>
      </VStack>
    </Box>
  );
}
