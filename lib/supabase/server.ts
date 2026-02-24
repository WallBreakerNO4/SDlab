import type { SetAllCookies } from "@supabase/ssr";
import { createServerClient as createSupabaseServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createClient() {
	function getRequiredEnv(
		name: "NEXT_PUBLIC_SUPABASE_URL" | "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
	) {
		const value = process.env[name];
		if (!value) {
			throw new Error(`Missing env: ${name}`);
		}
		return value;
	}

	const cookieStore = await cookies();
	const url = getRequiredEnv("NEXT_PUBLIC_SUPABASE_URL");
	const publishableKey = getRequiredEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY");

	return createSupabaseServerClient(url, publishableKey, {
		cookies: {
			getAll() {
				return cookieStore.getAll();
			},
			setAll(cookiesToSet: Parameters<SetAllCookies>[0]) {
				try {
					cookiesToSet.forEach(({ name, value, options }) => {
						cookieStore.set(name, value, options);
					});
				} catch {}
			},
		},
	});
}
