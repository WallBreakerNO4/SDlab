import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="text-muted-foreground w-full border-t px-4 py-1.5 text-center text-[11px] flex flex-wrap items-center justify-center gap-x-2">
      <span>
        &copy; {new Date().getFullYear()} SD Style Lab · AI 图像风格探索平台
      </span>
      <span className="hidden sm:inline">·</span>
      <Link
        href="/info"
        className="hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-[2px]"
      >
        关于
      </Link>
      <span className="hidden sm:inline">·</span>
      <Link
        href="/privacy-policy"
        className="hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-[2px]"
      >
        隐私权政策
      </Link>
    </footer>
  );
}
