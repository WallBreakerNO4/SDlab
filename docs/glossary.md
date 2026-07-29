# 项目术语表

本文档记录模型指南内容与 Web 展示边界使用的领域术语。

## Model Guide（模型使用指南）

与一个 `model_key` 绑定的 Markdown 使用经验文章。它描述模型本身的使用方式，不绑定某次生图运行或 release。每个模型可以没有指南，也可以分别拥有可选的中文和英文版本。

公开路由为 `/[locale]/guides/[modelKey]`。文件存在并通过构建校验即视为已发布，不存在草稿状态。

## `model_key`

模型本身的稳定、机器可读身份，由指南 Markdown 的 frontmatter 声明。

当前 Web 约定模型详情页的 `runDir` 与指南 `model_key` 一致。模型页直接使用其路由参数查询 Guide Index，不通过数据库或上传链路传递文章身份。

## `run_dir`

现有模型详情页 `/[locale]/models/[runDir]` 的路由参数。

指南功能将它作为 Guide Index 的查询键，并约定其值与目标文章的 frontmatter `model_key` 相同。若未来允许二者不同，应作为独立功能设计明确的关联来源。

## Guide Locale（指南语言）

Markdown frontmatter 的 `locale` 字段，表示该文章正文的实际语言。当前允许值为 `zh` 和 `en`。

指南语言版本彼此独立且均为可选。页面、sitemap、canonical 和 `hreflang` 只能声明真实存在的语言文章。

## Locale Fallback（语言回退）

当请求语言没有指南、但另一语言存在指南时，将用户临时重定向到实际存在语言的行为。

语言回退不生成缺失语言的虚假文章，不把缺失语言 URL加入 sitemap，也不把它声明为 canonical 或 `hreflang` 目标。两种语言均不存在时不发生回退，模型页隐藏按钮，指南直达 URL 返回 404。

## Guide Index（指南索引）

构建时扫描 Markdown frontmatter 后自动生成的服务端派生数据。索引按 `(model_key, locale)` 定位文章正文与标题，并用于按钮解析、指南路由、静态参数和 SEO 输出。

Guide Index 不是需要人工维护的注册表。删除后可以根据 Git 中的 Markdown 内容重新生成；新增或修改指南也只需要重新运行网站构建。
