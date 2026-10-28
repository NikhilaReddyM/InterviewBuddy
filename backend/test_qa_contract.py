import unittest
from qa_contract import make_sources, validate_answer


class CitationTests(unittest.TestCase):
    def setUp(self):
        self.sources=make_sources([{'id':'chunk','text':'Memoization stores previously computed subproblem results.',
            'metadata':{'document_id':'doc','filename':'DP.pdf','pages':[131],'review_status':'unreviewed'}}])
        self.answer={'sections':[{'title':'Memoization','text':'Previously computed results are stored.',
            'citations':[{'source_id':'S1','quote':'Memoization stores previously computed subproblem results.'}]}],
            'insufficient_evidence':False,'missing_information':''}

    def test_sources_and_valid_answer(self):
        parsed=validate_answer(self.answer,self.sources)
        self.assertEqual(parsed.sections[0].citations[0].source_id,'S1')
        self.assertEqual(self.sources[0]['url'],'/api/documents/doc/original#page=131')
        self.assertEqual(self.sources[0]['review_status'],'unreviewed')

    def test_unknown_ids_and_fabricated_quotes_rejected(self):
        for bad in [{'source_id':'S99','quote':'Memoization stores previously computed subproblem results.'},
                    {'source_id':'S1','quote':'A fabricated recurrence formula.'}]:
            self.answer['sections'][0]['citations']=[bad]
            with self.assertRaises(ValueError):
                validate_answer(self.answer,self.sources)

    def test_uncited_sections_and_empty_success_rejected(self):
        self.answer['sections'][0]['citations']=[]
        with self.assertRaises(ValueError): validate_answer(self.answer,self.sources)
        self.answer['sections']=[]
        with self.assertRaises(ValueError): validate_answer(self.answer,self.sources)

    def test_missing_evidence_and_partial_answer(self):
        answer={'sections':[],'insufficient_evidence':True,'missing_information':'The excerpts do not contain an interview date.'}
        self.assertTrue(validate_answer(answer,self.sources).insufficient_evidence)
        self.answer.update(insufficient_evidence=True,missing_information='Runtime analysis is not provided.')
        self.assertTrue(validate_answer(self.answer,self.sources).insufficient_evidence)
        self.answer['missing_information']=''
        with self.assertRaises(ValueError): validate_answer(self.answer,self.sources)

    def test_langchain_pipeline_preserves_source_data_and_validates_model_output(self):
        from langchain_core.runnables import RunnableLambda
        from qa_pipeline import answer_from_retrieval
        received=[]
        def generate(prompt):
            received.append(prompt.to_messages())
            return self.answer
        result=answer_from_retrieval('Explain memoization', {'results':[{'id':'chunk',
            'text':self.sources[0]['text'],'metadata':{'document_id':'doc','filename':'DP.pdf',
            'pages':[131],'review_status':'unreviewed'}}]}, RunnableLambda(generate))
        self.assertFalse(result['insufficient_evidence'])
        self.assertIn('Explain memoization',received[0][1].content)
        self.assertEqual(result['sources'][0]['pages'],[131])

    def test_empty_retrieval_does_not_call_a_model(self):
        from langchain_core.runnables import RunnableLambda
        from qa_pipeline import answer_from_retrieval
        def unexpected(_): raise AssertionError('No model call expected')
        result=answer_from_retrieval('Unknown', {'results':[]},RunnableLambda(unexpected))
        self.assertTrue(result['insufficient_evidence'])
        self.assertEqual(result['sources'],[])
