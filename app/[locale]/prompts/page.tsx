import { getTranslations } from "next-intl/server"
import { buildSeoMetadata } from "@/lib/metadata-utils"
import PromptBrowserPage from "@/components/prompt/prompt-browser-page"
import { ModelProvider } from "@/lib/prompt-model-context"
import { ChoiceProvider } from "@/lib/prompt-choice-context"
import type { Metadata } from "next"

interface PromptsPageProps {
  params: Promise<{ locale: string }>
}

export async function generateMetadata({
  params,
}: PromptsPageProps): Promise<Metadata> {
  const { locale } = await params
  const t = await getTranslations({ locale, namespace: "prompts" })

  return buildSeoMetadata({
    locale,
    path: "/prompts",
    title: t("title"),
    description: t("description"),
  })
}

export default async function PromptsPage({ params }: PromptsPageProps) {
  await params // 消费 params 以满足 Next.js 约定，locale 由 i18n provider 处理

  return (
    <ModelProvider>
      <ChoiceProvider>
        <PromptBrowserPage />
      </ChoiceProvider>
    </ModelProvider>
  )
}
