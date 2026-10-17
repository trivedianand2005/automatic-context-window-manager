import { Check, Copy } from "lucide-react";
import { Highlight, themes } from "prism-react-renderer";
import { useState } from "react";

const LANG: Record<string, string> = {
  python: "python", json: "json", yaml: "yaml", toml: "toml", markdown: "markdown", ini: "ini",
};

/** Syntax-highlighted, copyable code block. ACWM marker comments are dimmed. */
export function CodeView({ code, language, maxHeight = 420 }: { code: string; language: string; maxHeight?: number }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked; ignore */
    }
  };
  return (
    <div className="relative overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950">
      <button onClick={copy} className="absolute top-2 right-2 z-10 rounded-md border border-zinc-700 bg-zinc-900 p-1.5 text-zinc-300 hover:bg-zinc-800" aria-label="Copy code">
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
      <Highlight code={code} language={LANG[language] ?? "text"} theme={themes.vsDark}>
        {({ tokens, getLineProps, getTokenProps }) => (
          <pre className="overflow-auto p-4 text-[12.5px] leading-relaxed" style={{ maxHeight, fontFamily: "var(--font-mono)", background: "transparent" }}>
            {tokens.map((line, i) => {
              const text = line.map((t) => t.content).join("");
              const marker = /^#\s*(---|\.\.\.|\[ACWM)/.test(text.trim());
              return (
                <div key={i} {...getLineProps({ line })} className={marker ? "text-sky-300/70 italic" : undefined}>
                  {line.map((token, k) =>
                    marker ? <span key={k}>{token.content}</span> : <span key={k} {...getTokenProps({ token })} />,
                  )}
                </div>
              );
            })}
          </pre>
        )}
      </Highlight>
    </div>
  );
}
