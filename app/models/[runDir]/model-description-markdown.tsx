"use client";

import { ArrowDown01Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import { useLayoutEffect, useId, useRef, useState } from "react";
import ReactMarkdown, {
  defaultUrlTransform,
  type Components,
} from "react-markdown";

import { Link } from "@/i18n/navigation";

const ALLOWED_ELEMENTS = [
  "p",
  "strong",
  "em",
  "a",
  "code",
  "br",
  "ul",
  "ol",
  "li",
  "blockquote",
] as const;

export function transformModelDescriptionUrl(url: string): string | undefined {
  if (/^[\\/]{2}/.test(url)) return undefined;
  const transformed = defaultUrlTransform(url);
  if (!transformed || /^[\\/]{2}/.test(transformed)) return undefined;
  if (/^https?:\/\//i.test(transformed)) return transformed;
  if (/^[a-z][a-z\d+.-]*:/i.test(transformed)) return undefined;
  return transformed;
}

function withoutNode<T extends { node?: unknown }>(props: T): Omit<T, "node"> {
  const cleanProps = { ...props };
  delete cleanProps.node;
  return cleanProps;
}

const linkClassName =
  "text-primary rounded-sm font-medium underline decoration-primary/35 underline-offset-2 hover:decoration-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

const markdownComponents: Components = {
  p: (props) => (
    <p {...withoutNode(props)} className="mb-2 last:mb-0" />
  ),
  a: (inputProps) => {
    const props = withoutNode(inputProps);
    const href = props.href;
    delete props.href;
    const external = typeof href === "string" && /^https?:\/\//i.test(href);

    if (!href) {
      return <span {...props} className="text-muted-foreground" />;
    }
    if (!external) {
      return <Link {...props} href={href} className={linkClassName} />;
    }
    return (
      <a
        {...props}
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={linkClassName}
      />
    );
  },
  code: (props) => (
    <code
      {...withoutNode(props)}
      className="rounded-sm bg-muted/60 px-1 py-0.5 font-mono text-[0.9em] text-foreground/85"
    />
  ),
  ul: (props) => (
    <ul
      {...withoutNode(props)}
      className="mb-2 list-disc space-y-0.5 pl-5 last:mb-0"
    />
  ),
  ol: (props) => (
    <ol
      {...withoutNode(props)}
      className="mb-2 list-decimal space-y-0.5 pl-5 last:mb-0"
    />
  ),
  blockquote: (props) => (
    <blockquote
      {...withoutNode(props)}
      className="mb-2 border-l-2 border-border pl-3 text-muted-foreground last:mb-0"
    />
  ),
};

const previewComponents: Components = {
  p: (props) => <span className="mr-1">{props.children}</span>,
  strong: (props) => <span>{props.children}</span>,
  em: (props) => <span>{props.children}</span>,
  a: (props) => <span>{props.children}</span>,
  code: (props) => <span>{props.children}</span>,
  br: () => " ",
  ul: (props) => <span className="mr-1">{props.children}</span>,
  ol: (props) => <span className="mr-1">{props.children}</span>,
  li: (props) => <span className="mr-1">{props.children}</span>,
  blockquote: (props) => <span className="mr-1">{props.children}</span>,
};

const measurementComponents: Components = {
  ...markdownComponents,
  a: (props) => <span>{props.children}</span>,
};

type ModelDescriptionMarkdownProps = {
  children: string;
  expandLabel: string;
  collapseLabel: string;
  contentLabel: string;
};

export function ModelDescriptionMarkdown({
  children,
  expandLabel,
  collapseLabel,
  contentLabel,
}: ModelDescriptionMarkdownProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isOverflowing, setIsOverflowing] = useState(false);
  const measurementRef = useRef<HTMLDivElement>(null);
  const contentId = useId();

  useLayoutEffect(() => {
    if (isExpanded) return;

    const measurement = measurementRef.current;
    if (!measurement) return;

    const measure = () => {
      const lineHeight = Number.parseFloat(
        window.getComputedStyle(measurement).lineHeight,
      );
      setIsOverflowing(
        Number.isFinite(lineHeight) &&
          measurement.scrollHeight > lineHeight * 2 + 1,
      );
    };
    const frame = window.requestAnimationFrame(measure);
    const observer = new ResizeObserver(measure);
    observer.observe(measurement);

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [children, isExpanded]);

  const showPreview = isOverflowing && !isExpanded;
  const showScrollableContent = isOverflowing && isExpanded;

  return (
    <div className="relative text-muted-foreground/80 text-xs leading-5">
      <div
        ref={measurementRef}
        aria-hidden="true"
        className="pointer-events-none invisible absolute inset-x-0 top-0 wrap-break-word"
      >
        <ReactMarkdown
          skipHtml
          allowedElements={ALLOWED_ELEMENTS}
          unwrapDisallowed
          urlTransform={transformModelDescriptionUrl}
          components={measurementComponents}
        >
          {children}
        </ReactMarkdown>
      </div>

      <div
        hidden={!showPreview}
        data-testid="model-description-preview"
        className="line-clamp-2 wrap-break-word"
      >
        <ReactMarkdown
          skipHtml
          allowedElements={ALLOWED_ELEMENTS}
          unwrapDisallowed
          urlTransform={transformModelDescriptionUrl}
          components={previewComponents}
        >
          {children}
        </ReactMarkdown>
      </div>

      <div
        id={contentId}
        hidden={showPreview}
        data-testid="model-description-markdown"
        role={showScrollableContent ? "region" : undefined}
        tabIndex={showScrollableContent ? 0 : undefined}
        aria-label={showScrollableContent ? contentLabel : undefined}
        className={`wrap-break-word ${showScrollableContent ? "max-h-40 overflow-y-auto overscroll-contain pr-2 focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring" : "overflow-visible"}`}
      >
        <ReactMarkdown
          skipHtml
          allowedElements={ALLOWED_ELEMENTS}
          unwrapDisallowed
          urlTransform={transformModelDescriptionUrl}
          components={markdownComponents}
        >
          {children}
        </ReactMarkdown>
      </div>

      <button
        type="button"
        hidden={!isOverflowing}
        data-testid="model-description-toggle"
        aria-expanded={isExpanded}
        aria-controls={contentId}
        onClick={() => setIsExpanded((expanded) => !expanded)}
        className="mt-1 inline-flex items-center gap-1 rounded-sm text-xs font-medium text-muted-foreground transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        {isExpanded ? collapseLabel : expandLabel}
        <HugeiconsIcon
          icon={ArrowDown01Icon}
          strokeWidth={2}
          className={`size-3.5 transition-transform ${isExpanded ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>
    </div>
  );
}
