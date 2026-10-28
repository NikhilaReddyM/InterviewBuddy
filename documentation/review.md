# Phase 1 findings — 2026-10-28

Completed local PDFKit inventory and Apple Vision OCR of nine sample pages; visually compared each rendered page with OCR output. This is a qualitative sample assessment, not an accuracy benchmark for all pages. No hosted extraction or model API was used. Vision failed under sandbox restrictions but succeeded with local system access.

## Inventory

7 PDFs, 378 PDF pages. PDFKit found fewer than 80 characters after trimming leading/trailing whitespace on 281 pages. Earlier pypdf counts differed because extraction engines and modes differ. This heuristic flags review candidates, not confirmed scans. One DOCX is intentionally excluded.

| PDF | Pages | Low-text pages |
|---|---:|---:|
| Array Floater- Sliding Windows II | 20 | 18 |
| Arrays Prefix Sum | 54 | 52 |
| Binary search variants - 1 | 59 | 29 |
| Dynamic Programming Part 9 | 30 | 29 |
| Dynamic Programming Series Part 10 Slides | 22 | 22 |
| Dynamic Programming | 157 | 96 |
| Sliding Windows 1 | 36 | 35 |

## Visual comparison

Direct/OCR counts below include whitespace; inventory low-text counts trim leading/trailing whitespace.

| PDF / page | Direct / OCR characters | Content | Finding and decision |
|---|---:|---|---|
| Binary search / 8 | 30 / 707 | Printed problem with array annotation | OCR recovers statement, but exponent formatting and closing bracket are corrupted. Review constraints; preserve image for annotations. |
| Binary search / 25 | 194 / 204 | Handwritten pseudocode | Existing text is also corrupted and out of order. OCR misreads <=, return, else, and 1. Neither version is safe as code. Require reviewed transcription. |
| Binary search / 45 | 0 / 352 | Python code screenshot | OCR flattens indentation, groups line numbers separately, reads reader.get as reader-get, and alters return annotation. Require reviewed transcription; do not execute OCR output. |
| Dynamic Programming / 10 | 304 / 2213 | Historical illustration with printed quotation | OCR generates extensive noise from decorative historical text. Prefer existing text; exclude illustration OCR from coding index. More characters is not better. |
| Dynamic Programming / 40 | 0 / 635 | Printed problem and examples | Broad meaning recovered, but 0 becomes O, cost[1] becomes cost[1l, and array closing bracket becomes 1. OCR with review before accepting exact examples. |
| Dynamic Programming / 80 | 1176 / 1179 | Typed conceptual explanation | Direct extraction is readable and retains content; OCR introduces I/1 and 0/O errors. Prefer direct text. |
| Sliding Windows / 5 | 0 / 340 | Handwritten algorithm and annotations | q becomes 9; subtraction assignment and reading order are wrong; fraction structure lost. Needs reviewed transcription and layout interpretation. |
| Sliding Windows / 15 | 0 / 1134 | Printed problem with handwritten windows | Printed rules mostly recovered, but brackets/indexes are wrong and window relationships are not represented. Review formulas and describe diagram separately. |
| Sliding Windows / 25 | 0 / 0 | Blank dark slide | Visually confirmed blank. Skip; do not misclassify as OCR failure. |

## Extraction decision

Use a hybrid extraction approach in a future ingestion phase:

1. Prefer verified direct text for ordinary typed explanations.
2. Use local OCR for screenshot pages, retaining the page image and source page number.
3. Require reviewed text for code, handwritten pseudocode, formulas, and constraints. Neither direct text nor OCR is trustworthy merely because it is nonempty.
4. Handle diagrams through explicit descriptions or a separately evaluated vision workflow; OCR alone only reads labels.
5. Exclude blank pages and decorative-image noise.
6. Keep extraction method and review status with every page. Do not index unreviewed code as authoritative solutions.

## Status

Phase 1 is complete as a feasibility assessment. Automatic extraction of the entire collection is not validated. Local OCR is useful but insufficient for unattended coding-solution ingestion. No Phase 2 application integration has been added.
