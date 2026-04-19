type PublicEnv = {
  supabaseUrl: string;
  supabasePublishableKey: string;
  r2PublicBaseUrl: string;
};

function readRequiredEnv(...keys: string[]): string {
  for (const key of keys) {
    const value = process.env[key]?.trim();
    if (value) {
      return value;
    }
  }

  throw new Error(`Missing required environment variable: ${keys.join(" or ")}`);
}

let cachedPublicEnv: PublicEnv | null = null;

export function getPublicEnv(): PublicEnv {
  if (cachedPublicEnv) {
    return cachedPublicEnv;
  }

  cachedPublicEnv = {
    supabaseUrl: readRequiredEnv("NEXT_PUBLIC_SUPABASE_URL"),
    supabasePublishableKey: readRequiredEnv(
      "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    ),
    r2PublicBaseUrl: readRequiredEnv(
      "NEXT_PUBLIC_R2_PUBLIC_BASE_URL",
      "R2_PUBLIC_BASE_URL",
    ),
  };

  return cachedPublicEnv;
}
