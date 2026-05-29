import type { Metadata } from "next";
import { Geist, Geist_Mono, JetBrains_Mono } from "next/font/google";
import { cookies } from "next/headers";
import Script from "next/script";
import { ThemeProvider } from "next-themes";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { hasLocale } from "next-intl";

import "../globals.css";

import { AuthProvider } from "@/components/auth-provider";
import { JsonLdWebsite } from "@/components/json-ld";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { UserPreferencesProvider } from "@/components/user-preferences-provider";
import { Toaster } from "@/components/ui/sonner";
import { WebVitals } from "@/components/web-vitals";
import { createSupabaseAuthClient } from "@/lib/supabase-auth";
import {
  THEME_COOKIE_NAME,
  THEME_STORAGE_KEY,
  getThemeBootstrapScript,
  getThemeCriticalCss,
  getThemeInlineStyle,
  parseThemePreference,
} from "@/lib/theme";
import {
  DEFAULT_SHOW_NSFW,
  parseViewerShowNsfwCookieValue,
  VIEWER_SHOW_NSFW_COOKIE,
} from "@/lib/viewer-nsfw-cookie";
import { routing } from "@/i18n/routing";
import { SITE_ORIGIN } from "@/lib/site-origin";

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

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: Readonly<{
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}>) {
  const { locale } = await params;

  if (!hasLocale(routing.locales, locale)) {
    notFound();
  }

  setRequestLocale(locale);
  const messages = await getMessages();
  const tMetaHome = await getTranslations({ locale, namespace: "metadata.home" });
  const siteDescription = tMetaHome("description");

  const cookieStore = await cookies();

  let initialUser = null;
  try {
    const supabase = await createSupabaseAuthClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    initialUser = user ?? null;
  } catch {
    initialUser = null;
  }

  const initialTheme = parseThemePreference(
    cookieStore.get(THEME_COOKIE_NAME)?.value,
  );
  const initialThemeStyle = initialTheme
    ? getThemeInlineStyle(initialTheme)
    : undefined;
  const initialShowNsfwCookie = cookieStore.get(VIEWER_SHOW_NSFW_COOKIE)?.value;
  const initialShowNsfw =
    initialShowNsfwCookie === undefined
      ? DEFAULT_SHOW_NSFW
      : parseViewerShowNsfwCookieValue(initialShowNsfwCookie);

  return (
    <html
      lang={locale}
      className={
        initialTheme
          ? `${jetbrainsMono.variable} ${initialTheme}`
          : jetbrainsMono.variable
      }
      style={initialThemeStyle}
      suppressHydrationWarning
    >
      <head>
        {process.env.NODE_ENV === "development" && (
          <Script
            src="//unpkg.com/react-grab/dist/index.global.js"
            crossOrigin="anonymous"
            strategy="beforeInteractive"
          />
        )}
        <style id="theme-critical">{getThemeCriticalCss()}</style>
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <Script id="theme-bootstrap" strategy="beforeInteractive">
          {getThemeBootstrapScript()}
        </Script>
        <WebVitals />
        <JsonLdWebsite origin={SITE_ORIGIN} description={siteDescription} />
        <NextIntlClientProvider locale={locale} messages={messages}>
          <ThemeProvider
            attribute="class"
            defaultTheme={initialTheme ?? "system"}
            enableSystem
            enableColorScheme
            disableTransitionOnChange
            storageKey={THEME_STORAGE_KEY}
            scriptProps={{ "data-cfasync": "false" }}
          >
            <AuthProvider initialUser={initialUser}>
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
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
