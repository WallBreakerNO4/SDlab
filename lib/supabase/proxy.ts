import { getCloudflareContext } from "@opennextjs/cloudflare";
import type { SetAllCookies } from "@supabase/ssr";
import { createServerClient as createSupabaseServerClient } from "@supabase/ssr";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export async function updateSession(request: NextRequest) {
	async function getRequiredEnv(
		name: "NEXT_PUBLIC_SUPABASE_URL" | "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
	) {
		const fromProcessEnv = process.env[name];
		if (fromProcessEnv) return fromProcessEnv;

		try {
			const { env } = await getCloudflareContext({ async: true });
			const fromCloudflareEnv = (
				(env as unknown as Record<string, unknown> | undefined)?.[name]
			);
			if (typeof fromCloudflareEnv === "string" && fromCloudflareEnv) {
				return fromCloudflareEnv;
			}
		} catch {}

		throw new Error(`Missing env: ${name}`);
	}

	let response = NextResponse.next({ request });

	const url = await getRequiredEnv("NEXT_PUBLIC_SUPABASE_URL");
	const publishableKey = await getRequiredEnv(
		"NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
	);

	try {
		const supabase = createSupabaseServerClient(url, publishableKey, {
			cookies: {
				getAll() {
					return request.cookies.getAll();
				},
				setAll(cookiesToSet: Parameters<SetAllCookies>[0]) {
					try {
						cookiesToSet.forEach(({ name, value }) => {
							request.cookies.set(name, value);
						});

						response = NextResponse.next({ request });

						cookiesToSet.forEach(({ name, value, options }) => {
							response.cookies.set(name, value, options);
						});
					} catch {}
				},
			},
		});

		await supabase.auth.getClaims();
	} catch {}
	return response;
}
