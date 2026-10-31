import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { AskDocuments } from './AskDocuments'
afterEach(()=>vi.unstubAllGlobals())
const config={provider:'Groq',model:'openai/gpt-oss-120b',configured:true,documents:[{filename:'Dynamic Programming.pdf'}],corpus_error:null}
const source={source_id:'S1',filename:'Dynamic Programming.pdf',pages:[131],review_status:'unreviewed',text:'Memoization stores computed results.',url:'/api/documents/doc/original#page=131'}
it('displays cited sections, unreviewed labels, and expands source links',async()=>{
 const result={question:'Explain memoization',sections:[{title:'Memoization',text:'Computed results are stored.',citations:[{source_id:'S1',quote:source.text}]}],
  insufficient_evidence:false,missing_information:'',sources:[source],elapsed_ms:1200,provider:'Groq',model:config.model}
 const fetcher=vi.fn().mockResolvedValueOnce(Response.json(config)).mockResolvedValueOnce(Response.json(result))
 vi.stubGlobal('fetch',fetcher)
 render(<AskDocuments />)
 fireEvent.click(screen.getByRole('button',{name:'Ask my PDFs'}))
 await waitFor(()=>expect(screen.queryByText('Checking Q&A setup…')).not.toBeInTheDocument())
 fireEvent.change(screen.getByLabelText('Your question'),{target:{value:'Explain memoization'}})
 fireEvent.click(screen.getByText('Ask with citations'))
 await screen.findByText('Computed results are stored.')
 expect(screen.getByText(/Some retrieved text has not been reviewed/)).toBeInTheDocument()
 fireEvent.click(screen.getByRole('link',{name:'[S1] Dynamic Programming.pdf, p. 131'}))
 expect(screen.getByText('Retrieved sources (1)').parentElement).toHaveAttribute('open')
 expect(screen.getByText('Open original PDF page')).toHaveAttribute('href',source.url)
 expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({question:'Explain memoization'})
})
it('keeps missing evidence distinct from provider failure',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(Response.json(config)).mockResolvedValueOnce(Response.json({
  question:'Interview date?',sections:[],insufficient_evidence:true,missing_information:'The excerpts do not include an interview date.',sources:[],elapsed_ms:50,provider:'Groq',model:config.model})))
 render(<AskDocuments />)
 fireEvent.click(screen.getByRole('button',{name:'Ask my PDFs'}))
 await waitFor(()=>expect(screen.queryByText('Checking Q&A setup…')).not.toBeInTheDocument())
 fireEvent.change(screen.getByLabelText('Your question'),{target:{value:'Interview date?'}})
 fireEvent.click(screen.getByText('Ask with citations'))
 expect(await screen.findByText('Not enough evidence')).toBeInTheDocument()
 expect(screen.getByText('The excerpts do not include an interview date.')).toBeInTheDocument()
})
it('prevents requests without a configured model and key',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(Response.json({...config,configured:false,model:null})))
 render(<AskDocuments />)
 fireEvent.click(screen.getByRole('button',{name:'Ask my PDFs'}))
 await screen.findByText('Q&A setup')
 expect(screen.getByText('Ask with citations')).toBeDisabled()
 expect(screen.getByText(/add your Groq API key/)).toBeInTheDocument()
})
it('shows validation failures without rendering an answer',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(Response.json(config)).mockResolvedValueOnce(Response.json({detail:'The model response failed citation validation.'},{status:502})))
 render(<AskDocuments />)
 fireEvent.click(screen.getByRole('button',{name:'Ask my PDFs'}))
 await waitFor(()=>expect(screen.queryByText('Checking Q&A setup…')).not.toBeInTheDocument())
 fireEvent.change(screen.getByLabelText('Your question'),{target:{value:'Explain DP'}})
 fireEvent.click(screen.getByText('Ask with citations'))
 expect(await screen.findByRole('alert')).toHaveTextContent('failed citation validation')
 expect(screen.queryByRole('article',{name:'Cited answer'})).not.toBeInTheDocument()
})
