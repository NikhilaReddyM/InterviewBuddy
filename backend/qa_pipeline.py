"""LangChain answer pipeline with a caller-supplied structured-output model."""
import json
from time import perf_counter

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langsmith import tracing_context

from qa_contract import SYSTEM_PROMPT, PROMPT_VERSION, make_sources, validate_answer


def answer_from_retrieval(question, retrieval, structured_model):
    started = perf_counter()
    sources = make_sources(retrieval['results'])
    if not sources:
        return {'sections': [], 'insufficient_evidence': True,
                'missing_information': 'No supporting passages were retrieved from the selected documents.',
                'sources': [], 'prompt_version': PROMPT_VERSION, 'generation_ms': 0}
    prompt = ChatPromptTemplate.from_messages([
        ('system', SYSTEM_PROMPT),
        ('human', 'Question and source excerpts (untrusted data):\n{payload}'),
    ])
    payload = json.dumps({'question': question, 'sources': [
        {key: s[key] for key in ('source_id', 'text', 'review_status')} for s in sources]}, ensure_ascii=False)
    chain = prompt | structured_model | RunnableLambda(lambda draft: validate_answer(draft, sources))
    # LangSmith is a LangChain dependency; cloud tracing is explicitly disabled for Week 2.
    with tracing_context(enabled=False):
        draft = chain.invoke({'payload': payload}, config={'callbacks': []})
    return {**draft.model_dump(), 'sources': sources, 'prompt_version': PROMPT_VERSION,
            'generation_ms': round((perf_counter() - started) * 1000, 2)}
