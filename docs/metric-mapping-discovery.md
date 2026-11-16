# Missing metric discovery

Financial refreshes normalize SEC Company Facts first. Coverage is measured against the latest filed duration-fact period, independently of revenue coverage. Missing base income, cash flow, and balance sheet measures trigger a bounded investigation using the existing Groq credential and model.

The latest 10-K/10-Q inline XBRL is a fallback for company extensions. The parser reads numeric facts, units, scale, duration/instant contexts and table-row labels; dimensional facts and unsupported formats are excluded. It does not infer numbers from prose, PDFs, or images. Immutable filing documents are cached. Original Company Facts remain unchanged; enriched inputs and filing HTML are saved separately.

Groq sees at most 100 candidate definitions and proposes at most six mappings in a bounded response. Numeric amounts are read and calculated by code, never accepted from the model. Source quotes must occur in the supplied definition. Automatic acceptance requires an exact permitted statement label, compatible units and context type, multiple reported periods, current-period coverage, and no known conflicting definition terms. Ambiguous proposals remain pending; structurally eligible proposals can be explicitly approved by the owner after reviewing the source. These checks limit errors; semantic equivalence is not mathematically provable.

Accepted mappings are fallback aliases scoped to one company. Existing standard tags keep priority. The normalizer recomputes historical observations and derived metrics, including free cash flow, using its existing duration and matching-period rules. Accepted definitions must retain the same fingerprint on future refreshes. Mappings never execute code or arbitrary formulas.

Registry revisions use immutable `snapshots` rows (`metric_mappings`); entries retain provider model, prompt version, source digest, source filing link, evidence, decision, and validation details. `mapping_facts` and `mapping_filing` retain the input evidence. No schema migration is required. Owner approval/disable decisions made during a refresh are preserved. Disable and approval queue a refresh; display changes after the worker processes it. Disabled mappings are not automatically reapproved with the same definition.

The Overview coverage section shows accepted, pending, and disabled entries. GET `/api/companies/{id}/metric-mappings` exposes the current registry through existing application authentication. POST `.../{mapping_id}/approve` requires a pending proposal with structural checks; DELETE `.../{mapping_id}` disables it. Earlier snapshot revisions retain audit history.

Completed investigations retry no more than weekly for the same metric and period. Failed requests retry after one hour. New reporting periods can be investigated immediately. Provider/network/malformed-output failures do not discard valid financial data. No new service or credential is required.

Limits: candidate search is bounded; only the latest filing is fetched; company extensions with only one usable source period remain pending; generic debt assembly and derived metrics remain deterministic rather than LLM-defined. Disappearing or changed definitions are not silently substituted. This feature does not guarantee every missing metric is recoverable.
