import fs from "node:fs/promises";
import path from "node:path";

import type { Metadata } from "next";
import ReactMarkdown from "react-markdown";

export const dynamic = "force-static";

export const metadata: Metadata = {
  title: "关于 - SD Style Lab",
  description: "关于 SD Style Lab 与项目介绍",
};

export default async function InfoPage() {
  const filePath = path.join(process.cwd(), "data", "info-page.md");
  let content = "";
  try {
    content = await fs.readFile(filePath, "utf-8");
  } catch (error) {
    content = "内容加载失败，请稍后重试。";
    console.error("Failed to read info-page.md", error);
  }

  return (
    <main className="h-full w-full overflow-y-auto">
      <div className="container mx-auto px-4 py-12 md:py-24">
        <div className="prose-custom max-w-3xl mx-auto">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      </div>
    </main>
  );
}
