import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryComposer, dateFromFilename } from './QueryComposer';
import type { QueryImage } from '../types/contract';

describe('dateFromFilename', () => {
  it.each([
    ['urban_expansion_t1_2021-01-01.tif', '2021-01-01'],
    ['scene_2024_06_15.tif', '2024-06-15'],
    ['S2A_MSIL2A_20240615T103021_N0510_R108_T32UQD.SAFE.tif', '2024-06-15'],
    ['real_sentinel2_change_t1_2022.tif', undefined], // a year alone is not a date
    ['img_20241332.tif', undefined], // month 13
    ['img_20240230x.tif', '2024-02-30'], // shape only; the user can still correct it
    ['1234567890123.tif', undefined],
    ['', undefined],
  ])('%s -> %s', (name, expected) => {
    expect(dateFromFilename(name)).toBe(expected);
  });
});

const img = (id: string, modality: 'optical' | 'sar', date?: string): QueryImage => ({
  id, modality, date, url_or_base64: `/api/v1/assets/${id}`, asset_id: id, name: `${id}.tif`,
  previewUrl: 'data:image/png;base64,AAAA',
});

function setup(images: QueryImage[], query = 'What changed?') {
  const onExecute = vi.fn();
  render(<QueryComposer onExecute={onExecute} isLoading={false} initialQuery={query} initialImages={images} />);
  const analyze = screen.getByRole('button', { name: /analyze/i });
  return { onExecute, analyze };
}

describe('QueryComposer guardrails', () => {
  it('blocks two SAR images and says which pairs are supported', () => {
    const { analyze } = setup([img('a', 'sar'), img('b', 'sar')]);
    expect(analyze).toBeDisabled();
    // Visible even with the image drawer collapsed (as after loading a preset)...
    expect(screen.getByRole('status')).toHaveTextContent(/Supported 2-image tasks/);
  });

  it('shows the full notice in the drawer once it is opened', async () => {
    setup([img('a', 'sar'), img('b', 'sar')]);
    await userEvent.click(screen.getByRole('button', { name: /2 images attached/ }));
    expect(screen.getByText(/Supported 2-image tasks/)).toBeInTheDocument();
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getAllByTitle('Remove image')).toHaveLength(2);
  });

  it('allows optical + SAR (fusion)', async () => {
    const { analyze, onExecute } = setup([img('a', 'optical'), img('b', 'sar')], 'Classify land cover');
    expect(analyze).toBeEnabled();
    await userEvent.click(analyze);
    expect(onExecute).toHaveBeenCalledTimes(1);
    const [q, images] = onExecute.mock.calls[0];
    expect(q).toBe('Classify land cover');
    expect(images.map((i: QueryImage) => i.modality)).toEqual(['optical', 'sar']);
  });

  it('warns when two optical images share a capture date', () => {
    setup([img('a', 'optical', '2024-01-01'), img('b', 'optical', '2024-01-01')]);
    expect(screen.getByRole('status')).toHaveTextContent(/differing capture dates/);
  });

  it('asks for both dates on a change-detection pair', () => {
    setup([img('a', 'optical', '2024-01-01'), img('b', 'optical')]);
    expect(screen.getByRole('status')).toHaveTextContent(/Set both capture dates/);
  });

  it('needs a query and at least one image', () => {
    expect(setup([], 'Describe').analyze).toBeDisabled();
  });
});
