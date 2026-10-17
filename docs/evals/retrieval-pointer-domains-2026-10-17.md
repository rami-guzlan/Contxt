# Tentative pointers and domain constraints

October 17, 2026. This change reduces unrelated rule injection. It does not close the
remaining note precision, recall or answerability gaps, and is not a production-readiness claim.

## Behavior

A lean brief has already concluded that no note confidently answers the request. Its
near-match pointers are search suggestions. Previously, their filing locations activated
domain-wide constraints as though the request had reached those domains. They no longer do.
Explicit triggers, independently matched domains, named projects and qualified pointers
retain their existing behavior. Thresholds, model artifacts, null banks and gates are unchanged.

## Frozen comparison

Same 15 Brains, labels, 100 off-topic requests, BGE model and UTC clock as the previous
comparison. The private baseline is the frozen Haiku 5.5 enriched copy, not the original
unenriched copy. Every evaluation runs on a scratch copy; no real Brain is edited.

Needed-note recall, whole-note recall, reachable recall, precision, off-topic note
abstention, false nothing and labeled must-hold recall are unchanged on every Brain.

| Brain | Split | Off-topic requests carrying rules, before | After | Must-hold recall, before and after |
| --- | --- | --- | --- | --- |
| bistro | tuning | 26/100 | 11/100 | 5/5 |
| contractor | validation | 16/100 | 7/100 | 3/4 |
| dental | tuning | 43/100 | 9/100 | 10/10 |
| designer | sealed | 30/100 | 4/100 | 9/9 |
| foodbank | validation | 38/100 | 11/100 | 9/13 |
| lab | sealed | 28/100 | 6/100 | 6/6 |
| lawfirm | tuning | 35/100 | 6/100 | 8/8 |
| realtor | sealed | 24/100 | 10/100 | 12/12 |
| saas-support | validation | 11/100 | 2/100 | 8/10 |
| teacher | tuning | 45/100 | 13/100 | 10/10 |

The private Brain remains at 72/88 needed-note hits, 70/88 whole-note hits,
82/88 reachable hits, 106/158 delivered notes useful, 93/100 off-topic abstentions
and 2/63 false-empty briefs. It has no dedicated must-hold labels.

The original sealed sets have been evaluated in previous stages; they are regression
evidence here, not new untouched evidence. Scores on these small sets do not establish
performance on arbitrary Brains.

## Rejected alternatives

- Excluding all rule pointers, including qualified pointers, reduced noise further but
  failed both unchanged gates: one dental must-hold and one entrepreneur needed note
  disappeared. That change and its proposed behavior were discarded.
- Using the installed MiniLM pairwise scorer at logit zero caused many false-empty briefs.
- Calibrating that scorer against the unchanged null bank reduced off-topic delivery but
  worsened precision or false-empty rates. No reranker is added or enabled.
- Joint word/meaning calibration made some own-domain unanswerable requests worse.
- Giving source text equal weight beside generated hints reduced useful hits on some
  tuning Brains. No blend weights were swept to recover a favorable score.

These experiments used public tuning Brains. No private questions or labels were sent
to a model. The frozen enriched private data and both gate manifests remain unchanged.

## Remaining release requirements

The stricter existing brain-logic goals remain visible alongside the general-retrieval
plan: 90% needed-note recall, 80% whole-note precision, 95% correct nothing, at most 2%
false nothing, 95% must-hold recall and at most 2% must-hold decoys. The current system
does not meet all of them. Larger independent evaluation, answer-quality validation
and the 5,000-note latency target are also outstanding. Passing regression CI alone
does not turn these requirements green.

Local full-suite validation and merge status are recorded in the PR.
