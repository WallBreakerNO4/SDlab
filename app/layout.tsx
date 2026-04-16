import type { Metadata } from "next";
import { Geist, Geist_Mono, JetBrains_Mono } from "next/font/google";
import { cookies } from "next/headers";
import Script from "next/script";
import { ThemeProvider } from "next-themes";

import "./globals.css";

import { AuthProvider } from "@/components/auth-provider";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { UserPreferencesProvider } from "@/components/user-preferences-provider";
import { Toaster } from "@/components/ui/sonner";
import {
  THEME_COOKIE_NAME,
  THEME_STORAGE_KEY,
  getThemeBootstrapScript,
  getThemeCriticalCss,
  getThemeInlineStyle,
  parseThemePreference,
} from "@/lib/theme";
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
  icons: {
    icon: [
      { url: "/favicon/favicon-96x96.png", sizes: "96x96", type: "image/png" },
      { url: "/favicon/favicon.svg", type: "image/svg+xml" },
    ],
    shortcut: "/favicon/favicon.ico",
    apple: "/favicon/apple-touch-icon.png",
  },
  manifest: "/favicon/site.webmanifest",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const initialTheme = parseThemePreference(
    cookieStore.get(THEME_COOKIE_NAME)?.value,
  );
  const initialThemeStyle = initialTheme
    ? getThemeInlineStyle(initialTheme)
    : undefined;
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
      className={
        initialTheme
          ? `${jetbrainsMono.variable} ${initialTheme}`
          : jetbrainsMono.variable
      }
      style={initialThemeStyle}
      suppressHydrationWarning
    >
      <head>
        <style id="theme-critical">{getThemeCriticalCss()}</style>
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <Script id="theme-bootstrap" strategy="beforeInteractive">
          {getThemeBootstrapScript()}
        </Script>
        <ThemeProvider
          attribute="class"
          defaultTheme={initialTheme ?? "system"}
          enableSystem
          enableColorScheme
          disableTransitionOnChange
          storageKey={THEME_STORAGE_KEY}
          scriptProps={{ "data-cfasync": "false" }}
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
