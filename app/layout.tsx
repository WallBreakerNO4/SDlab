import type { Metadata } from "next";
import { Geist, Geist_Mono, JetBrains_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";

import "./globals.css";

import { AuthProvider } from "@/components/auth-provider";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { UserPreferencesProvider } from "@/components/user-preferences-provider";
import { Toaster } from "@/components/ui/sonner";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import { getViewerShowNsfwPreference } from "@/lib/server-user-preferences";
import type { User } from "@supabase/supabase-js";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-sans",
});

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "SD Style Lab — AI 风格实验室",
  description:
    "AI 图像风格探索平台，使用 ComfyUI 生成 Stable Diffusion 风格对比网格。",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  let initialUser: User | null | undefined;
  let initialShowNsfw = false;
  try {
    const supabase = await createSupabaseAuthClient();
    const { data } = await supabase.auth.getUser();
    initialUser = data.user ?? null;
    if (initialUser) {
      initialShowNsfw = await getViewerShowNsfwPreference(supabase);
    }
  } catch {
    initialUser = undefined;
  }

  const authSnapshotKey =
    initialUser === undefined
      ? "unknown"
      : initialUser === null
        ? "anon"
        : `${initialUser.id}:${initialUser.updated_at ?? "snapshot"}`;

  return (
    <html
      lang="zh-CN"
      className={jetbrainsMono.variable}
      suppressHydrationWarning
    >
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <AuthProvider key={authSnapshotKey} initialUser={initialUser}>
            <UserPreferencesProvider initialShowNsfw={initialShowNsfw}>
              <div className="flex h-dvh flex-col overflow-hidden">
                <SiteHeader />
                <div className="min-h-0 flex-1">{children}</div>
                <SiteFooter />
              </div>
              <Toaster position="bottom-left" />
            </UserPreferencesProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
