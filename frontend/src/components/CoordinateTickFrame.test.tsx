import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { CoordinateTickFrame } from './CoordinateTickFrame';
import type { VisualEvidence } from '../types/contract';

const PNG = 'data:image/png;base64,iVBORw0KGgo=';

const boxesOf = (container: HTMLElement) =>
  [...container.querySelectorAll<HTMLElement>('[style*="left"][style*="width"]')]
    .filter((el) => el.style.left.endsWith('%'));

describe('CoordinateTickFrame', () => {
  it('places boxes as fractions of the server pixel grid (image_size), not the preview size', () => {
    const ev: VisualEvidence = { type: 'bbox', boxes: [[100, 50, 300, 250], [900, 400, 700, 300]], image_size: [1000, 500] };
    const { container } = render(<CoordinateTickFrame imageUrl={PNG} visualEvidence={ev} />);
    const boxes = boxesOf(container);
    expect(boxes).toHaveLength(2);
    expect(boxes[0].style).toMatchObject({ left: '10%', top: '10%', width: '20%', height: '40%' });
    // Reversed corners are normalised
    expect(boxes[1].style).toMatchObject({ left: '70%', top: '60%', width: '20%', height: '20%' });
    expect(screen.getByRole('button', { name: 'Boxes (2)' })).toBeInTheDocument();
  });

  it('toggles boxes off and on', () => {
    const ev: VisualEvidence = { type: 'bbox', boxes: [[0, 0, 10, 10]], image_size: [100, 100] };
    const { container } = render(<CoordinateTickFrame imageUrl={PNG} visualEvidence={ev} />);
    const toggle = screen.getByRole('button', { name: 'Boxes (1)' });
    fireEvent.click(toggle);
    expect(boxesOf(container)).toHaveLength(0);
    fireEvent.click(toggle);
    expect(boxesOf(container)).toHaveLength(1);
  });

  it('labels georeferenced imagery and shows its ground extent', () => {
    const ev: VisualEvidence = {
      type: 'none', geospatial: { crs: 'EPSG:4326', image_bounds: [77.0, 28.0, 77.1, 28.1] },
    };
    render(<CoordinateTickFrame imageUrl={PNG} visualEvidence={ev} />);
    expect(screen.getByText('Georeferenced (WGS84)')).toBeInTheDocument();
    // 0.1 x 0.1 deg at 28 N is ~9.8 x 11.1 km; values of 10 km and more are shown whole
    expect(screen.getByText(/^Extent:/).textContent).toBe('Extent: 9.8 × 11 km');
  });

  it('falls back to pixel coordinates without georeferencing', () => {
    render(<CoordinateTickFrame imageUrl={PNG} visualEvidence={{ type: 'none' }} />);
    expect(screen.getByText('Pixel coordinates')).toBeInTheDocument();
  });

  it('never puts a non-renderable source (raw TIFF, javascript:) into an <img>', () => {
    for (const url of ['data:image/tiff;base64,SUkqAA==', 'javascript:alert(1)']) {
      const { container, unmount } = render(<CoordinateTickFrame imageUrl={url} />);
      expect([...container.querySelectorAll('img')].map((i) => i.getAttribute('src'))).not.toContain(url);
      unmount();
    }
  });
});
