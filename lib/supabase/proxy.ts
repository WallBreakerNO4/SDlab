import type { SetAllCookies } from "@supabase/ssr";
import { createServerClient as createSupabaseServerClient } from "@supabase/ssr";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export async function updateSession(request: NextRequest) {
	let response = NextResponse.next({ request });

	const url = getRequiredEnv("NEXT_PUBLIC_SUPABASE_URL");
	const publishableKey = getRequiredEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY");

	const supabase = createSupabaseServerClient(url, publishableKey, {
		cookies: {
			getAll() {
				return request.cookies.getAll();
			},
			setAll(cookiesToSet: Parameters<SetAllCookies>[0]) {
				cookiesToSet.forEach(({ name, value }) => {
					request.cookies.set(name, value);
				});

				response = NextResponse.next({ request });

				cookiesToSet.forEach(({ name, value, options }) => {
					response.cookies.set(name, value, options);
				});
			},
		},
	});

	await supabase.auth.getClaims();
	return response;
}

function getRequiredEnv(
	name: "NEXT_PUBLIC_SUPABASE_URL" | "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
) {
	const value = process.env[name];
	if (!value) {
		throw new Error(`Missing env: ${name}`);
	}
	return value;
}
