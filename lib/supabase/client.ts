import { createBrowserClient as createSupabaseBrowserClient } from "@supabase/ssr";

function getRequiredEnv(
	name: "NEXT_PUBLIC_SUPABASE_URL" | "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
) {
	const value = process.env[name];
	if (!value) {
		throw new Error(`Missing env: ${name}`);
	}
	return value;
}

export function createClient() {
	const url = getRequiredEnv("NEXT_PUBLIC_SUPABASE_URL");
	const publishableKey = getRequiredEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY");
	return createSupabaseBrowserClient(url, publishableKey);
}
