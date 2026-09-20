"use client";

import { useTranslations } from "next-intl";

/** 对比矩阵的次要说明：进行中评测不参与对比，完结后自动加入。 */
export function ComparisonInProgressNote() {
  const t = useTranslations("styleFavorites");

  return (
    <p
      data-testid="comparison-in-progress-note"
      className="mt-1 max-w-2xl text-xs leading-relaxed text-muted-foreground/70"
    >
      {t("comparisonInProgressNote")}
    </p>
  );
}
