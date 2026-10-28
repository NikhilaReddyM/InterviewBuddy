import json
import unittest
from types import SimpleNamespace
from fastapi import HTTPException
from evaluate_retrieval import Dataset, Reference, measures
from retrieval import rank, tokens


def row(identifier, text, page, vector, doc='d'):
    return {'id':identifier,'text':text,'vector':json.dumps(vector),
            'metadata':json.dumps({'document_id':doc,'filename':doc+'.pdf','pages':[page],'review_status':'unreviewed'})}


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.rows=[row('a','memoization caching repeated recursive calls',1,[1,0]),
                   row('b','matrix chain multiplication chooses parenthesization',2,[0,1]),
                   row('c','memoization uses a cache for subproblems',1,[0.9,0.1])]
        self.model=SimpleNamespace(query=lambda text:[1,0])

    def test_keyword_no_match_and_identifiers(self):
        self.assertIn('mincosttickets',tokens('minCostTickets'))
        self.assertIn('tickets',tokens('minCostTickets'))
        result=rank(self.rows,'matrix multiplication','keyword')
        self.assertEqual(result['results'][0]['id'],'b')
        self.assertEqual(rank(self.rows,'nonexistenttoken','keyword')['results'],[])
        self.assertTrue(all(h['evidence_status']=='unverified' for h in result['results']))

    def test_fusion_scores_unique_chunks_and_page_grouping(self):
        result=rank(self.rows,'memoization','hybrid',self.model,top_k=5)
        self.assertEqual(len({h['id'] for h in result['results']}),len(result['results']))
        self.assertAlmostEqual(result['results'][0]['score'],2/61)
        grouped=rank(self.rows,'memoization','dense',self.model,group_pages=True)
        self.assertEqual(len(grouped['results']),2)
        self.assertEqual(grouped['results'][0]['metadata']['pages'],[1])
        with self.assertRaises(HTTPException):
            rank(self.rows,'!!!','keyword')

    def test_metrics_use_document_and_page_and_drafts_are_explicit(self):
        results=[{'metadata':{'document_id':'other','pages':[1]}}, {'metadata':{'document_id':'d','pages':[1]}}]
        score=measures(results,[Reference(document_id='d',page=1)])
        self.assertEqual(score['reciprocal_rank_at_5'],0.5)
        self.assertEqual(score['supporting_page_hit_at_5'],1)
        self.assertEqual(measures(results[:1],[Reference(document_id='d',page=1)])['supporting_page_hit_at_5'],0)
        from evaluate_retrieval import evaluate
        dataset=Dataset(name='draft',document_ids=['d'],questions=[{'id':'q','question':'memoization','split':'development','answerable':True,'expected_pages':[{'document_id':'d','page':1}]}])
        with self.assertRaisesRegex(ValueError,'require review'):
            evaluate(dataset)
