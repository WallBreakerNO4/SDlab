import type { Metadata } from "next";
import ReactMarkdown from "react-markdown";

import infoPageMarkdown from "@/data/info-page.md";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "关于 - SD Style Lab",
  description: "关于 SD Style Lab 与项目介绍",
};

export default function InfoPage() {
  return (
    <main className="h-full w-full overflow-y-auto">
      <div className="container mx-auto px-4 py-12 md:py-24">
        <div className="prose-custom max-w-3xl mx-auto">
          <ReactMarkdown>{infoPageMarkdown}</ReactMarkdown>
        </div>
      </div>
    </main>
  );
}
