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

export default function NotFoundPage() {
  const tMeta = useTranslations("metadata.notFound");

  return (
    <main className="flex h-full w-full items-center justify-center">
      <Empty>
        <EmptyHeader>
          <EmptyTitle>{tMeta("title")}</EmptyTitle>
          <EmptyDescription>{tMeta("description")}</EmptyDescription>
        </EmptyHeader>
        <div className="mt-4">
          <Button type="button" asChild>
            <Link href="/">{tMeta("goHome")}</Link>
          </Button>
        </div>
      </Empty>
    </main>
  );
}
