import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { RetrievalComparison } from './RetrievalComparison'
afterEach(()=>vi.unstubAllGlobals())
it('compares only explicitly selected documents and labels evidence unverified', async()=>{
  const hit={id:'c',text:'Example passage',score:1,metadata:{document_id:'d',filename:'DP.pdf',pages:[40],review_status:'unreviewed'}}
  const fetcher=vi.fn().mockImplementation((_url, options)=>Promise.resolve(Response.json({method:JSON.parse(options.body).method,elapsed_ms:2,results:[hit]})))
  vi.stubGlobal('fetch',fetcher)
  render(<RetrievalComparison documents={[{id:'d',filename:'DP.pdf',page_count:157}]} />)
  fireEvent.click(screen.getByText('Compare search methods'))
  expect(screen.getByText('Compare all three')).toBeDisabled()
  fireEvent.click(screen.getByLabelText('DP.pdf'))
  fireEvent.change(screen.getByLabelText('Comparison question'),{target:{value:'What is DP?'}})
  fireEvent.click(screen.getByText('Compare all three'))
  await screen.findByText(/Evidence unverified/)
  expect(fetcher).toHaveBeenCalledTimes(3)
  expect(fetcher.mock.calls.map(call=>JSON.parse(call[1].body).method)).toEqual(['dense','keyword','hybrid'])
  expect(JSON.parse(fetcher.mock.calls[0][1].body).document_ids).toEqual(['d'])
  expect(screen.getAllByText('Open supporting page')[0]).toHaveAttribute('href','/api/documents/d/original#page=40')
})
it('explains when a selected index must be rebuilt', async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({detail:'Build current indexes for every selected document before searching.'},{status:409})))
  render(<RetrievalComparison documents={[{id:'d',filename:'DP.pdf',page_count:157}]} />)
  fireEvent.click(screen.getByText('Compare search methods'))
  fireEvent.click(screen.getByLabelText('DP.pdf'))
  fireEvent.change(screen.getByLabelText('Comparison question'),{target:{value:'DP'}})
  fireEvent.click(screen.getByText('Compare all three'))
  expect(await screen.findByRole('alert')).toHaveTextContent('Build current indexes')
})
