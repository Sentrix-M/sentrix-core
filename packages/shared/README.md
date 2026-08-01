# @sentrix/shared

Shared utilities, constants, and helper functions for the Sentrix platform.

## Contents

- `cn` — Tailwind class-name merger
- `sleep` — Promise-based delay helper
- `isDev` — Development-environment detection
- `APP_NAME` / `APP_VERSION` — Platform constants

## Usage

```ts
import { cn, sleep } from "@sentrix/shared";

const className = cn("px-4", isDev ? "bg-red-500" : "bg-blue-500");
await sleep(100);
```

