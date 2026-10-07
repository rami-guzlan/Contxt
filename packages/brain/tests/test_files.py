"""Files your AI can read: documents filed with their shape, quoted by the part a request is
about, filed into projects at once with versions, and one writer at a time across processes.

The bakery brain (test_layout) gets a project, "Spring launch proposals", and a proposal in
two versions. Its tests follow the plan: the LinkedIn part of the proposal reaches a request
about it, quoted with its version; a question about the podcast budget reaches that part; a
writing task that merely shares a word does not get the proposal quoted; a new version
replaces the text in place and its card says which version it is; undo puts it back.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, ROOT)

from brainkit import frontmatter as fm  # noqa: E402
from brainkit import importers, sections, uploads, util  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from brainkit.locking import Busy, WriteLock  # noqa: E402
from tests import fixture, test_layout  # noqa: E402

PROPOSAL_V2 = """# Spring launch proposal

## Goals

Grow pre-orders of sourdough loaves for the spring menu by 30 percent and sign two cafe
wholesale partners.

## LinkedIn video

Three short videos of the bakers at work, posted on Tuesdays. Budget: 600 dollars for
boosting the best one.

## Podcast sponsorship

Sponsor two episodes of the Local Eats podcast. Budget: 900 dollars.

## Timeline

March: film the videos. April: the podcast spots air. May: review the results with Ana.
"""

PROPOSAL_V3 = PROPOSAL_V2.replace("600 dollars", "800 dollars").replace(
    "Sponsor two episodes of the Local Eats podcast. Budget: 900 dollars.",
    "Cut: the podcast budget moves to the LinkedIn videos.")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def make_docx(path, blocks):
    """blocks: [(style id or None or "list", text)] or ("table", rows)."""
    body = []
    for kind, value in blocks:
        if kind == "table":
            rows = "".join("<w:tr>" + "".join(
                f"<w:tc><w:p><w:r><w:t>{escape(cell)}</w:t></w:r></w:p></w:tc>" for cell in row)
                + "</w:tr>" for row in value)
            body.append(f"<w:tbl>{rows}</w:tbl>")
            continue
        props = ""
        if kind == "list":
            props = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
        elif kind:
            props = f'<w:pPr><w:pStyle w:val="{kind}"/></w:pPr>'
        body.append(f"<w:p>{props}<w:r><w:t>{escape(value)}</w:t></w:r></w:p>")
    document = (f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W_NS}">'
                f'<w:body>{"".join(body)}</w:body></w:document>')
    styles = (f'<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="{W_NS}">'
              '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>'
              '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
              '</w:style><w:style w:type="paragraph" w:styleId="Kop2"><w:name w:val="heading 2"/>'
              "</w:style></w:styles>")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)


def _shape(kind, lines):
    ph = f'<p:ph type="{kind}"/>' if kind and kind != "body" else '<p:ph idx="1"/>'
    paragraphs = "".join(f"<a:p><a:r><a:t>{escape(line)}</a:t></a:r></a:p>" for line in lines)
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="1" name="s"/><p:cNvSpPr/><p:nvPr>{ph}</p:nvPr>'
            f"</p:nvSpPr><p:txBody>{paragraphs}</p:txBody></p:sp>")


def make_pptx(path, slides, order):
    """slides: {number: (title, [lines], notes or None)}; order: slide numbers as shown."""
    with zipfile.ZipFile(path, "w") as archive:
        ids = "".join(f'<p:sldId id="{255 + n}" r:id="rId{n}"/>' for n in order)
        archive.writestr("ppt/presentation.xml",
                         f'<p:presentation xmlns:p="{P_NS}" xmlns:r="{R_NS}">'
                         f"<p:sldIdLst>{ids}</p:sldIdLst></p:presentation>")
        rels = "".join(f'<Relationship Id="rId{n}" Type="{R_NS}/slide" '
                       f'Target="slides/slide{n}.xml"/>' for n in slides)
        archive.writestr("ppt/_rels/presentation.xml.rels",
                         f'<Relationships xmlns="{PKG_NS}">{rels}</Relationships>')
        for number, (title, lines, notes) in slides.items():
            shapes = _shape("title", [title]) + _shape("body", lines) + _shape("sldNum", ["9"])
            archive.writestr(f"ppt/slides/slide{number}.xml",
                             f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree>'
                             f"{shapes}</p:spTree></p:cSld></p:sld>")
            if notes:
                archive.writestr(
                    f"ppt/slides/_rels/slide{number}.xml.rels",
                    f'<Relationships xmlns="{PKG_NS}"><Relationship Id="rId1" '
                    f'Type="{R_NS}/notesSlide" Target="../notesSlides/notesSlide{number}.xml"/>'
                    "</Relationships>")
                archive.writestr(
                    f"ppt/notesSlides/notesSlide{number}.xml",
                    f'<p:notes xmlns:p="{P_NS}" xmlns:a="{A_NS}"><p:cSld><p:spTree>'
                    f'{_shape("sldImg", [])}{_shape("body", [notes])}</p:spTree></p:cSld>'
                    "</p:notes>")


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="brain-files-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_word_headings_lists_and_tables_keep_their_shape(self):
        path = os.path.join(self.tmp, "plan.docx")
        make_docx(path, [("Title", "Spring plan"), (None, "Why we are doing this."),
                         ("Heading1", "Budget"), ("list", "LinkedIn: 600"),
                         ("table", [["Channel", "Cost"], ["Podcast", "900"]]),
                         ("Kop2", "Podcast detail"), (None, "Two episodes.")])
        text = importers.to_markdown(path)
        self.assertIn("# Spring plan", text)
        self.assertIn("# Budget", text)
        self.assertIn("- LinkedIn: 600", text)
        self.assertIn("| Channel | Cost |", text)
        self.assertIn("| Podcast | 900 |", text)
        self.assertIn("## Podcast detail", text)  # a localized style id, named "heading 2"

    def test_slides_come_in_the_order_shown_with_titles_and_speaker_notes(self):
        path = os.path.join(self.tmp, "deck.pptx")
        make_pptx(path, {1: ("Agenda", ["Goals", "Budget"], None),
                         2: ("Budget overview", ["LinkedIn: 600", "Podcast: 900"],
                             "Say the budget can move.")}, order=[2, 1])
        text = importers.to_markdown(path)
        self.assertLess(text.index("## Slide 1: Budget overview"),
                        text.index("## Slide 2: Agenda"))
        self.assertIn("LinkedIn: 600\nPodcast: 900", text)
        self.assertIn("Speaker notes: Say the budget can move.", text)
        self.assertNotIn("9", text.replace("900", ""))  # the slide number placeholder

    def test_html_headings_and_list_items(self):
        path = os.path.join(self.tmp, "page.html")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("<h1>Rates</h1><p>Our rates.</p><h2>Day rate</h2><ul><li>900</li></ul>"
                         "<script>alert(1)</script>")
        text = importers.to_markdown(path)
        self.assertIn("# Rates", text)
        self.assertIn("## Day rate", text)
        self.assertIn("- 900", text)
        self.assertNotIn("alert", text)

    def test_a_meeting_transcript_reads_as_turns_with_who_spoke_and_when(self):
        # Teams writes WebVTT with a voice per cue; Zoom and SubRip put the name before a colon.
        vtt = os.path.join(self.tmp, "kickoff.vtt")
        with open(vtt, "w", encoding="utf-8") as handle:
            handle.write("WEBVTT\n\n1f4a\n00:00:01.000 --> 00:00:04.000\n<v Dana Ruiz>We keep the "
                         "videos.</v>\n\n00:00:04.500 --> 00:00:06.000\n<v Dana Ruiz>All three, "
                         "in October.</v>\n\n00:01:02.000 --> 00:01:05.000\n<v Sam Lee>And the "
                         "podcast?</v>\n")
        self.assertEqual(importers.to_markdown(vtt),
                         "**Dana Ruiz** [00:01] We keep the videos. All three, in October.\n\n"
                         "**Sam Lee** [01:02] And the podcast?")
        srt = os.path.join(self.tmp, "kickoff.srt")
        with open(srt, "w", encoding="utf-8") as handle:
            handle.write("1\n01:00:00,000 --> 01:00:02,000\nSam Lee: We drop it.\n\n2\n"
                         "01:00:03,000 --> 01:00:05,000\nA line nobody signed.\n")
        self.assertEqual(importers.to_markdown(srt),
                         "**Sam Lee** [1:00:00] We drop it.\n\n[1:00:03] A line nobody signed.")
        self.assertEqual(importers.extract(srt)[0], ("at 1:00:00", "Sam Lee: We drop it."))


class SectionTests(unittest.TestCase):
    def test_a_document_splits_at_its_headings_without_its_title_and_source_line(self):
        body = ("# Spring launch proposal\n\n> Source: `p.docx`, filed 2026-10-06.\n\n"
                + PROPOSAL_V2.split("\n", 1)[1])
        found = sections.split("references/p.md", body)
        self.assertEqual([s.heading for s in found],
                         ["Goals", "LinkedIn video", "Podcast sponsorship", "Timeline"])
        self.assertEqual(found[1].id, "references/p.md#2")
        self.assertNotIn("Source", " ".join(s.text for s in found))
        self.assertEqual(sections.outline(body),
                         ["Goals", "LinkedIn video", "Podcast sponsorship", "Timeline"])

    def test_headings_nest_and_a_long_section_is_cut_into_parts(self):
        long_text = "\n\n".join(f"Paragraph {n} " + "word " * 120 for n in range(6))
        body = f"# Guide\n\n## Budget\n\n### LinkedIn\n\nSmall.\n\n## Detail\n\n{long_text}\n"
        found = sections.split("references/g.md", body)
        self.assertEqual(found[0].heading, "Budget > LinkedIn")
        parts = [s for s in found if s.heading == "Detail"]
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(s.words <= sections.MAX_WORDS for s in parts))
        self.assertEqual(parts[0].label, f"Detail (part 1 of {len(parts)})")

    def test_text_without_headings_is_cut_by_paragraphs(self):
        body = "\n\n".join("Para " + "text " * 150 for _ in range(5))
        found = sections.split("references/plain.md", body)
        self.assertGreater(len(found), 1)
        self.assertTrue(found[0].label.startswith("Part 1 of"))

    def test_a_pasted_transcript_is_cut_at_its_sentences(self):
        # A short note on top, then one long paragraph with no breaks, as pasted transcripts are.
        talk = " ".join(f"We post video number {n} on Tuesday." for n in range(300))
        body = f"Machine-generated transcript, pasted as provided.\n\n---\n\n{talk}\n"
        found = sections.split("references/t.md", body)
        self.assertGreater(len(found), 3)
        self.assertTrue(all(s.words <= sections.MAX_WORDS for s in found))
        self.assertTrue(found[0].text.startswith("Machine-generated transcript"))
        self.assertIn("We post video number 0 on Tuesday.", found[0].text)  # not a header alone
        self.assertTrue(all(s.text.endswith("Tuesday.") for s in found))  # whole sentences
        runon = sections.split("references/r.md", "word " * 1500)
        self.assertEqual([s.words for s in runon], [320, 320, 320, 320, 220])

    def test_a_deck_outline_lists_its_slide_titles(self):
        body = "## Slide 1: Agenda\n\nx\n\n## Slide 2: Budget overview\n\ny\n\n## Slide 3\n\nz\n"
        self.assertEqual(sections.outline(body), ["Agenda", "Budget overview"])


class FileNameTests(unittest.TestCase):
    def test_copies_of_one_document_share_a_stem_and_say_their_version(self):
        for name in ("Campaign proposal v3 FINAL (2).docx", "campaign-proposal_v4.docx",
                     "Copy of Campaign Proposal.docx", "Campaign proposal 2026-10-03.pdf"):
            self.assertEqual(uploads.document_stem(name), "campaign proposal", name)
        self.assertNotEqual(uploads.document_stem("Media plan v2.docx"), "campaign proposal")
        self.assertEqual(uploads.version_in("Campaign proposal v3 FINAL.docx"), 3)
        self.assertIsNone(uploads.version_in("Campaign proposal.docx"))
        self.assertEqual(uploads.title_from_name("campaign-proposal_v4.docx"), "Campaign proposal")
        self.assertEqual(uploads.title_from_name("Planning call (2026-03-02).md"), "Planning call")


class ProjectFilesBase(unittest.TestCase):
    """The bakery brain with a project and its proposal, filed by Ana in the app."""

    def setUp(self):
        self.vault = test_layout.build()
        self.brain = Brain(self.vault, embeddings=False)
        made = self.brain.focus_create(
            "Spring launch proposals", "Proposals for the spring launch campaign.",
            principal="person:ana", aliases=["the spring proposals", "spring launch"])
        self.assertFalse(made.is_error, made.text)
        self.project = made.data["id"]
        self.filed = self.brain.add_file(content=PROPOSAL_V2,
                                         filename="Spring launch proposal v2.md",
                                         project="the spring proposals", status="sent",
                                         principal="person:ana", origin="app")
        self.assertEqual(self.filed.data.get("status"), "applied", self.filed.text)
        self.path = self.filed.data["path"]

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def ctx(self, request, **kwargs):
        kwargs.setdefault("record", False)
        return self.brain.context(request, principal="person:ana", **kwargs)

    def card(self):
        return self.brain.state().index.cards.get(self.path)


class FilingTests(ProjectFilesBase):
    def test_a_file_is_filed_at_once_in_its_project_with_a_card_that_says_which_copy(self):
        self.assertEqual(self.path,
                         "references/projects/spring-launch-proposals/spring-launch-proposal.md")
        data = self.filed.data
        self.assertEqual((data["version"], data["file_status"], data["sections"]), (2, "sent", 4))
        self.assertTrue(data["checkpoint"])
        self.assertIn("Spring launch proposals", self.filed.text)
        card = self.card()
        self.assertEqual(card.route_key, "projects/spring-launch-proposals")
        self.assertEqual(card.meta["type"], "file")
        self.assertEqual(card.meta["filename"], "Spring launch proposal v2.md")
        self.assertEqual(card.meta["dated"], util.today())
        self.assertIn("Sections: Goals; LinkedIn video; Podcast sponsorship; Timeline.", card.body)
        self.assertEqual(card.title, "Spring launch proposal")
        decision = util.read_jsonl(os.path.join(self.vault, "journal", "decisions.jsonl"))[-1]
        self.assertEqual(decision["action"], "auto-applied")
        self.assertFalse(os.listdir(os.path.join(self.vault, "inbox"))
                         if os.path.isdir(os.path.join(self.vault, "inbox")) else [])

    def test_a_file_named_like_one_in_the_project_is_its_new_version(self):
        new = self.brain.add_file(content=PROPOSAL_V3, filename="spring-launch-proposal_v3.md",
                                  project=self.project, principal="person:ana", origin="chat")
        self.assertEqual(new.data["status"], "applied", new.text)
        self.assertEqual(new.data["replaced"], self.path)
        self.assertEqual(new.data["version"], 3)
        self.assertIn("version 3 of Spring launch proposal", new.text)
        card = self.card()
        self.assertEqual(str(card.meta["version"]), "3")
        self.assertNotIn("file_status", card.meta)  # the new copy is not the one that was sent
        self.assertEqual(len([c for c in self.brain.state().index.cards.values()
                              if c.route_key == card.route_key]), 1)
        self.assertIn("800 dollars", self.brain.reference(self.path).text)

    def test_undo_puts_the_earlier_version_back_then_takes_the_file_out(self):
        new = self.brain.add_file(content=PROPOSAL_V3, filename="Spring launch proposal v3.md",
                                  project=self.project, principal="person:ana")
        undone = self.brain.undo(new.data["checkpoint"]["id"], actor="person:ana")
        self.assertFalse(undone.is_error, undone.text)
        self.assertIn("600 dollars", self.brain.reference(self.path).text)
        self.assertEqual(str(self.card().meta["version"]), "2")
        self.assertEqual(self.card().meta["file_status"], "sent")
        first = self.brain.undo(self.filed.data["checkpoint"]["id"], actor="person:ana")
        self.assertFalse(first.is_error, first.text)
        self.assertIsNone(self.card())
        self.assertTrue(self.brain.reference(self.path).is_error)

    def test_the_same_bytes_again_name_the_file_they_are(self):
        again = self.brain.add_file(content=PROPOSAL_V2, filename="copy.md",
                                    principal="person:ana")
        self.assertEqual(again.data["status"], "duplicate")
        self.assertEqual(again.data["path"], self.path)
        self.assertIn("Spring launch proposal", again.text)

    def test_an_unknown_project_is_refused(self):
        res = self.brain.add_file(content="x y z", filename="n.md", project="no such work",
                                  principal="person:ana")
        self.assertTrue(res.is_error)
        self.assertEqual(res.data["status"], "invalid")


class ProjectReadTests(ProjectFilesBase):
    def test_a_project_reads_in_full_with_its_files_progress_and_notes(self):
        self.brain.focus_update(self.project, "Sent v2 to Ana", {"next": "Wait for Ana"},
                                principal="person:ana", evidence="the app")
        made = self.brain.propose(
            area="projects", topic="spring-launch-proposals", title="Video first",
            text="The LinkedIn videos come before the podcast spots.", note_kind="fact",
            principal="person:ana", evidence="Ana, in the kickoff")
        self.assertFalse(made.is_error, made.text)
        if made.data.get("status") == "pending":
            self.brain.approve(made.data["proposal_id"], principal="person:ana")
        res = self.brain.project("the spring proposals", principal="person:ana")
        self.assertFalse(res.is_error, res.text)
        data = res.data
        self.assertEqual((data["id"], data["title"]), (self.project, "Spring launch proposals"))
        self.assertEqual(data["aliases"], ["the spring proposals", "spring launch"])
        self.assertEqual(data["state"]["next"], "Wait for Ana")
        self.assertEqual(data["updates"][0]["summary"], "Sent v2 to Ana")
        (filed,) = data["files"]
        self.assertEqual((filed["path"], filed["version"], filed["file_status"]),
                         (self.path, 2, "sent"))
        self.assertEqual(filed["sections"], 4)
        self.assertEqual([n["title"] for n in data["notes"]], ["Video first"])
        self.assertTrue(self.brain.project("no such work", principal="person:ana").is_error)

    def test_a_projects_other_names_are_set_in_one_field(self):
        res = self.brain.update(self.project, {"aliases": " the launch ,spring site, the launch"})
        self.assertFalse(res.is_error, res.text)
        data = self.brain.project(self.project, principal="person:ana").data
        self.assertEqual(data["aliases"], ["the launch", "spring site"])
        self.brain.update(self.project, {"aliases": ""})
        self.assertEqual(self.brain.project(self.project, principal="person:ana").data["aliases"],
                         [])


class RoutingTests(ProjectFilesBase):
    def test_the_part_a_request_is_about_is_quoted_with_its_version(self):
        res = self.ctx("Tighten the LinkedIn section of the spring launch proposal")
        self.assertIn("## From your files", res.text)
        self.assertIn("Budget: 600 dollars", res.text)
        self.assertNotIn("Local Eats", res.text)
        self.assertIn("version 2", res.text)
        self.assertIn("sent", res.text)
        self.assertIn(f'get_reference(path="{self.path}")', res.text)
        self.assertEqual(res.data["section_ids"], [f"{self.path}#2"])
        self.assertNotIn(self.card().id, res.data["note_ids"])  # quoted instead of its card

    def test_a_question_reaches_the_part_that_answers_it_without_naming_the_file(self):
        res = self.ctx("What budget did we propose for the podcast sponsorship?")
        self.assertIn("Local Eats", res.text)
        self.assertEqual(res.data["section_ids"], [f"{self.path}#3"])

    def test_a_section_is_not_sent_twice_to_one_conversation(self):
        first = self.ctx("What budget did we propose for the podcast sponsorship?",
                         record=True)
        again = self.ctx("What budget did we propose for the podcast sponsorship?",
                         record=True, session_id=first.data["session_id"])
        self.assertNotIn("## From your files", again.text)
        self.assertIn("Podcast sponsorship", again.text.split("## Already in this "
                                                              "conversation", 1)[1])
        self.assertEqual(again.data["held_section_ids"], [f"{self.path}#3"])

    def test_requests_that_are_not_about_the_file_do_not_quote_it(self):
        for request in ("What are our opening hours?",
                        "Write an Instagram caption about our sourdough loaves",
                        "Make the opening line punchier"):
            with self.subTest(request=request):
                self.assertNotIn("## From your files", self.ctx(request).text)

    def test_a_writing_task_quotes_only_the_files_it_names(self):
        # The post shares its subject with the proposal's LinkedIn part, but it is not written
        # from the proposal: the proposal is pointed to, not quoted.
        loose = self.ctx("Write a LinkedIn post about our bakers at work")
        self.assertNotIn("## From your files", loose.text)
        self.assertIn(self.card().id, loose.data["note_ids"] + loose.data["related_ids"])
        # Naming its project makes the proposal the material the post is written from.
        named = self.ctx("Write a LinkedIn post for the spring launch about our bakers at work")
        self.assertEqual(named.data["section_ids"], [f"{self.path}#2"])

    def test_a_meeting_is_named_by_the_person_in_its_title(self):
        call = ("Pasted transcript of a planning call.\n\n[00:00] Okay so the main thing is the "
                "polls. I want to run a poll every other Tuesday on Instagram about which bread "
                "people want next, and write the results up for the cafes at the end of the "
                "season. [00:20] Six or seven Tuesdays is enough. [00:25] And the tasting day "
                "stays on the Saturday before the end of April, I'll book the back room.\n")
        filed = self.brain.add_file(content=call, filename="TomMeeting transcript (2026-03-02).md",
                                    project="the spring proposals", principal="person:ana",
                                    origin="app")
        path = filed.data["path"]
        self.assertEqual(self.brain.state().index.file_title(path), "TomMeeting transcript")
        res = self.ctx("What did Tom say about the polls?")
        self.assertEqual(res.data["section_ids"], [f"{path}#1"])

    def test_a_status_question_lists_the_projects_files(self):
        res = self.ctx("What's the status of the spring proposals?")
        self.assertEqual(res.data["focus_id"], self.project)
        self.assertIn("Files:", res.text)
        self.assertIn("Spring launch proposal (version 2, sent", res.text)

    def test_a_superseded_copy_is_not_quoted(self):
        card = self.card()
        meta = dict(card.meta, file_status="superseded")
        util.atomic_write(os.path.join(self.vault, card.path), fm.dump(meta, card.body + "\n"))
        res = self.ctx("What budget did we propose for the podcast sponsorship?")
        self.assertNotIn("## From your files", res.text)

    def test_a_guide_kept_whole_is_quoted_when_named_not_on_a_loose_match(self):
        # A reference filed the older way: a pointer note, no `type: file` on it.
        guide = ("# Bakery brand guide\n\n## Photo style\n\nShoot loaves in morning light on "
                 "the oak counter. Never use filters.\n\n## Captions\n\nShort captions, one "
                 "emoji at most, and the price when there is one.\n")
        util.atomic_write(os.path.join(self.vault, "references", "bakery-brand-guide.md"),
                          guide)
        meta = {"id": "bakery-brand-guide-pointer", "title": "Bakery brand guide",
                "summary": "Where the full brand guide is.", "area": "brand", "topic": "voice",
                "kind": "fact", "scope": "company", "status": "approved", "load": "on-demand",
                "added": "2026-08-01"}
        util.atomic_write(
            os.path.join(self.vault, "knowledge", "brand", "voice",
                         "2026-08-01-bakery-brand-guide-pointer.md"),
            fm.dump(meta, "Pointer: the bakery brand guide is filed whole at "
                          "references/bakery-brand-guide.md.\n"))
        loose = self.ctx("Write an Instagram caption about our morning loaves")
        self.assertNotIn("## From your files", loose.text)
        named = self.ctx("What does the bakery brand guide say about captions?")
        self.assertIn("## From your files", named.text)
        self.assertIn("one emoji at most", named.text)

    def test_preview_says_what_an_ai_gets_and_why_without_recording_it(self):
        res = self.brain.preview("Tighten the LinkedIn section of the spring launch proposal",
                                 principal="person:ana")
        self.assertFalse(res.is_error, res.text)
        self.assertEqual(res.data["project"]["id"], self.project)
        self.assertEqual(res.data["sections"][0]["label"], "LinkedIn video")
        self.assertEqual(res.data["sections"][0]["why"], "in the project it names")
        self.assertIn("## From your files", res.text)
        self.assertNotIn("Startup context", res.text)
        self.assertNotIn("session_id", res.text)
        import sqlite3
        ledger = os.path.join(self.vault, ".brain", "sessions.sqlite")
        if os.path.exists(ledger):
            with sqlite3.connect(ledger) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM packets").fetchone()[0], 0)

    def test_search_finds_what_files_hold_beside_notes(self):
        res = self.brain.search("podcast sponsorship budget", principal="person:ana")
        self.assertFalse(res.is_error, res.text)
        self.assertEqual(res.data["files"][0]["id"], f"{self.path}#3")
        self.assertIn("In the brain's files:", res.text)
        self.assertIn("Podcast sponsorship", res.text)
        self.assertIn("get_reference", res.text)


class PolicyTests(unittest.TestCase):
    """The design-studio brain: Alex owns it, Sam is a colleague."""

    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_the_owners_files_are_filed_and_a_colleagues_wait(self):
        own = self.brain.add_file(content="# Rates\n\nDay rate: 900.", filename="rates.md",
                                  principal="person:alex", origin="chat")
        self.assertEqual(own.data["status"], "applied", own.text)
        other = self.brain.add_file(content="# Notes\n\nSam's notes.", filename="sam.md",
                                    principal="person:sam", origin="chat")
        self.assertEqual(other.data["status"], "pending", other.text)

    def test_the_owner_can_make_files_from_a_chat_wait(self):
        changed = self.brain.set_policies({"capture": {"file": {"chat": "wait"}}},
                                          actor="person:alex")
        self.assertFalse(changed.is_error, changed.text)
        with open(os.path.join(self.vault, "brain.json"), encoding="utf-8") as handle:
            stored = json.load(handle)["governance"]["capture"]
        self.assertEqual(stored, {"file": {"chat": "wait"}})  # only what differs is kept
        chat = self.brain.add_file(content="# A\n\nAlpha.", filename="a.md",
                                   principal="person:alex", origin="chat")
        self.assertEqual(chat.data["status"], "pending")
        app = self.brain.add_file(content="# B\n\nBeta.", filename="b.md",
                                  principal="person:alex", origin="app")
        self.assertEqual(app.data["status"], "applied")

    def test_defaults_and_refusals(self):
        # Without a preset a Brain is careful: only files go in at once (test_presets.py).
        policy = self.brain.policies().data["capture"]
        self.assertEqual(policy["rule"]["chat"], "wait")
        self.assertEqual(policy["decision"]["chat"], "wait")
        self.assertEqual(policy["file"]["chat"], "apply")
        bad = self.brain.set_policies({"capture": {"gossip": {"chat": "apply"}}},
                                      actor="person:alex")
        self.assertTrue(bad.is_error)
        bad = self.brain.set_policies({"capture": {"file": {"phone": "apply"}}},
                                      actor="person:alex")
        self.assertTrue(bad.is_error)


HOLD = """
import sys, time
sys.path.insert(0, {src!r})
from brainkit.locking import WriteLock
lock = WriteLock({path!r})
lock.acquire()
print("held", flush=True)
time.sleep({seconds})
lock.release()
"""


class LockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="brain-lock-")
        self.path = os.path.join(self.tmp, ".brain", "write.lock")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def hold(self, seconds):
        proc = subprocess.Popen([sys.executable, "-c",
                                 HOLD.format(src=SRC, path=self.path, seconds=seconds)],
                                stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.stdout.close)
        self.assertEqual(proc.stdout.readline().strip(), "held")
        return proc

    def test_a_second_process_waits_for_the_first_to_finish(self):
        proc = self.hold(1.0)
        start = time.monotonic()
        with WriteLock(self.path, timeout=20):
            waited = time.monotonic() - start
        proc.wait(20)
        self.assertGreater(waited, 0.5)

    def test_a_vault_held_too_long_is_a_busy_error_not_a_crash(self):
        proc = self.hold(3.0)
        try:
            with self.assertRaises(Busy):
                WriteLock(self.path, timeout=0.3).acquire()
        finally:
            proc.wait(20)

    def test_the_lock_is_reentrant_within_a_process(self):
        lock = WriteLock(self.path, timeout=1)
        with lock:
            with lock:
                self.assertTrue(lock.held)
        self.assertFalse(lock.held)

    def test_a_brain_write_reports_busy(self):
        vault = test_layout.build()
        brain = Brain(vault, embeddings=False)
        self.path = os.path.join(vault, ".brain", "write.lock")
        proc = self.hold(3.0)
        try:
            brain._writes.timeout = 0.3
            res = brain.propose(area="company", topic="menu", text="We sell rye bread.",
                                principal="person:ana")
            self.assertTrue(res.is_error)
            self.assertEqual(res.data["status"], "busy")
        finally:
            proc.wait(20)
            brain.close()
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
