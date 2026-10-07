---
name: webinar-one-pager
description: Make a one-page HTML flyer for a Brightmill webinar, ready to save as a PDF.
triggers:
  - make a webinar flyer
  - webinar one pager
  - flyer for the webinar
aliases:
  - webinar flyer
  - one pager
artifacts:
  - html
loads:
  - brand/visuals
  - brand/voice
  - brand/style
quality_gates:
  - Brightmill colors
  - every claim sourced
  - title under ten words
scope: company
---
# /webinar-one-pager

Make a one-page HTML flyer for a Brightmill webinar, ready to save as PDF from a browser.

1. Collect the title, date and time (Eastern), guest name and role, three things attendees
   will learn, and the registration link. Ask for anything missing.
2. Write the copy in the house style. Title in sentence case, under ten words.
3. Save the details as `webinar.json` in the run folder with the keys `title`, `date`,
   `time`, `guest`, `guest_role`, `points` (a list of three) and `link`.
4. Run `python skill/make_one_pager.py webinar.json` to build `one-pager.html`.
5. Check the page: Brightmill colors, no stock imagery, every claim sourced.
6. Save the result. It is a draft until Morgan approves it.
