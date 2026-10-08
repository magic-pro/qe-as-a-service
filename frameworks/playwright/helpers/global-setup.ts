import { FullConfig } from "@playwright/test";

async function globalSetup(_config: FullConfig) {
  const baseURL = process.env.BASE_URL ?? "http://localhost:3000";
  const token = process.env.TEST_AUTH_TOKEN;

  if (!token) {
    console.warn("[global-setup] TEST_AUTH_TOKEN not set — using placeholder. Set it before running against real environments.");
  }

  const res = await fetch(`${baseURL}/health`).catch(() => null);
  if (!res || !res.ok) {
    console.warn(`[global-setup] Health check failed for ${baseURL} — tests may fail if the target is not running.`);
  } else {
    console.log(`[global-setup] Target healthy: ${baseURL}`);
  }
}

export default globalSetup;
