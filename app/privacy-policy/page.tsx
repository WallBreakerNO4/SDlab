import type { Metadata } from "next";
import ReactMarkdown from "react-markdown";

import privacyPolicyPageMarkdown from "@/data/privacy-policy-page.md";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "隐私权政策 - SD Style Lab",
  description: "SD Style Lab 的隐私权政策说明",
};

export default function PrivacyPolicyPage() {
  return (
    <main className="h-full w-full overflow-y-auto">
      <div className="container mx-auto px-4 py-12 md:py-24">
        <div className="prose-custom max-w-3xl mx-auto">
          <ReactMarkdown>{privacyPolicyPageMarkdown}</ReactMarkdown>
        </div>
      </div>
    </main>
  );
}
