# Earnings-call thesis comparison

Each requested Groq comparison now attempts to retrieve the matching earnings call through Alpha Vantage in addition to reviewing the SEC filing. Fiscal year and quarter come from the filing's inline XBRL focus fields, not calendar months. An annual FY report maps to Q4. Missing or ambiguous focus fields skip transcript retrieval; no older call is silently substituted.

Successful transcripts are cached for 24 hours, with failures retried after an hour. HTTP reads are bounded to 4 MB, redirects disabled and errors redact provider response details. Raw speaker turns are snapshotted independently of the filing when analysis is saved. No new database migration or API key is required beyond the existing Alpha Vantage key.

Transcript retrieval ranks complete sentence units within individual speaker turns against the saved thesis. At most 8,000 characters are passed to Groq. The model classifies every selected unit against an exact thesis claim, or returns null. Quotes and speakers are attached from the source using exact passage equality. Questions remain attributed to analysts; they are not treated as management admissions. Broad budget optimism must not be linked to a valuation claim without valuation-specific content.

The app displays filing passages and call passages separately. All related call excerpts, speaker titles and thesis links can be expanded in the app. Missing access, unavailable transcripts and call-model errors are shown without discarding a successful filing analysis.

## Live check, November 17, 2026

- Used the existing saved CACI thesis, version 1, without modifying it.
- Latest filing declares fiscal 2027 Q1; Alpha Vantage returned an empty transcript for that quarter. The application must show unavailable for that period.
- An available real fiscal 2026 Q3 transcript contained 67 speaker turns. Selection supplied 42 passages; Groq classified all 42, returning 39 related passages after tightening the prompt.
- Four selected checks were found: optical communications, ARKA imaging/AI, accelerating counter-drone demand, and capital allocation. All returned source and thesis quotations matched exactly and retained the correct speaker.
- Initial prompt produced broad links to a higher-valuation thesis sentence. An added instruction requiring explicit valuation content removed those links in the next run.

This was a small, exploratory check with selected source anchors, not a blind recall/precision benchmark. It checks topic relevance and provenance, not whether management's claims are true or whether the stock should be bought. Lexical retrieval can miss synonyms or topics outside the input budget.

To repeat with another watched company that has a saved thesis:

```sh
PYTHONPATH=backend .venv/bin/python scripts/evaluate_transcript.py \
  --ticker CACI --quarter 2026Q3 --output work/call-eval.json
```

The command uses provider calls and the shared feed cache but does not save a thesis revision or application analysis.
