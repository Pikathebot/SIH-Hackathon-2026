import React from 'react';

/**
 * Minimal, safe rendering of the markdown subset the VLM writes in answers:
 * paragraphs, "-"/"*"/"1." list items, "#" headings, **bold**, *italic* and `code`.
 * Text is never interpreted as HTML: the UI gets React nodes, and the report
 * export gets HTML with every character escaped.
 */

type Inline = { text: string; bold?: boolean; italic?: boolean; code?: boolean };
type Block =
  | { kind: 'p'; inline: Inline[] }
  | { kind: 'h'; inline: Inline[] }
  | { kind: 'ul' | 'ol'; items: Inline[][]; start?: number };

const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|(?<![*\w])\*[^*\s][^*\n]*\*(?!\w))/g;

function parseInline(s: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of s.matchAll(INLINE)) {
    const i = m.index ?? 0;
    if (i > last) out.push({ text: s.slice(last, i) });
    const tok = m[0];
    if (tok.startsWith('**')) out.push({ text: tok.slice(2, -2), bold: true });
    else if (tok.startsWith('`')) out.push({ text: tok.slice(1, -1), code: true });
    else out.push({ text: tok.slice(1, -1), italic: true });
    last = i + tok.length;
  }
  if (last < s.length) out.push({ text: s.slice(last) });
  return out;
}

// Models sometimes put list markers inline ("Evidence: - one - two"); split those onto lines.
function normalise(text: string): string {
  return text
    .replace(/\r\n?/g, '\n')
    .replace(/:\s+(?=(?:-|\*|\d+\.)\s+\S)/g, ':\n')
    .replace(/\s+(?=(?:-|\*)\s+\*\*)/g, '\n')
    .replace(/(?<=[.!?])\s+(?=(?:-|\d+\.)\s+[A-Z*])/g, '\n');
}

export function parseAnswer(text: string): Block[] {
  const blocks: Block[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) blocks.push({ kind: 'p', inline: parseInline(para.join(' ')) });
    para = [];
  };
  for (const raw of normalise(text).split('\n')) {
    const line = raw.trim();
    if (!line) { flush(); continue; }
    const ul = /^[-*•]\s+(.*)$/.exec(line);
    const ol = /^(\d+)[.)]\s+(.*)$/.exec(line);
    const h = /^#{1,6}\s+(.*)$/.exec(line);
    if (ul || ol) {
      flush();
      const kind = ul ? 'ul' : 'ol';
      const item = parseInline(ul ? ul[1] : ol![2]);
      const prev = blocks[blocks.length - 1];
      if (prev && prev.kind === kind) prev.items.push(item);
      else blocks.push({ kind, items: [item], start: ol ? Number(ol[1]) : undefined });
    } else if (h) {
      flush();
      blocks.push({ kind: 'h', inline: parseInline(h[1]) });
    } else {
      para.push(line);
    }
  }
  flush();
  return blocks;
}

const renderInline = (parts: Inline[]) =>
  parts.map((p, i) =>
    p.code ? <code key={i} className="font-mono text-[0.9em] bg-surface-variant px-1 rounded">{p.text}</code>
    : p.bold ? <strong key={i} className="font-semibold">{p.text}</strong>
    : p.italic ? <em key={i}>{p.text}</em>
    : <React.Fragment key={i}>{p.text}</React.Fragment>
  );

export const AnswerText: React.FC<{ text: string }> = ({ text }) => (
  <div className="flex flex-col gap-2">
    {parseAnswer(text).map((b, i) =>
      b.kind === 'p' ? <p key={i}>{renderInline(b.inline)}</p>
      : b.kind === 'h' ? <p key={i} className="font-semibold">{renderInline(b.inline)}</p>
      : b.kind === 'ul' ? <ul key={i} className="list-disc pl-5 flex flex-col gap-1">{b.items.map((it, j) => <li key={j}>{renderInline(it)}</li>)}</ul>
      : <ol key={i} start={b.start} className="list-decimal pl-5 flex flex-col gap-1">{b.items.map((it, j) => <li key={j}>{renderInline(it)}</li>)}</ol>
    )}
  </div>
);

export function escapeHtml(s: unknown): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const inlineHtml = (parts: Inline[]) =>
  parts.map((p) => {
    const t = escapeHtml(p.text);
    return p.code ? `<code>${t}</code>` : p.bold ? `<strong>${t}</strong>` : p.italic ? `<em>${t}</em>` : t;
  }).join('');

/** Same formatting as <AnswerText>, as escaped HTML for the printable report. */
export function answerToHtml(text: string): string {
  return parseAnswer(text).map((b) =>
    b.kind === 'p' ? `<p>${inlineHtml(b.inline)}</p>`
    : b.kind === 'h' ? `<p><strong>${inlineHtml(b.inline)}</strong></p>`
    : `<${b.kind}${b.kind === 'ol' && b.start ? ` start="${b.start}"` : ''}>${b.items.map((it) => `<li>${inlineHtml(it)}</li>`).join('')}</${b.kind}>`
  ).join('');
}
