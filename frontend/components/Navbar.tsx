import {
  Box,
  Flex,
  HStack,
  Link,
  Spacer,
  Text,
  Button,
  Spinner,
  IconButton,
  useDisclosure,
  Drawer,
  DrawerOverlay,
  DrawerContent,
  DrawerHeader,
  DrawerBody,
  VStack,
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  Tooltip,
} from "@chakra-ui/react";
import { HamburgerIcon, ChevronDownIcon } from "@chakra-ui/icons";
import NextLink from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";
import {
  getToken,
  clearToken,
  parseToken,
  getTokenExpiration,
  getUsername,
  refreshAccessToken,
} from "../src/utils/auth";

export default function Navbar() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [roles, setRoles] = useState<string[]>([]);
  const [username, setUsername] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<string>("");
  const mobile = useDisclosure();

  useEffect(() => {
    const token = getToken();
    if (!token) {
      clearToken();
      router.push("/login");
      setIsLoading(false);
      return;
    }

    const loadUser = async () => {
      try {
        const parsed = parseToken(token);
        const parsedRoles = parsed?.roles;
        setRoles(Array.isArray(parsedRoles) ? parsedRoles : []);

        const user = getUsername();
        setUsername(user);
        setIsAuthenticated(true);

        const interval = setInterval(async () => {
          const exp = await getTokenExpiration();
          if (!exp) return;

          const secondsLeft = exp - Math.floor(Date.now() / 1000);

          if (secondsLeft <= 0) {
            setCountdown("Expired");
            clearToken();
            router.push("/login");
            clearInterval(interval);
          } else {
            if (secondsLeft < 120) {
              const refreshed = await refreshAccessToken();
              if (refreshed) {
                // token rotated; next tick will read the new exp
                return;
              } else {
                clearToken();
                router.push("/login");
                clearInterval(interval);
              }
            }
            const min = Math.floor(secondsLeft / 60);
            const sec = secondsLeft % 60;
            setCountdown(`${min}:${sec.toString().padStart(2, "0")}`);
          }
        }, 1000);

        return () => clearInterval(interval);
      } catch (err) {
        console.error("Invalid token:", err);
        clearToken();
        router.push("/login");
      } finally {
        setIsLoading(false);
      }
    };

    loadUser();
  }, [router]);

  const handleLogout = () => {
    clearToken();
    router.push("/login");
  };

  if (isLoading) {
    return (
      <Flex justify="center" align="center" h="100px">
        <Spinner size="md" color="teal.300" />
      </Flex>
    );
  }

  if (!isAuthenticated) return null;

  // Desktop link item
  const NavLink = ({
    href,
    label,
    hint,
  }: {
    href: string;
    label: string;
    hint?: string;
  }) => (
    <Tooltip label={hint} hasArrow openDelay={400}>
      <Link
        as={NextLink}
        href={href}
        color="white"
        _hover={{ color: "teal.300", textDecoration: "none" }}
        whiteSpace="nowrap"
      >
        {label}
      </Link>
    </Tooltip>
  );

  return (
    <Box
      bg="gray.900"
      px={{ base: 4, md: 6 }}
      py={3}
      mb={6}
      shadow="md"
      borderBottom="1px"
      borderColor="gray.700"
      position="sticky"
      top={0}
      zIndex={10}
    >
      <Flex align="center" w="100%" minW={0} gap={{ base: 3, xl: 4 }}>
        {/* Brand */}
        <Link as={NextLink} href="/" _hover={{ textDecoration: "none" }} flexShrink={0}>
          <HStack spacing={1} whiteSpace="nowrap">
            <Text fontSize="xl" fontWeight="black" color="teal.300">
              DICOM Toolkit
            </Text>
            <Text fontSize="xl" fontWeight="black" color="teal.400">
              UI
            </Text>
          </HStack>
        </Link>

        {/* Desktop nav (no wrap) */}
        <HStack
          spacing={{ xl: 4, "2xl": 6 }}
          ml={{ xl: 4, "2xl": 6 }}
          display={{ base: "none", xl: "flex" }}
          whiteSpace="nowrap"
          minW={0}
        >
          <NavLink href="/" label="Home" />
          <Menu placement="bottom-start" isLazy>
            <MenuButton
              as={Button}
              rightIcon={<ChevronDownIcon />}
              size="sm"
              variant="ghost"
              color="white"
              _hover={{ bg: "gray.800", color: "teal.300" }}
              _active={{ bg: "gray.800" }}
            >
              DICOM Converter
            </MenuButton>

            {/* make the dropdown dark */}
            <MenuList
              bg="gray.900"
              color="white"
              borderColor="gray.700"
              boxShadow="lg"
              p={1}
            >
              <MenuItem
                as={NextLink}
                href="/convert-DICOM-to-NON-DICOM"
                bg="transparent"
                _hover={{ bg: "gray.700" }}
                _focus={{ bg: "gray.700" }}
                _active={{ bg: "gray.700" }}
                borderRadius="md"
              >
                DICOM → NON-DICOM
              </MenuItem>

              <MenuItem
                as={NextLink}
                href="/convert-DICOM-to-NON-DICOM-batch"
                bg="transparent"
                _hover={{ bg: "gray.700" }}
                _focus={{ bg: "gray.700" }}
                _active={{ bg: "gray.700" }}
                borderRadius="md"
              >
                Batch (DICOM → NON-DICOM)
              </MenuItem>

              <MenuItem
                as={NextLink}
                href="/convert-NON-DICOM-to-dicom"
                bg="transparent"
                _hover={{ bg: "gray.700" }}
                _focus={{ bg: "gray.700" }}
                _active={{ bg: "gray.700" }}
                borderRadius="md"
              >
                NON-DICOM → DICOM
              </MenuItem>
            </MenuList>
          </Menu>

          <NavLink href="/AdminDashboard" label="Dashboard" />
          <NavLink href="/jobs" label="Jobs" />
          <NavLink href="/studies" label="Studies" />
          <NavLink
            href="/local-dicom-viewer"
            label="Local DICOM Viewer"
            hint="Open .dcm files or folders directly in OHIF"
          />
          <NavLink
            href="/anonymize-dicom"
            label="DICOM Anonymizer"
            hint="Anonymize DICOM using custom rules"
          />

          {/* NEW: Desktop link for MIME Ingest */}
          <NavLink
            href="/mime-ingest"
            label="MIME Ingest"
            hint="Upload .mime bundles and extract DICOM"
          />
        </HStack>

        <Spacer minW={0} />

        {/* Right side: user + logout */}
        <HStack spacing={{ base: 2, "2xl": 4 }} align="center" flexShrink={0}>
          <HStack spacing={3} display={{ base: "none", lg: "flex" }} whiteSpace="nowrap">
            <Text color="gray.300" fontSize="sm">👤 {username || "User"}</Text>
            <Text color="yellow.300" fontSize="sm" display={{ base: "none", "2xl": "block" }}>
              ⏳ {countdown}
            </Text>
          </HStack>

          <Button size="sm" colorScheme="red" onClick={handleLogout}>
            Logout
          </Button>

          {/* Mobile menu button */}
          <IconButton
            aria-label="Open menu"
            icon={<HamburgerIcon />}
            display={{ base: "inline-flex", xl: "none" }}
            variant="ghost"
            color="white"
            onClick={mobile.onOpen}
          />
        </HStack>
      </Flex>

      {/* Mobile drawer */}
      <Drawer isOpen={mobile.isOpen} placement="left" onClose={mobile.onClose}>
        <DrawerOverlay />
        <DrawerContent bg="gray.900" color="white">
          <DrawerHeader borderBottomWidth="1px">Menu</DrawerHeader>
          <DrawerBody>
            <VStack align="stretch" spacing={4}>
              <Link as={NextLink} href="/" onClick={mobile.onClose}>
                Home
              </Link>
              <Text fontSize="sm" color="gray.400" mt={2}>
                DICOM-Converter
              </Text>
              <VStack align="stretch" pl={2}>
                <Link as={NextLink} href="/convert-DICOM-to-NON-DICOM" onClick={mobile.onClose}>
                  DICOM → NON-DICOM
                </Link>
                <Link as={NextLink} href="/convert-DICOM-to-NON-DICOM-batch" onClick={mobile.onClose}>
                  Batch (DICOM → NON-DICOM)
                </Link>
                <Link as={NextLink} href="/convert-NON-DICOM-to-dicom" onClick={mobile.onClose}>
                  NON-DICOM → DICOM
                </Link>
              </VStack>
              <Link as={NextLink} href="/AdminDashboard" onClick={mobile.onClose}>
                Dashboard
              </Link>
              <Link as={NextLink} href="/jobs" onClick={mobile.onClose}>
                Jobs
              </Link>
              <Link as={NextLink} href="/studies" onClick={mobile.onClose}>
                Studies
              </Link>
              <Link as={NextLink} href="/local-dicom-viewer" onClick={mobile.onClose}>
                Local DICOM Viewer
              </Link>
              <Link as={NextLink} href="/anonymize-dicom" onClick={mobile.onClose}>
                DICOM Anonymizer
              </Link>
              {/* You already had this in the drawer; keeping it */}
              <Link as={NextLink} href="/mime-ingest" onClick={mobile.onClose}>
                MIME
              </Link>
              <Button onClick={handleLogout} colorScheme="red" size="sm" mt={2}>
                Logout
              </Button>
              <Box pt={4} color="gray.400" fontSize="sm">
                👤 {username || "User"} · ⏳ {countdown}
              </Box>
            </VStack>
          </DrawerBody>
        </DrawerContent>
      </Drawer>
    </Box>
  );
}
