import { describe, expect, it, vi } from 'vitest';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DEMO_PRESETS, DemoPresetSelector } from './DemoPresetSelector';

const SAMPLES = resolve(__dirname, '../../public/samples');
const MAGIC: Record<string, number[][]> = {
  '.tif': [[0x49, 0x49, 0x2a, 0x00], [0x4d, 0x4d, 0x00, 0x2a], [0x49, 0x49, 0x2b, 0x00]],
  '.jp2': [[0x00, 0x00, 0x00, 0x0c, 0x6a, 0x50]],
};

const files = [...new Set(DEMO_PRESETS.flatMap((p) => p.samples.map((s) => s.file)))];

describe('DEMO_PRESETS', () => {
  it.each(files)('sample %s is bundled, non-trivial and really an image', (file) => {
    const path = resolve(SAMPLES, file);
    expect(existsSync(path), `${file} missing: run scripts/build_demo_samples.py`).toBe(true);
    expect(statSync(path).size).toBeGreaterThan(1024);
    const head = [...readFileSync(path).subarray(0, 8)];
    const ext = file.slice(file.lastIndexOf('.'));
    expect(MAGIC[ext]?.some((m) => m.every((b, i) => head[i] === b)), `${file} has the wrong magic bytes`).toBe(true);
  });

  it.each(files)('sample %s is tracked by git, so a clean checkout has it', (file) => {
    let tracked = '';
    try {
      tracked = execFileSync('git', ['ls-files', '--', `public/samples/${file}`], { cwd: resolve(__dirname, '../..') }).toString();
    } catch {
      return; // not a git checkout (e.g. a source tarball): nothing to check
    }
    expect(tracked.trim(), `${file} is not committed (check .gitignore)`).toBe(`public/samples/${file}`);
  });

  it('has unique ids and sensible image/modality combinations', () => {
    expect(new Set(DEMO_PRESETS.map((p) => p.id)).size).toBe(DEMO_PRESETS.length);
    for (const p of DEMO_PRESETS) {
      expect(p.query.trim().length).toBeGreaterThan(5);
      expect(p.samples.length).toBeGreaterThanOrEqual(1);
      expect(p.samples.length).toBeLessThanOrEqual(2);
      if (p.samples.length === 2) {
        const mods = p.samples.map((s) => s.modality).sort().join('+');
        expect(['optical+optical', 'optical+sar']).toContain(mods);
        if (mods === 'optical+optical') {
          const [a, b] = p.samples.map((s) => s.date);
          expect(a && b && a < b, `${p.id}: change detection needs two increasing dates`).toBeTruthy();
        }
      }
    }
  });
});

describe('DemoPresetSelector', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<DemoPresetSelector isOpen={false} onClose={vi.fn()} onSelectPreset={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('selecting a card hands the preset over and closes', async () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(<DemoPresetSelector isOpen onClose={onClose} onSelectPreset={onSelect} />);
    await userEvent.click(screen.getByText(DEMO_PRESETS[1].title));
    expect(onSelect).toHaveBeenCalledWith(DEMO_PRESETS[1]);
    expect(onClose).toHaveBeenCalled();
  });
});
