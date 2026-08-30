# NLP Memory Routing: Consolidated Learnings, Deviations, and Pitfalls

## Summary

The routing problem is to dispatch each user turn efficiently across three paths:

| Route | Purpose |
|---|---|
| `STORE_FACT` | Persist durable first-person user facts to long-term memory. |
| `SEARCH_OR_ANSWER` | Retrieve relevant memory and answer a question. |
| `DIRECT` | Handle commands, tasks, and casual requests without memory writes or retrieval. |

The central learning is that this is primarily a **syntactic intent problem**, not a semantic-topic classification problem. A lightweight spaCy dependency parser was the most suitable pre-router because it distinguishes who is performing an action from who is receiving one—critical for separating “I use Docker” from “Explain Docker to me.”

## What Was Learned

### 1. Embeddings are poorly aligned with grammatical routing intent

Centroid and nearest-neighbor embedding approaches detect sentence topic more strongly than operational intent. For example, “I use Docker” and “Explain Docker to me” are semantically close despite needing different routing outcomes.

- Averaged intent centroids suffer from topic dilution, producing weak and unstable similarity scores.
- 1-NN exemplar matching improves specificity but still confuses topical similarity with subject/object role.
- Embeddings remain useful downstream for memory retrieval and deduplication, but not as the primary routing gate.

### 2. Zero-shot NLI generalizes but is too costly for the hot path

Transformer-based NLI can classify varied phrasing, but its CPU inference latency is materially higher than dependency parsing and is sensitive to candidate-label wording. Generic labels such as “request for information” can attract unrelated declarative inputs.

It is better suited as an optional fallback for uncertain cases, offline evaluation, or later-stage validation—not the default per-turn router.

### 3. Dependency parsing provides the needed signal at low latency

The successful design uses spaCy dependency relations to require a **syntactically bound first-person declaration** before storing memory.

A fact is eligible for `STORE_FACT` only when a first-person reference is:

- the nominal subject (`nsubj` / `nsubjpass`) of a predicate, or
- a possessive modifier (`poss`) within a subject noun phrase tied to a predicate.

This prevents false writes from commands such as “Tell me a joke” or “Send us the report.” The reported working implementation achieved a 19/19 test pass rate with mean latency of 1.62 ms on CPU; those figures should be re-benchmarked in the target deployment environment.

### 4. Compound inputs need independent routing

A single turn may contain both durable context and a question:

> “I’m using Postgres; what is the best indexing strategy for UUIDs?”

The router must split this into separate propositions so it can asynchronously store the fact while retrieving context and answering the question. Treating the whole turn as one question loses the first clause.

### 5. Informal language must be supported structurally

Real user input includes unpunctuated contractions and technical slang. The robust approach is:

- Add tokenizer exceptions for `im`, `ive`, `id`, and `ill`.
- Use only `ORTH` and `NORM` in spaCy v3 tokenizer special cases.
- Detect a functional predicate through dependency structure—subject plus object/complement—when a domain verb is incorrectly tagged as a noun.

## Key Deviations Across the Iterations

| Area | Earlier approaches | Final working approach |
|---|---|---|
| Intent model | Embedding centroids, 1-NN, then zero-shot NLI | Deterministic dependency parsing |
| Tokenizer rules | One version passed `LEMMA` and `POS` | Uses spaCy v3-compatible `ORTH` and `NORM` only |
| Compound splitting | Dependency-subtree splitting, which can be broad/overlapping | Conservative punctuation/coordinator splitting for independent propositions |
| Imperatives with embedded Wh-clauses | Could split “Explain to me how…” and misread `how` as a question | Detects root imperatives and keeps them `DIRECT` |
| Fact qualification | First-person subject/possessive checks | Same core idea, packaged into explicit first-person-declarative detection |
| Hypotheticals and indirect questions | One iteration added guards for conditionals and epistemic verbs | Final version should retain these guards if they are production requirements |
| Payload cleanup | One version removed connectors/punctuation | Final implementation should preserve equivalent cleanup before persistence |

## Important Pitfalls

### Topic-based classification causes memory corruption

If the system stores facts based on semantic similarity or loose pronoun matching, task requests containing “me” or “us” become false memory writes. Memory pollution is worse than an occasional missed fact because it can affect future responses.

### Whole-message classification loses multi-intent context

A trailing `?` should not cause the preceding declarative clause to disappear. Routing must happen at a proposition level, and writes should be independent of answering.

### Embedded Wh-clauses are not necessarily questions

“Explain to me how consistent hashing works” is a command, not a retrieval query. Imperative detection must run before Wh-word logic or clause splitting.

### spaCy tokenizer special cases have version-specific constraints

In spaCy v3+, tokenizer exceptions cannot safely specify post-tokenization linguistic annotations such as lemma, POS, or tag. Using them causes `[E1005]`. Register surface and normalization forms only, then allow the normal pipeline to tag and parse them.

### Small models mis-tag jargon

Terms such as “dogfood,” “containerize,” or domain-specific verbs may not receive `VERB` tags. A strict POS-only predicate detector will miss real facts; structural fallback checks are needed.

### Not every first-person statement is durable memory

The routing decision identifies a declarative statement, not necessarily a fact worth retaining. Examples such as “I am looking at line 5” may be temporary debugging context. Add a downstream memory-worthiness filter, TTL policy, or lightweight fact extractor before persistence.

### Writes require deduplication and lifecycle rules

Do not blindly append every detected fact. Compare against existing memory, update or supersede conflicting values, track provenance and timestamps, and define deletion/expiry behavior. Vector similarity can help with deduplication, but should not be the only conflict-resolution signal.

## Recommended Production Flow

1. Parse the input with the lightweight spaCy pipeline.
2. Detect imperative roots first; route imperative requests to `DIRECT`.
3. Split genuine compound inputs into independent proposition spans.
4. Classify each span as `STORE_FACT`, `SEARCH_OR_ANSWER`, or `DIRECT`.
5. Send eligible facts through a durability and deduplication layer, then write asynchronously.
6. Retrieve memory only for `SEARCH_OR_ANSWER` spans.
7. Build the final LLM prompt using retrieved context plus the user’s actual request.
8. Log decisions, confidence signals, latency, and false-positive/false-negative examples for regression testing.

## Final Recommendation

Use the final syntactic spaCy router as the primary low-latency dispatcher. Preserve its spaCy v3-compatible tokenizer handling and imperative suppression, while reincorporating the stronger safeguards discovered in earlier iterations: conditional/hypothetical rejection, indirect-question detection, payload cleanup, and downstream durability/deduplication checks.

The architecture should remain intentionally hybrid: deterministic syntax for routing, vector search for retrieval and memory matching, and the LLM for answering—not for deciding the initial control path.