// pages/_app.tsx
import React, { useEffect, useRef, useState } from "react";
import { ChakraProvider, ColorModeScript, Box, Spinner, Text, VStack } from "@chakra-ui/react";
import theme from "../src/chakra/theme";
import type { AppProps } from "next/app";
import Router from "next/router";
import { loaderBus } from "../src/utils/loaderBus"; // must match where you saved it

/**
 * Global overlay that listens to both:
 *  - loaderBus (network requests)
 *  - Next.js route changes
 */
function GlobalLoader() {
  const [networkBusy, setNetworkBusy] = useState(false);
  const [routeBusy, setRouteBusy] = useState(false);

  // Avoid flicker on very fast requests/navigations
  const delayMs = 150;
  const routeTimer = useRef<number | null>(null);
  const netTimer = useRef<number | null>(null);

  // Subscribe to loaderBus counter
  useEffect(() => {
    const onChange = (count: number) => {
      if (count > 0) {
        if (netTimer.current) window.clearTimeout(netTimer.current);
        netTimer.current = window.setTimeout(() => setNetworkBusy(true), delayMs);
      } else {
        if (netTimer.current) window.clearTimeout(netTimer.current);
        setNetworkBusy(false);
      }
    };

    // Support whichever API your loaderBus exposes
    let unsubscribe: (() => void) | void;
    const anyBus = loaderBus as any;
    if (typeof anyBus.onChange === "function") {
      unsubscribe = anyBus.onChange(onChange);
    } else if (typeof anyBus.subscribe === "function") {
      unsubscribe = anyBus.subscribe(onChange);
    } else if (typeof anyBus.on === "function") {
      anyBus.on("change", onChange);
      unsubscribe = () => anyBus.off?.("change", onChange);
    } else {
      // Fallback: poll every 250ms if no event API (shouldn't happen)
      const id = window.setInterval(() => {
        const c = typeof anyBus.getCount === "function" ? anyBus.getCount() : 0;
        onChange(c);
      }, 250);
      unsubscribe = () => window.clearInterval(id);
    }

    return () => {
      if (typeof unsubscribe === "function") unsubscribe();
      if (netTimer.current) window.clearTimeout(netTimer.current);
    };
  }, []);

  // Hook router events
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
      zIndex={1400} // above modals/tooltips
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
}

export default function App({ Component, pageProps }: AppProps) {
  return (
    <ChakraProvider theme={theme}>
      {/* Ensures color mode is synced between SSR and client */}
      <ColorModeScript initialColorMode={theme.config.initialColorMode} />

      {/* App-wide loading overlay (Axios + Router) */}
      <GlobalLoader />

      <Component {...pageProps} />
    </ChakraProvider>
  );
}
