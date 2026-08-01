# @sentrix/types

Shared TypeScript types and API interfaces for the Sentrix platform.

## Contents

- `HealthStatus` — API health-check contract
- `Paginated<T>` — Generic pagination wrapper
- `ApiResponse<T>` — Generic API envelope
- `AiResult` — AI pipeline result shape

## Usage

```ts
import type { HealthStatus, Paginated } from "@sentrix/types";

const health: HealthStatus = { status: "ok", service: "Sentrix API", version: "0.1.0" };
const page: Paginated<number> = { items: [1, 2, 3], total: 3, page: 1, pageSize: 10 };
```

