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
  const { locale } = await params

  return (
    <ModelProvider>
      <ChoiceProvider>
        <PromptBrowserPage />
      </ChoiceProvider>
    </ModelProvider>
  )
}
