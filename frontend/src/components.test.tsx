import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Badge } from './components';

describe('engineering review status presentation',()=>{
  it('distinguishes unresolved identity conflicts from resolved decisions',()=>{
    expect(renderToStaticMarkup(<Badge value="unresolved"/>)).toContain('badge warning');
    expect(renderToStaticMarkup(<Badge value="resolved"/>)).toContain('badge success');
  });
  it('never presents an unconfirmed failure as confirmed evidence',()=>{
    expect(renderToStaticMarkup(<Badge value="unconfirmed"/>)).toContain('badge danger');
    expect(renderToStaticMarkup(<Badge value="confirmed"/>)).toContain('badge success');
  });
});
