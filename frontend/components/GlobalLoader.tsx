// components/GlobalLoader.tsx
import React, { useEffect, useRef, useState } from "react";
import { Box, Spinner, Text, VStack } from "@chakra-ui/react";
import Router from "next/router";
import { loaderBus } from "../src/utils/loaderBus";

const GlobalLoader: React.FC = () => {
  const [networkBusy, setNetworkBusy] = useState(false);
  const [routeBusy, setRouteBusy] = useState(false);

  const delayMs = 150; // avoid flicker on very fast ops
  const netTimer = useRef<number | null>(null);
  const routeTimer = useRef<number | null>(null);

  // Listen to global network busy counter
  useEffect(() => {
    const unsubscribe = loaderBus.subscribe((count) => {
      if (count > 0) {
        if (netTimer.current) window.clearTimeout(netTimer.current);
        netTimer.current = window.setTimeout(() => setNetworkBusy(true), delayMs);
      } else {
        if (netTimer.current) window.clearTimeout(netTimer.current);
        setNetworkBusy(false);
      }
    });

    return () => {
      if (netTimer.current) window.clearTimeout(netTimer.current);
      unsubscribe();
    };
  }, []);

  // Listen to Next.js route changes
  useEffect(() => {
    const start = () => {
      if (routeTimer.current) window.clearTimeout(routeTimer.current);
      routeTimer.current = window.setTimeout(() => setRouteBusy(true), delayMs);
    };
    const stop = () => {
      if (routeTimer.current) window.clearTimeout(routeTimer.current);
      setRouteBusy(false);
    };

    Router.events.on("routeChangeStart", start);
    Router.events.on("routeChangeComplete", stop);
    Router.events.on("routeChangeError", stop);

    return () => {
      Router.events.off("routeChangeStart", start);
      Router.events.off("routeChangeComplete", stop);
      Router.events.off("routeChangeError", stop);
      if (routeTimer.current) window.clearTimeout(routeTimer.current);
    };
  }, []);

  const active = networkBusy || routeBusy;
  if (!active) return null;

  return (
    <Box
      position="fixed"
      inset={0}
      bg="blackAlpha.600"
      zIndex={1400}
      display="grid"
      placeItems="center"
    >
      <VStack spacing={3} bg="gray.800" px={6} py={5} rounded="xl" boxShadow="xl">
        <Spinner thickness="4px" speed="0.65s" emptyColor="gray.600" size="xl" />
        <Text fontWeight="medium" color="gray.100">
          Loading…
        </Text>
      </VStack>
    </Box>
  );
};

export default GlobalLoader;
