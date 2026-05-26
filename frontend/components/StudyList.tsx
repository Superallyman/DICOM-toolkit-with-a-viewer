// components/StudyList.tsx

import React, { useEffect, useState } from 'react';
import {
  Box,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Spinner,
  Button,
  Text,
  Center,
} from '@chakra-ui/react';
import axios from 'axios';
import { API_URL, buildStudyViewerUrl } from '../src/utils/env';

interface Study {
  StudyInstanceUID: string;
  PatientID: string;
  PatientName: string;
  StudyDate: string;
  StudyDescription: string;
  AccessionNumber: string;
  ModalitiesInStudy: string[];
}

const StudyList: React.FC = () => {
  const [studies, setStudies] = useState<Study[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStudies = async () => {
      try {
        const response = await axios.get(`${API_URL}/studies`);
        setStudies(response.data as Study[]); // ✅ Fix: Type cast to Study[]
      } catch (err) {
        console.error(err);
        setError('Failed to fetch studies');
      } finally {
        setLoading(false);
      }
    };

    fetchStudies();
  }, []);

  const handleLaunchViewer = (studyUID: string) => {
    window.open(buildStudyViewerUrl(studyUID), "_blank", "noopener,noreferrer");
  };

  if (loading) {
    return (
      <Center py={20}>
        <Spinner size="xl" />
      </Center>
    );
  }

  if (error) {
    return (
      <Center py={20}>
        <Text color="red.500">{error}</Text>
      </Center>
    );
  }

  return (
    <Box overflowX="auto" py={8} px={4}>
      <Text fontSize="2xl" fontWeight="bold" mb={4}>
        Available Studies
      </Text>
      <Table variant="striped" size="md">
        <Thead>
          <Tr>
            <Th>Patient Name</Th>
            <Th>Patient ID</Th>
            <Th>Study Date</Th>
            <Th>Study Description</Th>
            <Th>Modality</Th>
            <Th>Accession #</Th>
            <Th>Action</Th>
          </Tr>
        </Thead>
        <Tbody>
          {studies.map((study) => (
            <Tr key={study.StudyInstanceUID}>
              <Td>{study.PatientName}</Td>
              <Td>{study.PatientID}</Td>
              <Td>{study.StudyDate}</Td>
              <Td>{study.StudyDescription}</Td>
              <Td>{study.ModalitiesInStudy?.join(', ') || 'OT'}</Td>
              <Td>{study.AccessionNumber}</Td>
              <Td>
                <Button
                  colorScheme="blue"
                  size="sm"
                  onClick={() => handleLaunchViewer(study.StudyInstanceUID)}
                >
                  View in OHIF
                </Button>
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </Box>
  );
};

export default StudyList;
