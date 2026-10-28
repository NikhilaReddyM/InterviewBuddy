"""Shared Phase 4 ranking for UI search and reproducible evaluations."""
import json
import re
from time import perf_counter

import numpy as np
from rank_bm25 import BM25Plus
from fastapi import HTTPException

SETTINGS = {'version': 'retrieval-v1', 'candidates_per_method': 10, 'rrf_k': 60,
            'bm25': 'BM25Plus', 'k1': 1.5, 'b': 0.75, 'delta': 1.0,
            'tokenizer': 'identifiers-and-words-v1'}


def tokens(text):
    # Keep full identifiers and add camelCase/underscore components.
    words = re.findall(r'[A-Za-z_][A-Za-z_0-9]*|\d+', text)
    result = []
    for word in words:
        result.append(word.lower())
        parts = re.findall(r'[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+', word)
        if len(parts) > 1:
            result.extend(part.lower() for part in parts)
    return result


def rank(rows, query, method, model=None, top_k=5, group_pages=False):
    started = perf_counter()
    if method not in ('dense', 'keyword', 'hybrid'):
        raise HTTPException(422, 'Choose dense, keyword, or hybrid retrieval.')
    query_tokens = tokens(query)
    if not query.strip() or not query_tokens:
        raise HTTPException(422, 'Enter a question containing words or identifiers.')
    if not rows:
        return {'results': [], 'method': method, 'elapsed_ms': 0, 'evidence_status': 'unverified', 'settings': SETTINGS}
    lexical = [tokens(row['text']) for row in rows]
    keyword_ranks, dense_ranks = [], []
    if method in ('keyword', 'hybrid'):
        nonempty = [terms or ['__empty_document__'] for terms in lexical]
        scores = BM25Plus(nonempty, k1=SETTINGS['k1'], b=SETTINGS['b'], delta=SETTINGS['delta']).get_scores(query_tokens)
        # BM25Plus includes a baseline; never return chunks with zero term overlap.
        keyword_ranks = sorted((i for i in range(len(rows)) if set(query_tokens).intersection(lexical[i])),
                               key=lambda i: (-float(scores[i]), rows[i]['id']))
        keyword_scores = {i: float(scores[i]) for i in keyword_ranks}
    if method in ('dense', 'hybrid'):
        vector = np.asarray(model.query(query), dtype=float)
        matrix = np.asarray([json.loads(row['vector']) for row in rows], dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] != len(vector) or not np.isfinite(matrix).all() or not np.isfinite(vector).all():
            raise HTTPException(409, 'Invalid vector data; rebuild the selected indexes.')
        norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(vector)
        if np.any(norms == 0):
            raise HTTPException(409, 'Invalid zero vector; rebuild the selected indexes.')
        similarities = matrix @ vector / norms
        dense_ranks = sorted(range(len(rows)), key=lambda i: (-float(similarities[i]), rows[i]['id']))
        dense_scores = {i: float(similarities[i]) for i in dense_ranks}
    if method == 'hybrid':
        scores = {}
        for ranking in (dense_ranks, keyword_ranks):
            for position, i in enumerate(ranking[:SETTINGS['candidates_per_method']], 1):
                scores[i] = scores.get(i, 0) + 1 / (SETTINGS['rrf_k'] + position)
        ranking = sorted(scores, key=lambda i: (-scores[i], rows[i]['id']))
        score_type = 'reciprocal_rank_fusion'
    elif method == 'dense':
        scores, ranking, score_type = dense_scores, dense_ranks, 'cosine_similarity'
    else:
        scores, ranking, score_type = keyword_scores, keyword_ranks, 'bm25_plus'
    dense_positions = {i: n for n, i in enumerate(dense_ranks, 1)}
    keyword_positions = {i: n for n, i in enumerate(keyword_ranks, 1)}
    results, seen = [], set()
    for i in ranking:
        row = rows[i]
        metadata = json.loads(row['metadata'])
        key = (metadata['document_id'], tuple(metadata['pages'])) if group_pages else row['id']
        if key in seen:
            continue
        seen.add(key)
        results.append({'id': row['id'], 'text': row['text'], 'metadata': metadata,
                        'score': float(scores[i]), 'score_type': score_type,
                        'dense_rank': dense_positions.get(i), 'keyword_rank': keyword_positions.get(i),
                        'evidence_status': 'unverified'})
        if len(results) >= top_k:
            break
    return {'results': results, 'method': method, 'elapsed_ms': round((perf_counter() - started) * 1000, 2),
            'evidence_status': 'unverified', 'settings': SETTINGS,
            'message': 'Inspect the source pages: ranking does not establish that the question can be answered.'}
