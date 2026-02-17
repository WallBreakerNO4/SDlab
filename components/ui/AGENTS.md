# components/ui/ — shadcn/radix 基础组件

## 概览

- 该目录是 UI primitives：shadcn 模板 + Tailwind + Radix 组合；业务组件应优先复用这些 primitives。

## 入口与依赖

- 设计系统配置：`components.json`（style: `radix-lyra`，`app/globals.css` 为 CSS 入口，aliases `@/components/ui` 等）
- 全局样式与 tokens：`app/globals.css`（导入 `tailwindcss`/`tw-animate-css`/`shadcn/tailwind.css` 并定义 CSS 变量）
- className 合并：`lib/utils.ts:cn()`（`clsx` + `tailwind-merge`）

## 组件实现约定

- variants：普遍用 `class-variance-authority`（`cva`）定义 `variant/size` 等，并导出 `VariantProps`（例：`components/ui/button.tsx`）
- asChild：很多组件支持 `asChild` 并用 `radix-ui` 的 `Slot` 透传到子元素，便于在 Link/a 等场景复用样式
- 可访问性：依赖 Radix 组件的 aria/keyboard 行为；保留 `focus-visible`/`aria-invalid` 等状态类
- token 优先：颜色/圆角/边框等使用 `bg-background`、`text-foreground`、`border-border` 这类 token 类名（对应 `app/globals.css` 的 CSS 变量）

## 反模式

- 不要在 primitives 中引入 ComfyUI 领域数据结构（那些属于 `components/comfyui` / `app/`）
- 不要绕过 `cn()` 手写长串 className 合并逻辑（会破坏 tailwind-merge 的冲突解析）
