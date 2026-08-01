import type { NextConfig } from "next";

const allowedDevOrigins = (process.env.ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  // Allow LAN/container dev access (e.g. 192.168.56.1) without blocking
  // HMR/font dev resources. Configure via ALLOWED_DEV_ORIGINS="host1,host2".
  ...(allowedDevOrigins.length > 0 ? { allowedDevOrigins } : {}),
};

export default nextConfig;
