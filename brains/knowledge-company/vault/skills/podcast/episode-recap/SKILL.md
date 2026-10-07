---
name: episode-recap
description: Turn a Floor Notes transcript into show notes, three LinkedIn posts and a newsletter blurb.
triggers:
  - recap this episode
  - repurpose the podcast
  - show notes for
aliases:
  - episode recap
  - show notes
artifacts: []
loads:
  - marketing/podcast
  - brand/voice
  - brand/style
quality_gates:
  - quotes only from the transcript
  - three posts, one per segment
scope: company
---
# /episode-recap

Turn a Floor Notes transcript into the episode's promotion set.

1. Read the transcript and find the guest's best story under each segment: The Problem, What
   We Tried, What Stuck.
2. Write show notes: a two-sentence summary, three takeaways, and timestamps if the
   transcript has them.
3. Write three LinkedIn posts with /linkedin-post, one per segment.
4. Write a newsletter blurb of about 80 words for The Line Brief.
5. Quote the guest only with words from the transcript. Mark anything you paraphrase.
6. Return everything as drafts for Morgan's approval.
