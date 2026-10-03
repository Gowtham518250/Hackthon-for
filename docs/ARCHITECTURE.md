# DeepSearch Architecture

## Workflow
Register → Verify → Login → Upload → Extract/OCR → Chunk → Index → Hybrid Search → Rerank → Evidence Preview → Adapt to new corpus.

## Bounded scope
PDF, DOCX, XLSX, CSV, JPG and PNG in a representative local corpus.

## Search
BM25 provides lexical retrieval, embeddings provide semantic retrieval, and a reranker produces the final ranking. Each result preserves source location and evidence text.
