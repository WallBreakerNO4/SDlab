import { useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";

export function SiteFooter() {
  const t = useTranslations("footer");
  const year = new Date().getFullYear();

  return (
    <footer className="text-muted-foreground w-full border-t px-4 py-1.5 text-center text-[11px] flex flex-wrap items-center justify-center gap-x-2">
      <span>{t("copyright", { year })}</span>
      <span className="hidden sm:inline">·</span>
      <Link
        href="/info"
        className="hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-[2px]"
      >
        {t("about")}
      </Link>
      <span className="hidden sm:inline">·</span>
      <Link
        href="/privacy-policy"
        className="hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-[2px]"
      >
        {t("privacy")}
      </Link>
    </footer>
  );
}
