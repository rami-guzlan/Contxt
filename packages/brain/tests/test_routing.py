"""Routing and packets on the generic fixture brain: every mode, admission, and sessions."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit.api import Brain
from tests import fixture


class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vault = fixture.build()
        cls.brain = Brain(cls.vault, embeddings=False)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'brain'):
            cls.brain.close()
        fixture.remove(cls.vault)

    def ctx(self, request, **kwargs):
        kwargs.setdefault("record", False)
        result = self.brain.context(request, **kwargs)
        self.assertFalse(result.is_error, result.text)
        return result

    def test_a_multiword_term_is_read_as_one_word(self):
        from brainkit import router
        from brainkit.config import RoutingConfig
        from brainkit.index import BM25
        sig = router.analyze("Now add a call to action to the post", RoutingConfig())
        self.assertIn("cta", sig.wordset)
        self.assertNotIn("call", sig.wordset)
        own = router.analyze("Draft the statement of work",
                             RoutingConfig(phrases={"statement of work": "sow"}))
        self.assertIn("sow", own.wordset)
        bm25 = BM25({"calls": "Lessons from cold calling bank leaders",
                     "cta": "Every post ends with one CTA."})
        scores = bm25.scores("Add a Call-to-Action")
        self.assertIn("cta", scores)
        self.assertNotIn("calls", scores)

    def test_also_relevant_titles_clear_the_floor_and_freshness_sets_no_bar(self):
        floor = self.brain.state().router.policy.note_abs_floor
        for request in ("What are the grid and spacing rules?", "How long do projects run?",
                        "Write a headline for our web design service page"):
            data = self.ctx(request, explain=True).data
            scores = {s["id"]: s for s in data["trace"]["note_scores"]}
            for note_id in data["related_ids"]:
                self.assertGreaterEqual(scores[note_id]["adj"], floor, (request, note_id))

    def test_a_note_past_the_budget_is_named_never_dropped(self):
        """Nothing is silently left out: a selected note that does not fit the brief's budget
        comes in short, or is named under "Did not fit" for the model to open."""
        from unittest import mock
        request = "Write a headline for our web design service page"
        selected = self.ctx(request).data["note_ids"]
        self.assertGreater(len(selected), 1)
        for budget in (1, 40, 90, 160):
            with mock.patch("brainkit.packets.note_budget", return_value=budget):
                res = self.ctx(request, explain=True)
            named = set(res.data["note_ids"]) | set(res.data["related_ids"])
            for note_id in selected:
                self.assertIn(note_id, named, budget)
                self.assertIn(note_id, res.text.split("# Task context", 1)[1], budget)
            skipped = [d for d in res.data["trace"]["decisions"] if "skipped" in d]
            self.assertEqual(skipped, [], budget)
        with mock.patch("brainkit.packets.note_budget", return_value=1):
            res = self.ctx(request)
        self.assertEqual(res.data["note_ids"], [])
        self.assertEqual(res.data["unfit_ids"], selected)
        self.assertIn("## Did not fit", res.text)
        self.assertIn('get_note(id="...")', res.text.split("## Did not fit", 1)[1])

    def test_a_topic_gate_yields_to_a_request_that_names_the_note(self):
        # facts/clients asks for a client's name; naming what the note says is as good.
        named = self.ctx("Which screens need WCAG AA contrast?", partition="client:globex",
                         explain=True).data
        scores = {s["id"]: s for s in named["trace"]["note_scores"]}
        self.assertFalse(scores["facts-clients-globex-001"]["gated"])
        # One shared word is a loose match: the gate holds, and the note stays out.
        router = self.brain.state().router
        self.assertTrue(router._names("Which screens need WCAG AA contrast?",
                                      "facts-clients-globex-001"))
        self.assertFalse(router._names("Is contrast important?", "facts-clients-globex-001"))
        loose = self.ctx("Is contrast important?", partition="client:globex").data
        self.assertNotIn("facts-clients-globex-001", loose["note_ids"])

    def test_a_proper_name_in_a_focus_summary_names_that_focus(self):
        data = self.ctx("Draft show notes for the Quillfeather session").data
        self.assertEqual(data["focus_id"], "state-focus-studio-podcast")

    def test_a_common_word_in_a_focus_summary_does_not_name_it(self):
        # "relaunch" is rare in this brain and sits in the Website Redesign summary, but a
        # request about relaunching something else is not about that project.
        data = self.ctx("Plan a relaunch of the client newsletter").data
        self.assertIsNone(data["focus_id"])

    def test_knowledge_question_delivers_the_answering_note(self):
        data = self.ctx("How long do web design projects run?").data
        self.assertIn("facts-services-002", data["note_ids"])
        self.assertEqual(data["task_type"], "knowledge")
        self.assertIsNone(data["focus_id"])

    def test_exact_note_id(self):
        data = self.ctx("facts-services-001").data
        self.assertEqual(data["mode"], "exact-note")
        self.assertEqual(data["note_ids"], ["facts-services-001"])

    def test_permission_is_answered_by_standing_rules(self):
        data = self.ctx("Can I send the logo files to the client now?").data
        self.assertEqual(data["mode"], "standing")
        self.assertEqual(data["task_type"], "workflow")
        self.assertIn("rules-delivery-001", data["standing_ids"])
        self.assertEqual(data["note_ids"], [])

    def test_writing_task_gets_house_style(self):
        data = self.ctx("Write a headline for our web design service page").data
        self.assertIn("rules/style", data["topics"])
        self.assertIn("rules-style-002", data["note_ids"])

    def test_unrelated_request_is_lean(self):
        data = self.ctx("What is the weather in Lisbon tomorrow?").data
        self.assertEqual(data["mode"], "lean")
        self.assertEqual(data["note_ids"], [])

    def test_a_question_that_mentions_an_artifact_is_not_a_writing_task(self):
        data = self.ctx("Which client wants a new blog post about grids?", explain=True).data
        self.assertFalse(data["composing"])
        self.assertFalse(any("house style" in line for line in data["trace"]["decisions"]))
        writing = self.ctx("Write a blog post about our grid system", explain=True).data
        self.assertTrue(writing["composing"])
        self.assertTrue(any("house style" in line for line in writing["trace"]["decisions"]))

    def test_a_question_about_how_to_write_lifts_the_style_rules(self):
        data = self.ctx("How should I phrase the headline in the newsletter?", explain=True).data
        self.assertFalse(data["composing"])
        self.assertIn("rules-style-002", data["note_ids"])
        scores = {s["id"]: s for s in data["trace"]["note_scores"]}
        self.assertTrue(scores["rules-style-002"]["rule"])

    def test_a_lean_packet_lists_the_closest_notes_and_says_to_search(self):
        import dataclasses
        router = self.brain.state().router
        policy = router.policy
        router.policy = dataclasses.replace(policy, lean_floor=0.95)
        try:
            result = self.ctx("Who owns the motion budget next year?")
        finally:
            router.policy = policy
        self.assertEqual(result.data["mode"], "lean")
        self.assertEqual(result.data["note_ids"], [])
        self.assertIn("facts-services-001", result.data["related_ids"])
        self.assertIn("## Closest notes (not included)", result.text)
        self.assertIn("search_notes", result.text)

    def test_a_permission_question_is_about_the_action_asked(self):
        self.assertEqual(self.ctx("Can we post the launch announcement now?").data["mode"],
                         "standing")
        # "post" here is the thing the budget is for, not the action asked about.
        about = self.ctx("Can we put a budget behind the launch post?").data
        self.assertNotEqual(about["mode"], "standing")

    def test_a_newcomer_gets_a_map_and_the_owner_still_gets_the_portfolio(self):
        result = self.ctx("I'm new here. What do I need to know before I write anything?")
        self.assertEqual(result.data["mode"], "orientation")
        self.assertIn("## What this brain covers", result.text)
        self.assertTrue(result.data["note_ids"])
        self.assertEqual(self.ctx("Get me up to speed on what's active").data["mode"],
                         "portfolio")

    def test_named_focus_status_update_and_work(self):
        status = self.ctx("Where are we with the website redesign?").data
        self.assertEqual((status["mode"], status["focus_id"]),
                         ("focus-only", "state-focus-website-redesign"))
        self.assertEqual(status["note_ids"], ["state-focus-website-redesign"])
        update = self.ctx("The Figma prototype was approved by the client, record that").data
        self.assertEqual(update["focus_mode"], "focus-update")
        self.assertEqual(update["focus_id"], "state-focus-website-redesign")
        packet = self.ctx("The Figma prototype was approved by the client, record that").text
        self.assertIn("record_focus_update", packet)

    def test_a_task_in_a_project_opens_with_the_projects_objective(self):
        # Its summary stands in until the project has an objective of its own.
        text = self.ctx("Draft the launch email for the website redesign").text
        task = text.split("## Task\n\n", 1)[1]
        self.assertTrue(task.startswith("Objective of the project Website Redesign: Northwind "
                                        "site relaunch from the Figma prototype\n\nDraft the "
                                        "launch email"), task[:200])
        focus = self.brain.state().index.focuses["state-focus-website-redesign"]
        focus.note.meta["objective"] = "A relaunched site that wins two new clients a quarter."
        self.assertEqual(focus.objective, "A relaunched site that wins two new clients a quarter.")

    def test_portfolio(self):
        data = self.ctx("What is active in my brain?").data
        self.assertEqual(data["mode"], "portfolio")
        self.assertEqual(data["portfolio_ids"][0], "state-focus-website-redesign")

    def test_system_question_gets_engine_docs_not_knowledge(self):
        data = self.ctx("How do I restart the brain MCP server?").data
        self.assertEqual(data["mode"], "system")
        self.assertIn("system-mcp", data["system_ids"])
        self.assertEqual(data["note_ids"], [])

    def test_skill_candidate_and_slash_command(self):
        data = self.ctx("Create a brand sheet for the new client").data
        self.assertIn("brand-sheet", data["candidates"])
        self.assertEqual(data["procedure"], "candidate")
        exact = self.ctx("/brand-sheet").data
        self.assertEqual((exact["procedure"], exact["skill_id"]), ("executable", "brand-sheet"))

    def test_a_model_with_no_tools_is_never_asked_to_call_one(self):
        # One side of a comparison runs with no tools at all: told to call one, it writes the
        # call out instead of the answer. It gets the procedure it would open, in full.
        calls = ("get_task_context", "get_skill", "get_note", "get_reference", "search_notes",
                 "propose_note", "propose_skill", "add_file", "create_focus",
                 "record_focus_update", "record_output", "fallback", "session_id", "fresh=true")
        kernel = self.brain.kernel(tools=False).text
        self.assertIn("Nothing goes to a client before Alex approves it.", kernel)
        self.assertNotIn("## Skills", kernel)
        candidate = self.brain.preview("Create a brand sheet for the new client", tools=False)
        self.assertEqual(candidate.data["skill_included"], "brand-sheet")
        self.assertIn("Write the voice lines in plain language.", candidate.text)
        self.assertIn("(the closest for this task; follow it if it fits)", candidate.text)
        self.assertNotIn("## Skill candidates", candidate.text)
        routed = self.brain.preview("/brand-sheet", tools=False)
        self.assertIn("### /brand-sheet (routed for this task)", routed.text)
        self.assertIn("Export a one-page PDF.", routed.text)
        texts = {"kernel": kernel}
        for request in ("Write a headline for our web design service page",
                        "Create a brand sheet for the new client", "/brand-sheet",
                        "Where are we with the website redesign?",
                        "The Figma prototype was approved by the client, record that",
                        "I'm new here. What do I need to know before I write anything?",
                        "What is active in my brain?", "When do invoices go out?",
                        "Write the brand sheet copy; we always use sentence case from now on"):
            texts[request] = self.ctx(request, tools=False).text
        import dataclasses
        router = self.brain.state().router
        policy = router.policy
        router.policy = dataclasses.replace(policy, lean_floor=0.95)
        try:
            lean = self.ctx("Who owns the motion budget next year?", tools=False)
        finally:
            router.policy = policy
        self.assertEqual(lean.data["mode"], "lean")
        self.assertIn("answer from general knowledge", lean.text)
        texts["lean"] = lean.text
        for name, text in texts.items():
            for call in calls:
                self.assertNotIn(call, text, (name, call))
        # A model that can call the brain still gets the pointer, not the text.
        normal = self.brain.preview("Create a brand sheet for the new client")
        self.assertIsNone(normal.data["skill_included"])
        self.assertIn("get_skill", normal.text)
        self.assertNotIn("Write the voice lines", normal.text)

    def test_intent_includes_topic(self):
        data = self.ctx("When do invoices go out?").data
        self.assertIn("billing-question", data["intents"])
        self.assertIn("facts-services-002", data["note_ids"])

    def test_scope_admission_hides_other_people_and_teams(self):
        sam = self.ctx("What are the grid and spacing rules?", principal="person:sam").data
        self.assertNotIn("rules-design-001", sam["note_ids"])
        alex = self.ctx("What are the grid and spacing rules?").data
        self.assertIn("rules-design-001", alex["note_ids"])
        mine = self.ctx("Does anyone prefer async reviews on Fridays?").data
        self.assertNotIn("facts-sam-001", mine["note_ids"])

    def test_partitions_are_sealed(self):
        none = self.ctx("What does Acme prefer for palettes?").data
        self.assertNotIn("facts-clients-acme-001", none["note_ids"])
        acme = self.ctx("What does Acme prefer for palettes?", partition="client:acme").data
        self.assertIn("facts-clients-acme-001", acme["note_ids"])
        self.assertNotIn("facts-clients-globex-001", acme["note_ids"])
        refused = self.brain.context("x", principal="person:sam", partition="client:acme",
                                     record=False)
        self.assertTrue(refused.is_error)

    def test_explain_trace(self):
        data = self.ctx("Write a headline for our web design service page", explain=True).data
        self.assertIn("trace", data)
        self.assertTrue(data["trace"]["note_scores"])


class FakeReranker:
    """Stands in for the cross-encoder: it strongly prefers one note's text."""

    def __init__(self, favourite_text):
        self.favourite_text = favourite_text
        self.calls = 0

    def score(self, query, texts):
        self.calls += 1
        return [5.0 if text == self.favourite_text else -5.0 for text in texts]


class RerankTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def ranked(self, weight, reranker):
        import dataclasses
        from brainkit.router import Route, analyze
        st = self.brain.state()
        router = st.router
        router.reranker = reranker
        router.policy = dataclasses.replace(router.policy, rerank_weight=weight)
        request = "What do web design projects cost and how long do they run?"
        chain = st.scopes.chain("person:alex")
        notes = [n for n in router.admitted_notes(chain, []) if not n.standing
                 and not st.config.is_focus(n)]
        route = Route(request=request, chain=chain, partitions=[],
                      signals=analyze(request, st.config.routing))
        before = router.score_notes(request, notes)
        return before, router._rerank(route, request, before)

    def test_reranker_reorders_near_ties_but_keeps_every_score(self):
        before, _ = self.ranked(0.0, None)
        note = before[1].item
        chars = self.brain.state().router.policy.rerank_chars
        fake = FakeReranker(f"{note.title}. {note.summary} {note.body}"[:chars])
        _, after = self.ranked(0.5, fake)
        self.assertEqual(fake.calls, 1)
        # The favourite takes first place, with the first place's original score: the best
        # score, and so every relative threshold, is unchanged.
        self.assertEqual(after[0].item.id, note.id)
        self.assertEqual(after[0].score, before[0].score)
        self.assertEqual(sorted(s.score for s in before), sorted(s.score for s in after))
        # A small weight cannot overturn a clear gap.
        _, gentle = self.ranked(0.001, fake)
        self.assertEqual(gentle[0].item.id, before[0].item.id)

    def test_weight_zero_or_no_model_changes_nothing(self):
        fake = FakeReranker("anything")
        before, after = self.ranked(0.0, fake)
        self.assertEqual([s.item.id for s in before], [s.item.id for s in after])
        self.assertEqual(fake.calls, 0)
        before, after = self.ranked(0.5, None)
        self.assertEqual([s.item.id for s in before], [s.item.id for s in after])

    def test_reranker_never_downloads_on_its_own(self):
        import tempfile
        from brainkit.index import Reranker
        reranker = Reranker(tempfile.mkdtemp(prefix="brain-rerank-"))
        self.assertFalse(reranker.present())
        self.assertIsNone(reranker.score("anything", ["a note"]))
        self.assertIn("not downloaded", reranker.status()["reason"])


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_session_dedupes_and_fresh_resends(self):
        first = self.brain.context("How long do web design projects run?")
        session = first.data["session_id"]
        self.assertIn("facts-services-002", first.data["note_ids"])
        self.assertTrue(first.data["kernel_included"])
        again = self.brain.context("How long do web design projects run?", session_id=session)
        self.assertNotIn("facts-services-002", again.data["note_ids"])
        self.assertIn("facts-services-002", again.data["held_ids"])
        self.assertFalse(again.data["kernel_included"])
        fresh = self.brain.context("How long do web design projects run?", session_id=session,
                                   fresh=True)
        self.assertIn("facts-services-002", fresh.data["note_ids"])

    def test_startup_fingerprint_suppresses_kernel(self):
        kernel = self.brain.kernel()
        res = self.brain.context("What services do we offer?",
                                 startup_fingerprint=kernel.data["fingerprint"])
        self.assertFalse(res.data["kernel_included"])
        self.assertNotIn("# Startup context", res.text)

    def test_the_kernel_names_the_vaults_command_whatever_the_process_says(self):
        import os
        from unittest import mock
        plain = self.brain.kernel()
        with mock.patch.dict(os.environ, {"BRAIN_CLI": "python other.py"}):
            same = self.brain.kernel()
        self.assertEqual(plain.data["fingerprint"], same.data["fingerprint"])
        self.assertIn("`brain context", plain.text)
        config = self.brain.state().config
        with mock.patch.dict(config.data, {"cli": "python brain.py"}):
            from brainkit import kernel as kernel_mod
            text, _ = kernel_mod.render(config, self.brain.state().index,
                                        self.brain.state().scopes, ["company"])
        self.assertIn("`python brain.py context", text)

    def test_kernel_proven_by_fingerprint_is_not_resent_later(self):
        kernel = self.brain.kernel().data["fingerprint"]
        first = self.brain.context("What services do we offer?", startup_fingerprint=kernel)
        later = self.brain.context("How long do web design projects run?",
                                   session_id=first.data["session_id"])
        self.assertFalse(first.data["kernel_included"])
        self.assertFalse(later.data["kernel_included"])

    def test_explicit_skills_run_by_name_only(self):
        skill_path = os.path.join(self.vault, "skills", "design", "brand-sheet", "SKILL.md")
        with open(skill_path, encoding="utf-8") as handle:
            text = handle.read()
        with open(skill_path, "w", encoding="utf-8") as handle:
            handle.write(text.replace("loads:", "invocation: explicit\nloads:", 1))
        suggested = self.brain.context("Create a brand sheet for the new client", record=False)
        self.assertNotIn("brand-sheet", suggested.data["candidates"])
        named = self.brain.context("/brand-sheet", record=False)
        self.assertEqual(named.data["skill_id"], "brand-sheet")

    def test_followup_inherits_topics_and_stays_small(self):
        first = self.brain.context("Write a headline for our web design service page")
        session = first.data["session_id"]
        follow = self.brain.context("Make it shorter and punchier", session_id=session,
                                    explain=True)
        self.assertTrue(any("follow-up" in line
                            for line in follow.data["trace"]["route_log"]))
        self.assertEqual(follow.data["followup"], "edit")
        self.assertEqual(follow.data["candidates"], [])
        self.assertTrue(set(follow.data["topics"]) <= set(first.data["topics"]))

    def test_editing_a_named_document_part_is_a_pure_edit(self):
        # A side question between the draft and the edit does not make the edit new: it is
        # compared with the request that started the draft. "Executive summary" is a part of
        # the document, not a subject.
        first = self.brain.context("Write a proposal for a new client's web design project")
        session = first.data["session_id"]
        side = self.brain.context("How long do projects run?", session_id=session)
        self.assertFalse(side.data["followup"])
        edit = self.brain.context("Make the executive summary warmer", session_id=session)
        self.assertEqual(edit.data["followup"], "edit")
        self.assertEqual(edit.data["candidates"], [])
        self.assertEqual(edit.data["draft"], first.data["draft"])
        self.assertIn("proposal", edit.data["draft"])

    def test_naming_new_subject_matter_in_a_writing_task_still_continues_it(self):
        first = self.brain.context("Write a headline for our web design service page")
        later = self.brain.context("Now add a CTA to the brand sheet offer",
                                   session_id=first.data["session_id"])
        self.assertEqual(later.data["followup"], "continuation")
        self.assertTrue(later.data["composing"])
        executive = self.brain.context("Make the executive program warmer",
                                       session_id=first.data["session_id"])
        self.assertEqual(executive.data["followup"], "continuation")

    def test_continuation_reaches_past_the_previous_topics(self):
        # "Also, ..." carries on the conversation and asks something new: it is routed with
        # the conversation's subject, not held to what the first packet loaded.
        first = self.brain.context("How long do web design projects run?")
        follow = self.brain.context("Also, what are our rules for headlines?",
                                    session_id=first.data["session_id"])
        self.assertEqual(follow.data["followup"], "continuation")
        self.assertIn("rules-style-002", follow.data["note_ids"])
        self.assertNotIn("rules/style", first.data["topics"])
        self.assertIn("web design projects", follow.data["subject"])

    def test_a_new_request_in_a_session_starts_a_new_subject(self):
        first = self.brain.context("How long do web design projects run?")
        later = self.brain.context("Write a headline for our motion design service page",
                                   session_id=first.data["session_id"])
        self.assertFalse(later.data["followup"])
        self.assertNotIn("projects run", later.data["subject"])

    def test_a_short_question_the_brain_can_answer_alone_is_not_a_follow_up(self):
        first = self.brain.context("Write a headline for our web design service page")
        later = self.brain.context("How long do projects run?",
                                   session_id=first.data["session_id"])
        self.assertFalse(later.data["followup"])
        self.assertIn("facts-services-002", later.data["note_ids"] + later.data["held_ids"])

    def test_a_continuation_passes_topic_gates_through_the_conversation(self):
        # facts/clients asks for a client's name; "they" in the follow-up means Acme.
        first = self.brain.context("What does Acme like in a design?", partition="client:acme")
        follow = self.brain.context("Do they hate stock photography too?",
                                    session_id=first.data["session_id"],
                                    partition="client:acme", explain=True)
        self.assertEqual(follow.data["followup"], "continuation")
        scores = {s["id"]: s for s in follow.data["trace"]["note_scores"]}
        self.assertFalse(scores["facts-clients-acme-001"]["gated"])
        self.assertIn("facts-clients-acme-001", follow.data["held_ids"])
        self.assertIn("nothing for this beyond what this conversation already holds",
                      follow.text)


    def test_a_short_question_that_names_its_own_subject_is_not_a_follow_up(self):
        first = self.brain.context("How long do web design projects run?")
        later = self.brain.context("What is the capital of Portugal?",
                                   session_id=first.data["session_id"])
        self.assertFalse(later.data["followup"])


class ConflictLinkTests(unittest.TestCase):
    """A note that says it contradicts another brings that note along."""

    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_a_note_that_names_a_conflict_travels_with_it(self):
        from brainkit import governance
        res = self.brain.propose(layer="facts", topic="services", scope="company",
                                 text="Web design projects now run ten weeks from kickoff to "
                                      "launch, which contradicts `facts-services-002`.")
        governance.approve(self.brain, res.data["proposal_id"])
        data = self.brain.context("How long do web design projects run from kickoff to "
                                  "launch now?", record=False).data
        self.assertIn(res.data["id"], data["note_ids"])
        self.assertIn("facts-services-002", data["note_ids"])


class PlacementTests(unittest.TestCase):
    """How a writing task's packet spends its budget on house style."""

    @staticmethod
    def scored(note_id, tokens, **detail):
        from types import SimpleNamespace
        from brainkit.router import Scored
        note = SimpleNamespace(id=note_id, tokens=tokens)
        return Scored(item=note, score=detail.get("rel", 0.5),
                      detail={"rel": 0.5, "adj": 0.5, "blend": 0.5, **detail})

    def place(self, style, notes=(), total=1000, held=()):
        from types import SimpleNamespace
        from brainkit.packets import _place_notes
        from brainkit.router import Policy
        route = SimpleNamespace(policy=Policy(house_style_share=0.3), style_notes=list(style),
                                notes=list(notes), signals=SimpleNamespace(edit=False))
        placed = []
        _place_notes(route, lambda note, reason: placed.append((note.id, reason)), total,
                     lambda note: note.id in held)
        return placed

    def test_a_held_style_rule_costs_the_share_nothing(self):
        style = [self.scored("core-a", 200, core=True), self.scored("core-b", 80, core=True)]
        placed = dict(self.place(style, held={"core-a"}))
        self.assertEqual(placed["core-a"], "house style, already held")
        self.assertIn("core-b", placed)

    def test_a_rule_specific_to_the_request_goes_in_past_the_share(self):
        style = [self.scored("core-a", 280, core=True),
                 self.scored("cta-ladder", 150, core=False, specific=True, rel=0.7),
                 self.scored("generic", 40, core=False)]
        placed = dict(self.place(style))
        self.assertIn("core-a", placed)
        self.assertIn("for this request", placed["cta-ladder"])
        # The specific rule counts against the share, so it makes no room for a generic one.
        self.assertNotIn("generic", placed)


    def test_a_rule_for_another_format_does_not_fill_spare_share(self):
        style = [self.scored("core-a", 100, core=True),
                 self.scored("post-architecture", 60, core=False, format_fits=False),
                 self.scored("vocabulary", 60, core=False, format_fits=True)]
        placed = dict(self.place(style))
        self.assertNotIn("post-architecture", placed)
        self.assertIn("vocabulary", placed)

if __name__ == "__main__":
    unittest.main()
