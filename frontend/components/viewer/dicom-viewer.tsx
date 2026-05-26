import { useEffect, useRef } from "react";
import { Box } from "@chakra-ui/react";

type Props = {
  url: string;
};

export default function DicomViewer({ url }: Props) {
  const elementRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cornerstone: any;
    let imageId: string;

    const loadDicom = async () => {
      const cs = await import("cornerstone-core");
      const wadoLoader = await import("cornerstone-wado-image-loader");

      cornerstone = cs.default || cs;
      wadoLoader.external.cornerstone = cornerstone;

      wadoLoader.configure({
        beforeSend: function (xhr: XMLHttpRequest) {
          // Add any authentication headers here if needed
        },
      });

      imageId = `wadouri:${url}`;
      cornerstone.enable(elementRef.current!);

      try {
        const image = await cornerstone.loadImage(imageId);
        cornerstone.displayImage(elementRef.current!, image);
      } catch (err) {
        console.error("Failed to load DICOM image", err);
      }
    };

    loadDicom();

    return () => {
      if (cornerstone && elementRef.current) {
        cornerstone.disable(elementRef.current);
      }
    };
  }, [url]);

  return (
    <Box
      ref={elementRef}
      width="512px"
      height="512px"
      backgroundColor="black"
      border="1px"
      borderColor="gray.600"
      borderRadius="md"
    />
  );
}
