"use client";

import { createClient } from "@/lib/supabase/client";
import type { Provider } from "@supabase/supabase-js";

export default function LoginPage() {
	const handleLogin = async (provider: Provider) => {
		const supabase = createClient();
		await supabase.auth.signInWithOAuth({
			provider,
			options: {
				redirectTo: `${window.location.origin}/auth/callback`,
			},
		});
	};

	return (
		<div className="flex min-h-screen items-center justify-center bg-background p-4">
			<div className="w-full max-w-sm space-y-6 rounded-lg border bg-card p-8 shadow-sm">
				<div className="space-y-2 text-center">
					<h1 className="text-2xl font-semibold tracking-tight">登录</h1>
					<p className="text-sm text-muted-foreground">
						选择以下方式登录以继续
					</p>
				</div>
				<div className="space-y-3">
					<button
						type="button"
						onClick={() => handleLogin("google")}
						className="flex w-full items-center justify-center gap-2 rounded-md border bg-background px-4 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
					>
						Google
					</button>
					<button
						type="button"
						onClick={() => handleLogin("azure")}
						className="flex w-full items-center justify-center gap-2 rounded-md border bg-background px-4 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
					>
						Microsoft
					</button>
					<button
						type="button"
						onClick={() => handleLogin("github")}
						className="flex w-full items-center justify-center gap-2 rounded-md border bg-background px-4 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
					>
						GitHub
					</button>
					<button
						type="button"
						onClick={() => handleLogin("apple")}
						className="flex w-full items-center justify-center gap-2 rounded-md border bg-background px-4 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
					>
						Apple
					</button>
				</div>
			</div>
		</div>
	);
}
