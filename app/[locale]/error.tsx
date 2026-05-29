"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Link } from "@/i18n/navigation";

export default function ErrorPage({
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- Next.js 要求的 prop
  error: _error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const tMeta = useTranslations("metadata.error");

  return (
    <main className="flex h-full w-full items-center justify-center">
      <Empty>
        <EmptyHeader>
          <EmptyTitle>{tMeta("title")}</EmptyTitle>
          <EmptyDescription>{tMeta("description")}</EmptyDescription>
        </EmptyHeader>
        <div className="mt-4 flex items-center gap-3">
          <Button type="button" onClick={reset} variant="default">
            {tMeta("retry")}
          </Button>
          <Button type="button" asChild variant="outline">
            <Link href="/">{tMeta("goHome")}</Link>
          </Button>
        </div>
      </Empty>
    </main>
  );
}
