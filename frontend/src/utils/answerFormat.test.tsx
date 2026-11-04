import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { AnswerText, answerToHtml, escapeHtml, parseAnswer } from './answerFormat';

const HOSTILE = '<img src=x onerror=alert(1)><script>alert(2)</script> & "quotes" \'single\'';

describe('parseAnswer', () => {
  it('splits paragraphs, headings and lists', () => {
    const blocks = parseAnswer('# Summary\nTwo ships.\n\n- one\n- two\n\n3. third\n4. fourth');
    expect(blocks.map((b) => b.kind)).toEqual(['h', 'p', 'ul', 'ol']);
    const ol = blocks[3] as { kind: 'ol'; items: unknown[]; start?: number };
    expect(ol.items).toHaveLength(2);
    expect(ol.start).toBe(3);
  });

  it('parses bold, italic and code inline', () => {
    const [p] = parseAnswer('a **bold** b *it* c `code` d');
    expect(p.kind).toBe('p');
    const inline = (p as { inline: { text: string; bold?: boolean; italic?: boolean; code?: boolean }[] }).inline;
    expect(inline.find((i) => i.bold)?.text).toBe('bold');
    expect(inline.find((i) => i.italic)?.text).toBe('it');
    expect(inline.find((i) => i.code)?.text).toBe('code');
  });

  it('moves inline list markers the model writes onto their own lines', () => {
    const blocks = parseAnswer('Evidence: - first point - second point');
    expect(blocks[0].kind).toBe('p');
    expect(blocks[1]).toMatchObject({ kind: 'ul' });
  });

  it('does not treat multiplication or lone asterisks as italics', () => {
    const [p] = parseAnswer('area 3 * 4 km and a*b');
    const inline = (p as { inline: { italic?: boolean }[] }).inline;
    expect(inline.some((i) => i.italic)).toBe(false);
  });

  it('copes with empty and whitespace-only answers', () => {
    expect(parseAnswer('')).toEqual([]);
    expect(parseAnswer('\n\n  \r\n')).toEqual([]);
  });
});

describe('AnswerText', () => {
  it('renders HTML in an answer as text, never as elements', () => {
    const { container } = render(<AnswerText text={`**${HOSTILE}**\n- ${HOSTILE}`} />);
    expect(container.querySelector('img, script')).toBeNull();
    expect(container.textContent).toContain('<script>alert(2)</script>');
    expect(container.querySelector('strong')).not.toBeNull();
    expect(container.querySelector('li')).not.toBeNull();
  });
});

describe('escapeHtml / answerToHtml', () => {
  it('escapes all five HTML-significant characters', () => {
    expect(escapeHtml(`<>&"'`)).toBe('&lt;&gt;&amp;&quot;&#39;');
    expect(escapeHtml(null)).toBe('');
    expect(escapeHtml(42)).toBe('42');
  });

  it('produces markup with no live tags from a hostile answer', () => {
    const html = answerToHtml(`# ${HOSTILE}\n**${HOSTILE}**\n- ${HOSTILE}\n1. \`${HOSTILE}\``);
    const doc = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html');
    expect(doc.querySelector('img, script')).toBeNull();
    expect([...doc.body.querySelectorAll('*')].every((el) => el.attributes.length === 0 || el.tagName === 'OL')).toBe(true);
    expect(doc.body.textContent).toContain('<script>alert(2)</script>');
  });
});
