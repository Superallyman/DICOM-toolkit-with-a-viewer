import React from 'react';
import { Box, Button, Image, Text, VStack } from '@chakra-ui/react';
import { buildStudyViewerUrl } from '../src/utils/env';

interface Thumbnail {
  sopInstanceUID: string;
  thumbnailUrl: string;
  viewerUrl: string;
  studyInstanceUID?: string;
}

interface ThumbnailsGridProps {
  thumbnails: Thumbnail[];
}

const ThumbnailsGrid: React.FC<ThumbnailsGridProps> = ({ thumbnails }) => {
  if (!thumbnails.length) return <Text>No thumbnails found.</Text>;

  const handleViewerLaunch = (studyUID?: string) => {
    if (!studyUID) return;
    window.open(buildStudyViewerUrl(studyUID), '_blank', 'noopener,noreferrer');
  };

  return (
    <Box display="flex" flexWrap="wrap" gap="20px">
      {thumbnails.map((thumb) => (
        <VStack
          key={thumb.sopInstanceUID}
          spacing={2}
          border="1px solid #ccc"
          borderRadius="md"
          padding={3}
          boxShadow="sm"
        >
          <a href={thumb.viewerUrl} target="_blank" rel="noopener noreferrer">
            <Image
              src={thumb.thumbnailUrl}
              alt={`Thumbnail ${thumb.sopInstanceUID}`}
              boxSize="150px"
              objectFit="cover"
              borderRadius="md"
            />
          </a>
          <Text fontSize="xs" noOfLines={1}>
            {thumb.sopInstanceUID}
          </Text>
          <Button
            size="xs"
            colorScheme="blue"
            onClick={() => handleViewerLaunch(thumb.studyInstanceUID)}
          >
            Launch Viewer
          </Button>
        </VStack>
      ))}
    </Box>
  );
};

export default ThumbnailsGrid;
