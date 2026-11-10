import { Check, Copy } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/feedback";
import type { OcrStatus } from "@/lib/api";

const OCR_BADGES: Record<OcrStatus, { label: string; variant: "success" | "warning" | "secondary" }> = {
  used: { label: "OCR used", variant: "success" },
  failed: { label: "OCR failed", variant: "warning" },
  not_used: { label: "OCR not needed", variant: "secondary" },
};

interface MarkdownResultProps {
  title: string;
  value: string;
  busy: boolean;
  ocrStatus: OcrStatus | "";
}

/** Streams model output as Markdown. Raw HTML in the output is never rendered. */
export function MarkdownResult({ title, value, busy, ocrStatus }: MarkdownResultProps) {
  const [copied, setCopied] = useState(false);
  const badge = ocrStatus ? OCR_BADGES[ocrStatus] : null;

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be denied; the text is still selectable.
    }
  }

  return (
    <Card aria-busy={busy}>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>{title}</CardTitle>
          {badge ? <Badge variant={badge.variant}>{badge.label}</Badge> : null}
        </div>
        <Button variant="outline" size="sm" onClick={() => void copy()} disabled={busy}>
          {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {copied ? "Copied" : "Copy Markdown"}
        </Button>
      </CardHeader>
      <CardContent>
        <div className="markdown-body">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ node: _node, children, ...props }) => (
                <a {...props} target="_blank" rel="noreferrer">
                  {children}
                </a>
              ),
              // The page already has an h1 and the card title is an h2: shift headings down.
              h1: ({ node: _node, children, ...props }) => <h3 {...props}>{children}</h3>,
              h2: ({ node: _node, children, ...props }) => <h4 {...props}>{children}</h4>,
              h3: ({ node: _node, children, ...props }) => <h5 {...props}>{children}</h5>,
              h4: ({ node: _node, children, ...props }) => <h6 {...props}>{children}</h6>,
            }}
          >
            {value}
          </ReactMarkdown>
          {busy ? <span className="stream-cursor" aria-hidden="true" /> : null}
        </div>
      </CardContent>
    </Card>
  );
}
