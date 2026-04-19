type PublicEnv = {
  supabaseUrl: string;
  supabasePublishableKey: string;
  r2PublicBaseUrl: string;
};

function readRequiredValue(
  value: string | undefined,
  ...keys: string[]
): string {
  const trimmed = value?.trim();
  if (trimmed) {
    return trimmed;
  }

  throw new Error(`Missing required environment variable: ${keys.join(" or ")}`);
}

function readSupabaseUrl(): string {
  return readRequiredValue(
    process.env.NEXT_PUBLIC_SUPABASE_URL,
    "NEXT_PUBLIC_SUPABASE_URL",
  );
}

function readSupabasePublishableKey(): string {
  return readRequiredValue(
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
  );
}

function readR2PublicBaseUrl(): string {
  const publicValue = process.env.NEXT_PUBLIC_R2_PUBLIC_BASE_URL?.trim();
  if (publicValue) {
    return publicValue;
  }

  if (typeof window === "undefined") {
    const serverValue = process.env.R2_PUBLIC_BASE_URL?.trim();
    if (serverValue) {
      return serverValue;
    }
  }

  throw new Error(
    "Missing required environment variable: NEXT_PUBLIC_R2_PUBLIC_BASE_URL or R2_PUBLIC_BASE_URL",
  );
}

let cachedPublicEnv: PublicEnv | null = null;

export function getPublicEnv(): PublicEnv {
  if (cachedPublicEnv) {
    return cachedPublicEnv;
  }

  cachedPublicEnv = {
    supabaseUrl: readSupabaseUrl(),
    supabasePublishableKey: readSupabasePublishableKey(),
    r2PublicBaseUrl: readR2PublicBaseUrl(),
  };

  return cachedPublicEnv;
}
