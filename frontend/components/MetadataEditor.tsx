import { Box, Input, FormLabel, VStack } from "@chakra-ui/react";
import { useState } from "react";

interface MetadataEditorProps {
  metadata: {
    PatientName?: string;
    AccessionNumber?: string;
    StudyDate?: string;
    StudyDescription?: string;
  };
  onChange?: (updated: any) => void;
}

export default function MetadataEditor({ metadata, onChange }: MetadataEditorProps) {
  const [localMeta, setLocalMeta] = useState(metadata);

  const handleChange = (field: keyof typeof localMeta, value: string) => {
    const updated = { ...localMeta, [field]: value };
    setLocalMeta(updated);
    if (onChange) onChange(updated);
  };

  return (
    <Box p={2} borderWidth="1px" borderRadius="md" mt={2}>
      <VStack spacing={2} align="stretch">
        <Box>
          <FormLabel>Patient Name</FormLabel>
          <Input
            value={localMeta.PatientName || ""}
            onChange={(e) => handleChange("PatientName", e.target.value)}
          />
        </Box>
        <Box>
          <FormLabel>Accession Number</FormLabel>
          <Input
            value={localMeta.AccessionNumber || ""}
            onChange={(e) => handleChange("AccessionNumber", e.target.value)}
          />
        </Box>
        <Box>
          <FormLabel>Study Date</FormLabel>
          <Input
            type="date"
            value={localMeta.StudyDate || ""}
            onChange={(e) => handleChange("StudyDate", e.target.value)}
          />
        </Box>
        <Box>
          <FormLabel>Study Description</FormLabel>
          <Input
            value={localMeta.StudyDescription || ""}
            onChange={(e) => handleChange("StudyDescription", e.target.value)}
          />
        </Box>
      </VStack>
    </Box>
  );
}
