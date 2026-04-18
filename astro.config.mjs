import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";

export default defineConfig({
  site: "https://statisticalintuitions.com",
  output: "static",
  integrations: [tailwind()],
});
