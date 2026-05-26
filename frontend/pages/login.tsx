import { useState } from "react";
import {
  Box, Button, Input, FormControl, FormLabel, VStack, Text, Alert, AlertIcon,
} from "@chakra-ui/react";
import { useRouter } from "next/router";
import { setToken } from "../src/utils/auth";
import { decodeToken } from "../src/utils/jwt";
import { API_URL } from "../src/utils/env";




export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleLogin = async () => {
    try {
      const formData = new FormData();
      formData.append("username", username);
      formData.append("password", password);

      const res = await fetch(`${API_URL}/authenticator`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        setError("Invalid credentials");
        return;
      }

      const data = await res.json();

      if (!data.access_token || !data.refresh_token) {
        setError("Missing tokens from server");
        return;
      }

      // Store both tokens
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);

      // Optionally: decode & store username or roles if included
      setToken(data.access_token); // use if you have a central auth utility

  const decoded = decodeToken(data.access_token); // ✅ no await

    if (decoded) {
      localStorage.setItem("username", decoded.sub);
    }


      router.push("/");
    } catch (err) {
      setError("Failed to login. Try again.");
    }
  };

  return (
    <Box p={8} maxW="md" mx="auto" bg="gray.900" color="white" rounded="md" shadow="md" mt={12}>
      <Text fontSize="2xl" fontWeight="bold" mb={4}>Login</Text>
      <VStack spacing={4}>
        <FormControl>
          <FormLabel>Username</FormLabel>
          <Input
            bg="gray.800"
            borderColor="gray.700"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </FormControl>
        <FormControl>
          <FormLabel>Password</FormLabel>
          <Input
            bg="gray.800"
            borderColor="gray.700"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </FormControl>
        <Button colorScheme="teal" onClick={handleLogin} width="full">
          Login
        </Button>
        {error && (
          <Alert status="error" rounded="md">
            <AlertIcon />
            {error}
          </Alert>
        )}
      </VStack>
    </Box>
  );
}
