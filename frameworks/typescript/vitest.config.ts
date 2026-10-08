import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["tests/**/*.{test,spec}.ts"],
    exclude: ["tests/**/*.integration.{test,spec}.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      exclude: ["tests/**", "**/*.d.ts"],
    },
    projects: [
      {
        name: "unit",
        include: ["tests/**/*.spec.ts"],
        exclude: ["tests/**/*.integration.spec.ts"],
      },
      {
        name: "integration",
        include: ["tests/**/*.integration.spec.ts"],
      },
    ],
  },
});
