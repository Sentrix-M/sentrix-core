# @sentrix/config

Shared configuration and environment validation for the Sentrix platform.

## Contents

- `envSchema` — Zod schema for required environment variables
- `EnvConfig` — Type-safe environment configuration interface
- `loadEnvConfig` — Parse and validate `process.env` (throws on invalid)

## Usage

```ts
import { loadEnvConfig } from "@sentrix/config";

const config = loadEnvConfig({
  NODE_ENV: "development",
  API_BASE_URL: "http://localhost:8000",
});
```

