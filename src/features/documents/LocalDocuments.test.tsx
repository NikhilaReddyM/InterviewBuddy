import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { LocalDocuments } from './LocalDocuments'

afterEach(() => vi.unstubAllGlobals())
it('reads a source page and persists a reviewed correction', async () => {
  const doc = { id: 'abc', filename: 'Example.pdf', page_count: 1, status: 'ready', unreviewed: 1 }
  const page = { number: 1, text: 'raw OCR', direct_text: '', ocr_text: 'raw OCR', method: 'ocr', issues: ['Check symbols'], review_status: 'unreviewed', revision: 0 }
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json([doc])).mockResolvedValueOnce(Response.json(page))
    .mockResolvedValueOnce(Response.json({ ...page, text: 'corrected', review_status: 'reviewed', revision: 1 }))
  vi.stubGlobal('fetch', fetcher)
  render(<LocalDocuments />)
  fireEvent.click(screen.getByText('Open PDF library'))
  fireEvent.click(await screen.findByRole('button', { name: 'Example.pdf' }))
  const editor = await screen.findByLabelText('Reviewed text')
  expect(editor).toHaveValue('raw OCR')
  expect(screen.getByAltText('Original PDF page 1 of Example.pdf')).toHaveAttribute('src', '/api/documents/abc/pages/1/image')
  fireEvent.change(editor, { target: { value: 'corrected' } })
  fireEvent.change(screen.getByLabelText('Review status'), { target: { value: 'reviewed' } })
  fireEvent.click(screen.getByText('Save page review'))
  await screen.findByText('Page corrections and review status saved locally.')
  expect(JSON.parse(fetcher.mock.calls[2][1].body)).toMatchObject({ text: 'corrected', revision: 0, review_status: 'reviewed' })
})
it('explains when the local API is unavailable', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Backend offline')))
  render(<LocalDocuments />)
  fireEvent.click(screen.getByText('Open PDF library'))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Backend offline'))
})
it('keeps unsaved corrections when navigation is cancelled', async () => {
  const doc = { id: 'abc', filename: 'Example.pdf', page_count: 1, status: 'ready', unreviewed: 1 }
  const page = { number: 1, text: 'raw', direct_text: 'raw', ocr_text: '', method: 'direct', issues: [], review_status: 'unreviewed', revision: 0 }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json([doc])).mockResolvedValueOnce(Response.json(page)))
  vi.stubGlobal('confirm', vi.fn().mockReturnValue(false))
  render(<LocalDocuments />)
  fireEvent.click(screen.getByText('Open PDF library'))
  fireEvent.click(await screen.findByRole('button', { name: 'Example.pdf' }))
  fireEvent.change(await screen.findByLabelText('Reviewed text'), { target: { value: 'unsaved correction' } })
  const navigation = new Event('interviewbuddy:before-navigate', { cancelable: true })
  expect(window.dispatchEvent(navigation)).toBe(false)
  fireEvent.click(screen.getByText('Back to PDFs'))
  expect(screen.getByLabelText('Reviewed text')).toHaveValue('unsaved correction')
})
it('filters attention pages and removes a reviewed page from the attention queue', async () => {
  const doc = { id: 'abc', filename: 'Example.pdf', page_count: 3, status: 'ready', unreviewed: 3, needs_attention: 1, spot_check: 2 }
  const index = [
    { number: 1, review_status: 'unreviewed', needs_attention: false, attention_reasons: [], priority: 'spot_check' },
    { number: 2, review_status: 'unreviewed', needs_attention: true, attention_reasons: ['Possible code; verify symbols'], priority: 'needs_attention' },
    { number: 3, review_status: 'unreviewed', needs_attention: false, attention_reasons: [], priority: 'spot_check' },
  ]
  const base = { text: 'text', direct_text: 'text', ocr_text: '', method: 'direct', issues: [], review_status: 'unreviewed', revision: 0, page_index: index }
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json([doc]))
    .mockResolvedValueOnce(Response.json({ ...base, number: 1, attention_reasons: [] }))
    .mockResolvedValueOnce(Response.json({ ...base, number: 2, attention_reasons: index[1].attention_reasons }))
    .mockResolvedValueOnce(Response.json({ ...base, number: 2, review_status: 'reviewed', revision: 1,
      page_index: index.map(p => p.number === 2 ? { ...p, review_status: 'reviewed', needs_attention: false, priority: 'reviewed' } : p) }))
  vi.stubGlobal('fetch', fetcher)
  render(<LocalDocuments />)
  fireEvent.click(screen.getByText('Open PDF library'))
  fireEvent.click(await screen.findByRole('button', { name: 'Example.pdf' }))
  await screen.findByLabelText('Reviewed text')
  fireEvent.change(screen.getByLabelText('Review filter'), { target: { value: 'attention' } })
  await screen.findByText('Possible code; verify symbols')
  expect(screen.getByRole('combobox', { name: /^PDF page/ })).toHaveValue('2')
  expect(screen.getByText('Next page')).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Review status'), { target: { value: 'reviewed' } })
  fireEvent.click(screen.getByText('Save page review'))
  await screen.findByText('No pages match this filter. Choose All pages to browse the document.')
  expect(screen.getByLabelText('Reviewed text')).toHaveValue('text')
})
it('separates reader and indexing views and guards an unsaved review before switching', async () => {
  const doc = { id: 'abc', filename: 'Example.pdf', page_count: 1, status: 'ready', unreviewed: 1 }
  const page = { number: 1, text: 'original', direct_text: 'original', ocr_text: '', method: 'direct', issues: [], review_status: 'unreviewed', revision: 0 }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json([doc])).mockResolvedValueOnce(Response.json(page))
    .mockResolvedValueOnce(Response.json({ state: 'not_indexed', chunks: [] })))
  const confirm = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true)
  vi.stubGlobal('confirm', confirm)
  render(<LocalDocuments />)
  fireEvent.click(screen.getByText('Open PDF library'))
  fireEvent.click(await screen.findByRole('button', { name: 'Example.pdf' }))
  const editor = await screen.findByLabelText('Reviewed text')
  expect(screen.queryByText('Make this PDF searchable')).not.toBeInTheDocument()
  fireEvent.change(editor, { target: { value: 'unsaved' } })
  fireEvent.click(screen.getByRole('button', { name: 'Index & search' }))
  expect(editor).toBeVisible()
  expect(editor).toHaveValue('unsaved')
  fireEvent.click(screen.getByRole('button', { name: 'Index & search' }))
  await screen.findByText('Saved index: Not built')
  expect(editor).not.toBeVisible()
  expect(editor).toHaveValue('original')
  fireEvent.click(screen.getByRole('button', { name: 'Read & review' }))
  expect(editor).toBeVisible()
})
