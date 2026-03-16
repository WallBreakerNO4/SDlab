# components/ui/ — shadcn/radix 基础组件

## 概览

- UI primitives：shadcn 模板 + Tailwind + Radix 组合；业务组件应优先复用这些 primitives。

## 入口与依赖

- 设计系统配置：`components.json`（style: `radix-lyra`，`app/globals.css` 为 CSS 入口，aliases `@/components/ui` 等）
- 全局样式与 tokens：`app/globals.css`（导入 `tailwindcss`/`tw-animate-css`/`shadcn/tailwind.css` 并定义 CSS 变量）
- className 合并：`lib/utils.ts:cn()`（`clsx` + `tailwind-merge`）
- 复杂容器 primitive：`sidebar.tsx`（`SidebarProvider` + cookie 持久化 + `Ctrl/Cmd+B` 快捷键 + mobile `Sheet`）

## 组件实现约定

- variants：普遍用 `class-variance-authority`（`cva`）定义 `variant/size` 等，并导出 `VariantProps`
- asChild：很多组件支持 `asChild` 并用 `radix-ui` 的 `Slot` 透传到子元素
- 可访问性：依赖 Radix 组件的 aria/keyboard 行为；保留 `focus-visible`/`aria-invalid` 等状态类
- token 优先：颜色/圆角/边框等使用 `bg-background`、`text-foreground`、`border-border` 等 token 类名
- 容器级 primitive（如 `sidebar.tsx`）允许自带 context/provider，但仍只能封装通用 UI 状态，不能混入业务数据获取

## 反模式

- 不要在 primitives 中引入 ComfyUI 领域数据结构（属于 `components/comfyui` / `app/`）
- 不要绕过 `cn()` 手写长串 className 合并逻辑
- 不要把页面级业务状态塞进 `SidebarProvider` 这类 UI context
