# Approaches to anonymising mail

## The task

Turn "Dear John Smith, I met Anne the other day" into "Dear [PER], I met
[PER] the other day". Every span of a class in the label set (PER, ORG, LOC,
DATE, EMAIL, PHONE, URL, ATTACHMENT) is replaced by a placeholder of its type.
Stage two, indexed placeholders ("[PER_1] ... [PER_1]"), needs coreference
and is only noted here.

Constraints: local models only, possibly fine-tuned, on one consumer GPU.
Whatever the model, its output must become character spans over the prepared
text, so one deterministic function renders the email and the same spans are
scored and pre-labelled in Label Studio. This relies on the planned strata
**harmonisers** (named, versioned post-processing between a model's raw output and canonical spans,
such as `merge-adjacent` and `tagged-text`) and an **evaluate stage** with an
anonymisation task that gives each failure mode its own metric. What happens
to each gold entity: missed, truncated, fragmented, mislabelled, shared. What
each predicted span does: spurious, spilled, merging, duplicate. Plus leaked
share, character recall and precision, and placeholder-count error per
document. The set of failure modes is open to additions as new ones show up.
Neither is shipped yet.

The failure that matters most is **fragmentation**: "Dear John Smith"
becoming "Dear [PER] [PER]", which reads as two people. A fragmented entity
is worse than a slightly wrong boundary, because it changes what the output
says.

## 1. BIO token tagger (current baseline)

**How it works.** `TextSpanTagger` fine-tunes an encoder for token
classification with one O tag plus B- and I- per class, over 512-token windows
with overlap. Offsets map spans to subwords and back;
`merge_windows` unions same-label spans that overlap across windows.

**Fragmentation.** Each token's tag is picked independently (argmax per
token in `decode_window`), so nothing stops "John" from getting B-PER and
"Smith" getting B-PER too, or a middle subword getting O. Both split one
entity into two spans. `decode_window` already tolerates an I- with no
preceding B- (it opens a span), so the remaining sources are a B- where an
I- should be, and a gap tagged O. `merge_windows` does not help: it merges
only same-label spans that overlap, and two fragments of one name touch but
do not overlap.

Fixes, roughly from cheapest to dearest:

- **Decoding repair.** A `merge-adjacent` harmoniser that merges same-label
  spans separated only by whitespace. It fixes "Dear [PER] [PER]" directly.
  The risk is merging genuinely separate entities in lists or signature
  blocks; the "merged spans" metric shows it.
- **Word-level labels.** Predict on the first subword of each word and let
  the word's other subwords inherit the tag. This removes the "label
  changes mid-word" class of error entirely.
- **CRF head or constrained Viterbi.** A CRF learns tag transitions.
  Constrained Viterbi over the existing softmax, with I-X allowed only after
  B-X or I-X, needs no retraining. Neither stops a confident B-PER B-PER,
  which still needs data or the merge step.
- **A better encoder.** The default encoder in `windows.py` is
  `distilbert-base-uncased`, and `project.toml` does not override it.
  Lowercasing throws away capitalisation, which is one of the strongest cues
  for names, so switching this is probably the cheapest real improvement. A
  cased encoder such as DeBERTa-v3-base, or a multilingual one (XLM-R,
  mDeBERTa-v3) if the mail is not all English, fits comfortably on one GPU.

**Output to spans.** Native. `merge-adjacent` is the only harmoniser needed.
**Cost.** Uses the existing labels. Training takes minutes to hours on one
GPU, and inference on a long email is a handful of windowed forward passes,
which takes milliseconds. **Risks.** No overlapping spans (a name inside an
EMAIL); fine if the outer span wins.
**Stage two.** A separate step: cluster the predicted spans by normalised
string, then add coreference.

## 2. Span classification (GLiNER, SpERT-style)

**How it works.** Enumerate candidate spans up to a maximum width, represent
each one (for example by its boundary token embeddings), and classify it as
one of the labels or none. GLiNER (Zaratiana et al.) does this with a
bidirectional encoder that also encodes the label names, so it can score
arbitrary labels zero-shot. It is small enough for a consumer GPU or even a
CPU, and it can be fine-tuned. Community PII checkpoints exist; check them
against this label set.

**Fragmentation.** The unit of prediction is the whole span, so "John
Smith" is one decision rather than two token decisions that must agree.
Fragmentation is still possible: if "John" and "Smith" each score above
threshold and "John Smith" does not, decoding keeps the pieces. But it is no
longer the default failure mode. Greedy non-overlapping decoding by score
(GLiNER's flat mode) also removes duplicates and overlaps.

**Output to spans.** GLiNER returns character offsets over its input, so
only a window rebase and the same overlap merge are needed. `merge-adjacent`
is still worth running as a safety net. **Cost.** Fine-tunes directly from start/end/label
spans; widths are capped, so inference stays fast. **Risks.** The maximum span width and maximum input
length are limited (check the checkpoint's config), so long emails need
chunking, and long entities such as ATTACHMENT filenames or URLs may exceed
the width. Zero-shot quality on DATE or ATTACHMENT should be measured,
not assumed. **Stage two.** As for the
tagger.

## 3. Generative extraction with a local LLM

A 7-8B instruction model (e.g. Qwen2.5-7B or Qwen3-8B, Llama 3.1 8B, Ministral
8B, Gemma 2 9B or its successors) runs on one consumer GPU at 4-bit
quantisation. LoRA or QLoRA fine-tuning of that size also fits on one 24 GB
card. Larger models need more memory or slower offloading.

**(a) Inline-tagged rewrite.** The model reproduces the text with tags, e.g.
`Dear <PER>John Smith</PER>, ...`, and a `tagged-text` harmoniser aligns the
output back to source offsets. Fragmentation is less likely than with BIO,
because the model writes a closing tag around a whole name, but it is not
impossible. The main risk is copy drift (normalised whitespace, fixed
typos, dropped quoted lines), which the aligner must report, not silently
misplace. Output is as long as input: seconds to tens of seconds per long
email.

**(b) JSON entity list.** The model emits `[{"text": "John Smith", "type":
"PER"}, ...]`, and a locator finds each string in the source. Output is short.
But repeated strings are ambiguous (which "Anne"?), a string may also occur
in a non-entity sense, and some emitted strings will not occur verbatim. The practical policy is to mask every occurrence,
which is the right bias for anonymisation, and to count unlocatable strings
as a quality metric.

**(c) Direct rewrite to the anonymised email.** Not recommended as the
primary output. Nothing verifies that only entities changed:
hallucinated edits and dropped content look like redactions, there are no
offsets to score or pre-label, and finding leaks means diffing, which is (a)
done badly. At most a comparison row.

For (a) and (b), **constrained decoding** (a JSON schema or grammar through
outlines, llama.cpp GBNF grammars, or the guided-decoding options in vLLM)
guarantees parseable output. It does not guarantee correct output. For (a) a
grammar cannot easily force faithful copying, so alignment remains the check.
**Fine-tuning** converts the existing span labels to the target format
mechanically. **Stage two** comes most naturally here: the model can be asked
to emit an entity id with each mention. The id still needs the same evaluation
as a dedicated coreference step.

## 4. Seq2seq span generation (T5 / Flan-T5)

An encoder-decoder model fine-tuned to emit either format (a) or format (b).
It is lighter than a decoder LLM (base or large sizes train easily on one GPU)
and shares its harmonisers. Its input length is limited too, and it offers little
over approach 2 for the effort. Worth one row in the grid only if the LLM rows look promising
but too slow.

## 5. Hybrid

- **Rules for pattern classes.** EMAIL, URL and most PHONE formats are
  better found by regex than learned. Rule spans take precedence for those
  classes.
- **Tagger or GLiNER for recall, LLM for repair.** A cheap model proposes
  spans. An LLM, constrained to answer about given spans only, confirms or
  rejects each one, fixes its boundaries, or merges neighbours. Offsets stay anchored to the source.
- **Presidio as a reference.** Microsoft Presidio combines pattern
  recognisers with an NER model (spaCy or transformers) and returns offsets.
  Off the shelf, with its types mapped to this label set, it is
  a reference row.

The cost is more moving parts, and each rule or combiner is itself a
harmoniser that has to be named and versioned.

Dropped: prompting a general LLM zero-shot as the final system without
fine-tuning or constraints. It is a useful first row within 3a or 3b, but not
a separate approach.

## Comparison

| Approach | Fragmentation risk | Output → spans | Training data | Compute / latency (long email) | Main risk |
|---|---|---|---|---|---|
| BIO tagger, as-is | High | native | existing spans | low / ms | split names, uncased encoder |
| BIO + merge-adjacent, word-level, Viterbi/CRF, cased encoder | Low-medium | native + `merge-adjacent` | existing spans | low / ms | over-merging lists |
| GLiNER, fine-tuned | Low | native (offsets) | existing spans; zero-shot possible | low / ms-s | span-width and length caps |
| LLM tagged rewrite (3a) | Low-medium | `tagged-text` | spans → tagged text | high / s-tens of s | copy drift, slow |
| LLM JSON list (3b) | Low | string locator | spans → JSON | medium / s | repeated or unlocatable strings |
| LLM direct rewrite (3c) | n/a | none reliable | — | high | unverifiable edits; comparison only |
| Seq2seq (T5) | Low-medium | as 3a/3b | spans → text | medium | little gain over GLiNER |
| Hybrid rules + model (+ LLM repair) | Low | per component | existing spans | low to medium | more parts to version |
| Presidio | Medium | native | none | low | label mismatch; reference only |

## Recommended order of experiments

Freeze one dataset version and one holdout first, and score every row with
the same evaluate tasks: entity F1, and the anonymisation task's per-failure
metrics (`fragmented` and `merging` above all, for the problem this project
has). Each row is a (model, harmoniser chain) pair, so gains
from post-processing and gains from the model are reported separately.

1. **Baseline as-is**, then the **same predictions + `merge-adjacent`**.
   This measures how much of the fragmentation is purely a decoding problem.
2. **Cased encoder** (DeBERTa-v3-base, or a multilingual one if needed) with
   word-level labels and constrained Viterbi, with and without
   `merge-adjacent`.
3. **Regex for EMAIL / PHONE / URL** layered over the best row so far.
   Presidio added once as a reference row.
4. **GLiNER** zero-shot, then fine-tuned on the frozen training split.
5. **Local LLM, 3b then 3a**, with constrained decoding: prompted first,
   then QLoRA fine-tuned, with the relevant harmoniser. 3c is included only
   if a comparison is wanted.
6. **Hybrid repair**: the best cheap model's spans reviewed by the best LLM
   row, if the gap between them justifies the latency.

Weight leak rate and placeholder-count error above F1: masking slightly too
much beats splitting or missing a name. Stage two (indexed placeholders) starts from
whichever row wins, as a separate entity-linking step over its spans.
