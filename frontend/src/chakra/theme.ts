// Optional: Customize Chakra theme here
import { extendTheme } from "@chakra-ui/react";
const theme = extendTheme({});
// theme.ts
export default extendTheme({
  config: {
    initialColorMode: "dark", // Or "light"
    useSystemColorMode: false,
  },
});
