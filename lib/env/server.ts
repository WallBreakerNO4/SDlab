import "server-only";

import { getPublicEnv } from "@/lib/env/public";

type ServerEnv = ReturnType<typeof getPublicEnv> & {
  runMediaGrantSecret: string;
};

function readRequiredServerEnv(key: string): string {
  const value = process.env[key]?.trim();
  if (value) {
    return value;
  }

  throw new Error(`Missing required environment variable: ${key}`);
}

let cachedServerEnv: ServerEnv | null = null;

export function getServerEnv(): ServerEnv {
  if (cachedServerEnv) {
    return cachedServerEnv;
  }

  cachedServerEnv = {
    ...getPublicEnv(),
    runMediaGrantSecret: readRequiredServerEnv("RUN_MEDIA_GRANT_SECRET"),
  };

  return cachedServerEnv;
}
