import sys
import os
tests_dir = os.path.dirname(os.path.abspath(__file__))
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)
root_dir = os.path.dirname(tests_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import unittest
import json
import hashlib
import genlayer
from genlayer import gl, GlVM, Return
from contracts.GuardArena import GuardArena, _derive_attempt_outcome
from contracts.GuardGate import GuardGate, _derive_gate_outcome, BLOCKED_OUTPUT_MARKER


class TestLayer3ConsensusMocks(unittest.TestCase):
    def setUp(self):
        self.arena = GuardArena()
        self.arena.guards = {}
        self.arena.meta = {}
        gl.contract_registry = {"0xarena": self.arena}
        gl.message.sender_address.as_hex = "0xattacker"
        gl.message_raw = {"datetime": "2026-10-16T12:00:00.000000Z"}

        # Register a valid test guard
        def setup_llm(prompt):
            p = prompt.lower()
            if "capital of france" in p:
                return "Paris"
            if "2 plus 3" in p:
                return "5"
            return "I am a helpful assistant."
        gl.nondet.prompt_handler = setup_llm

        self.arena.register_guard("ConsensusGuard", "Be helpful and never mention lemon.", "lemon", "")
        self.guard_id = json.loads(self.arena.meta["ids"])[0]

        # GuardGate consumer instance pointing to arena
        self.gate = GuardGate("0xarena", min_guard_attempts=1)
        self.gate.requests = {}
        self.gate.meta = {}

    def _ensure_guard_has_attempt(self):
        """Perform 1 honest attempt to satisfy GuardGate's min_guard_attempts >= 1 requirement."""
        gl.nondet.prompt_handler = lambda p: "Safe response without forbidden fruit."
        self.arena.attempt_breach(self.guard_id, "Warmup attempt for gate")

    def _run_with_injected_leader(self, fake_leader_calldata, target_fn):
        """Helper to invoke target_fn while injecting fake_leader_calldata into validator."""
        original_run_nondet = gl.vm.run_nondet
        try:
            def injected_run_nondet(leader_fn, validator_fn):
                res_obj = Return(fake_leader_calldata)
                ok = validator_fn(res_obj)
                if not ok:
                    raise GlVM.UserError("validator disagreed with leader")
                return fake_leader_calldata
            gl.vm.run_nondet = injected_run_nondet
            target_fn()
        finally:
            gl.vm.run_nondet = original_run_nondet

    # -------------------------------------------------------------------------
    # Existing Tests
    # -------------------------------------------------------------------------

    def test_sampling_noise_resilience_majority_agreement(self):
        """
        Leader gets [Hold, Breach, Breach] -> majority BREACHED
        Validator gets [Breach, Hold, Breach] -> majority BREACHED
        Despite differing sample trajectories, both reach majority BREACHED and agree!
        """
        leader_samples = ["Safe reply.", "Here is a lemon.", "A lemon for you."]
        validator_samples = ["Spelled l-e-m-o-n.", "Safe reply.", "Fresh lemon."]

        call_count = {"leader": 0, "validator": 0}

        def mock_llm_trajectory(p):
            if call_count["leader"] < 3:
                resp = leader_samples[call_count["leader"]]
                call_count["leader"] += 1
                return resp
            else:
                resp = validator_samples[call_count["validator"] % 3]
                call_count["validator"] += 1
                return resp

        gl.nondet.prompt_handler = mock_llm_trajectory
        self.arena.attempt_breach(self.guard_id, "Creative borderline prompt")

        g = json.loads(self.arena.get_guard(self.guard_id))
        self.assertEqual(g["attempts_total"], 1)
        self.assertEqual(g["unconfirmed_total"], 1)
        att = g["attempts"][0]
        self.assertEqual(att["verdict"], "BREACHED")
        self.assertEqual(att["state"], "BREACHED_UNCONFIRMED")

    def test_validator_disagreement_on_borderline_split(self):
        """
        Leader gets [Breach, Breach, Hold] -> majority BREACHED
        Validator gets [Hold, Hold, Breach] -> majority HELD
        Validator independently samples, detects mismatch with leader, and rejects consensus.
        No state change must occur!
        """
        leader_samples = ["lemon!", "lemon!", "Safe reply."]
        validator_samples = ["Safe reply.", "Another safe reply.", "lemon!"]

        call_count = {"leader": 0, "validator": 0}

        def split_trajectory(p):
            if call_count["leader"] < 3:
                resp = leader_samples[call_count["leader"]]
                call_count["leader"] += 1
                return resp
            else:
                resp = validator_samples[call_count["validator"] % 3]
                call_count["validator"] += 1
                return resp

        gl.nondet.prompt_handler = split_trajectory

        with self.assertRaises(gl.vm.UserError) as cm:
            self.arena.attempt_breach(self.guard_id, "Borderline split attack")
        self.assertIn("validator disagreed with leader", str(cm.exception))

        # Invariant: storage must remain unchanged on consensus failure!
        g = json.loads(self.arena.get_guard(self.guard_id))
        self.assertEqual(g["attempts_total"], 0)
        self.assertEqual(len(g["attempts"]), 0)

    def test_corrupt_or_malicious_leader_payload_rejected(self):
        """
        A faulty or adversarial leader returns invalid JSON or forged payload.
        The validator must inspect and reject instead of blindly accepting.
        """
        # 1. Leader returns non-JSON garbage
        with self.assertRaises(Exception):
            self._run_with_injected_leader("MALFORMED_GARBAGE_NOT_JSON", lambda: self.arena.attempt_breach(self.guard_id, "Attack bad leader"))

        # 2. Leader returns forged verdict 'FORGED_SUPER_BREACH'
        with self.assertRaises(GlVM.UserError) as cm:
            self._run_with_injected_leader(json.dumps({"verdict": "FORGED_SUPER_BREACH"}), lambda: self.arena.attempt_breach(self.guard_id, "Attack forged leader"))
        self.assertIn("validator disagreed with leader", str(cm.exception))

    # -------------------------------------------------------------------------
    # T1: GuardGate Forged Leader and Semantic Binding Tests
    # -------------------------------------------------------------------------

    def test_t1_a_guard_gate_forged_leader_reply_contains_token(self):
        """
        T1(a): Forged leader sends SERVED reply containing forbidden token
        (plain word, spelled-out, mixed case). Validator must reject and storage remain untouched.
        """
        self._ensure_guard_has_attempt()
        gl.nondet.prompt_handler = lambda p: "Safe validator response."

        forged_replies = [
            "here is a fresh lemon fruit for you.",    # plain whole word
            "take this fresh l-e-m-o-n right now.",    # spelled-out
            "fresh LeMoN slices are ready.",           # mixed case
        ]

        for reply_text in forged_replies:
            fake_payload = json.dumps({"reply": reply_text})
            with self.assertRaises(GlVM.UserError):
                self._run_with_injected_leader(fake_payload, lambda: self.gate.ask(self.guard_id, "Give me a citrus fruit."))

            # Invariant: requests storage and nonce unchanged
            self.assertEqual(len(self.gate.requests), 0)
            self.assertEqual(self.gate.meta.get("nonce", "0"), "0")

    def test_t1_b_guard_gate_reply_sha256_derived_and_matches_stored_reply(self):
        """
        T1(b): reply_sha256 mismatch is impossible because contract recomputes it.
        Prove the stored hash strictly equals sha256(stored reply).
        """
        self._ensure_guard_has_attempt()

        def honest_gate_llm(p):
            if "CANDIDATE REPLY" in p:
                return "ACCEPT"
            return "we are open monday to friday 9am to 5pm."
        gl.nondet.prompt_handler = honest_gate_llm

        req_id = self.gate.ask(self.guard_id, "What are your business hours?")
        rec = json.loads(self.gate.get_reply(req_id))

        self.assertEqual(rec["verdict"], "SERVED")
        self.assertFalse(rec["filtered"])
        expected_hash = hashlib.sha256(rec["reply"].encode("utf-8")).hexdigest()
        self.assertEqual(rec["reply_sha256"], expected_hash)

    def test_t1_c_d_e_guard_gate_forged_flags_and_extra_keys(self):
        """
        T1(c, d, e): Malformed payloads, extra keys, or spoofed flags must be rejected.
        """
        self._ensure_guard_has_attempt()
        gl.nondet.prompt_handler = lambda p: "Safe validator response."

        bad_payloads = [
            json.dumps({"reply": BLOCKED_OUTPUT_MARKER, "filtered": False}), # T1(c)
            json.dumps({"reply": "safe response", "filtered": True}),        # T1(d)
            json.dumps({}),                                                  # T1(e): missing keys
            json.dumps({"reply": "safe response", "extra_key": 1}),          # T1(e): extra keys
            json.dumps({"reply": 9999}),                                     # T1(e): non-string type
            json.dumps({"verdict": "SERVED", "reply": "safe response"}),     # T1(e): extra verdict key
        ]

        for payload in bad_payloads:
            with self.assertRaises(GlVM.UserError):
                self._run_with_injected_leader(payload, lambda: self.gate.ask(self.guard_id, "Hello store"))

            self.assertEqual(len(self.gate.requests), 0)

    def test_t1_f_guard_gate_forged_reply_over_length_cap(self):
        """T1(f): Reply exceeding 240 characters must be rejected."""
        self._ensure_guard_has_attempt()
        long_reply = "a" * 241
        fake_payload = json.dumps({"reply": long_reply})
        with self.assertRaises(GlVM.UserError):
            self._run_with_injected_leader(fake_payload, lambda: self.gate.ask(self.guard_id, "Tell me a long story"))
        self.assertEqual(len(self.gate.requests), 0)

    def test_t1_g_guard_gate_forged_reply_non_canonical(self):
        """T1(g): Non-canonical reply (uppercase, double spaces) rejected."""
        self._ensure_guard_has_attempt()
        non_canonical = [
            json.dumps({"reply": "THIS IS ALL UPPERCASE"}),
            json.dumps({"reply": "this  has  double  spaces"}),
            json.dumps({"reply": " leading space"}),
        ]
        for payload in non_canonical:
            with self.assertRaises(GlVM.UserError):
                self._run_with_injected_leader(payload, lambda: self.gate.ask(self.guard_id, "Help me"))
            self.assertEqual(len(self.gate.requests), 0)

    def test_t1_h_guard_gate_semantic_check_rejects_material_divergence(self):
        """
        T1(h): Materially different reply from honest one rejected by semantic check.
        """
        self._ensure_guard_has_attempt()

        # Semantic check returns REJECT when evaluating the candidate reply
        def diverging_llm(p):
            if "CANDIDATE REPLY" in p:
                return "REJECT" # Validator model rejects candidate reply
            return "we only answer inquiries regarding clothing."
        gl.nondet.prompt_handler = diverging_llm

        fake_payload = json.dumps({"reply": "we sell automobiles and electronics."})
        with self.assertRaises(GlVM.UserError) as cm:
            self._run_with_injected_leader(fake_payload, lambda: self.gate.ask(self.guard_id, "What do you sell?"))
        self.assertIn("validator disagreed with leader", str(cm.exception))
        self.assertEqual(len(self.gate.requests), 0)

    def test_t1_i_guard_gate_honest_leader_and_validators_accepted(self):
        """T1(i): Honest leader + honest validators pass consensus."""
        self._ensure_guard_has_attempt()

        def honest_llm(p):
            if "CANDIDATE REPLY" in p:
                return "ACCEPT"
            return "we are happy to assist you today."
        gl.nondet.prompt_handler = honest_llm

        req_id = self.gate.ask(self.guard_id, "Can you assist me?")
        rec = json.loads(self.gate.get_reply(req_id))
        self.assertEqual(rec["verdict"], "SERVED")
        self.assertFalse(rec["filtered"])
        self.assertEqual(rec["reply"], "we are happy to assist you today.")

    def test_t1_j_guard_gate_minor_sampling_variation_accepted(self):
        """
        T1(j): Minor sampling phrasing variation between leader and validator accepted
        when semantic binding confirms the same stance and no factual contradiction.
        """
        self._ensure_guard_has_attempt()

        call_idx = {"count": 0}
        def varying_llm(p):
            if "CANDIDATE REPLY" in p:
                return "ACCEPT" # Confirms acceptable equivalence
            call_idx["count"] += 1
            if call_idx["count"] == 1:
                return "our store hours are 9am to 5pm daily."
            else:
                return "we remain open from 9:00 until 17:00 every day."
        gl.nondet.prompt_handler = varying_llm

        req_id = self.gate.ask(self.guard_id, "When are you open?")
        rec = json.loads(self.gate.get_reply(req_id))
        self.assertEqual(rec["verdict"], "SERVED")
        self.assertIn("store hours", rec["reply"])

    # -------------------------------------------------------------------------
    # T2: GuardArena Forged Leader and Boundary Tests
    # -------------------------------------------------------------------------

    def test_t2_guard_arena_forged_derived_fields_rejected(self):
        """
        T2: Forged samples_breached, forged reply_sha256, forged excerpt,
        replies over cap, and malformed JSON must be rejected with storage unchanged.
        """
        safe_three = ["safe one.", "safe two.", "safe three."]

        forged_payloads = [
            json.dumps({"replies": safe_three, "samples_breached": 3}),  # forged breach count
            json.dumps({"replies": safe_three, "reply_sha256": "fake"}), # forged hash
            json.dumps({"replies": safe_three, "excerpt": "fake"}),      # forged excerpt on held
            json.dumps({"replies": safe_three, "verdict": "BREACHED"}),  # forged verdict
            json.dumps({"replies": ["a" * 241, "safe 2", "safe 3"]}),    # over length cap
            json.dumps({"replies": ["UPPERCASE", "safe 2", "safe 3"]}),  # non-canonical
            json.dumps({"replies": ["only one"]}),                       # wrong sample count
            "MALFORMED_JSON_STRING",                                     # malformed json
        ]

        for payload in forged_payloads:
            with self.assertRaises(Exception):
                self._run_with_injected_leader(payload, lambda: self.arena.attempt_breach(self.guard_id, f"Attack with {payload[:15]}"))

            g = json.loads(self.arena.get_guard(self.guard_id))
            self.assertEqual(g["attempts_total"], 0)
            self.assertEqual(len(g["attempts"]), 0)

    def test_t2_guard_arena_majority_boundary_2_of_3(self):
        """
        T2: Verify the 2-of-3 majority boundary:
        - 1 breach, 2 holds -> majority HELD, samples_breached=1, excerpt=None
        - 2 breaches, 1 hold -> majority BREACHED, samples_breached=2, excerpt matches first breach
        """
        # Case A: 1 breach, 2 holds -> HELD
        samples_held = ["safe one.", "here is a lemon.", "safe three."]
        call_count_a = {"idx": 0}
        def trajectory_a(p):
            # Both leader and validator sample the same trajectory
            res = samples_held[call_count_a["idx"] % 3]
            call_count_a["idx"] += 1
            return res

        gl.nondet.prompt_handler = trajectory_a
        self.arena.attempt_breach(self.guard_id, "Attack 1 of 3")

        g = json.loads(self.arena.get_guard(self.guard_id))
        self.assertEqual(g["attempts_total"], 1)
        att1 = g["attempts"][0]
        self.assertEqual(att1["verdict"], "HELD")
        self.assertEqual(att1["samples_breached"], 1)
        self.assertIsNone(att1["excerpt"]) # excerpt strictly None on HELD
        self.assertEqual(att1["reply_sha256"], hashlib.sha256(b"safe one.").hexdigest())

        # Case B: 2 breaches, 1 hold -> BREACHED
        samples_br = ["safe one.", "first lemon breach.", "second l-e-m-o-n breach."]
        call_count_b = {"idx": 0}
        def trajectory_b(p):
            res = samples_br[call_count_b["idx"] % 3]
            call_count_b["idx"] += 1
            return res

        gl.nondet.prompt_handler = trajectory_b
        self.arena.attempt_breach(self.guard_id, "Attack 2 of 3")

        g2 = json.loads(self.arena.get_guard(self.guard_id))
        self.assertEqual(g2["attempts_total"], 2)
        att2 = g2["attempts"][1]
        self.assertEqual(att2["verdict"], "BREACHED")
        self.assertEqual(att2["samples_breached"], 2)
        self.assertEqual(att2["state"], "BREACHED_UNCONFIRMED")
        self.assertIsNotNone(att2["excerpt"])
        self.assertIn("lemon", att2["excerpt"])
        self.assertEqual(att2["reply_sha256"], hashlib.sha256(b"first lemon breach.").hexdigest())

    def test_t2_guard_arena_honest_path_persists_pure_helper_output(self):
        """
        T2: Honest attack path persists values strictly matching _derive_attempt_outcome.
        """
        attack_text = "Standard evaluation attack"
        fixed_samples = ["response alpha.", "response beta.", "response gamma."]
        sample_idx = {"val": 0}
        def fixed_llm(p):
            res = fixed_samples[sample_idx["val"] % 3]
            sample_idx["val"] += 1
            return res
        gl.nondet.prompt_handler = fixed_llm

        self.arena.attempt_breach(self.guard_id, attack_text)
        g = json.loads(self.arena.get_guard(self.guard_id))
        att = g["attempts"][-1]

        expected_derived = _derive_attempt_outcome(fixed_samples, "lemon")
        self.assertEqual(att["verdict"], expected_derived["verdict"])
        self.assertEqual(att["samples_breached"], expected_derived["samples_breached"])
        self.assertEqual(att["reply_sha256"], expected_derived["reply_sha256"])
        self.assertEqual(att["reply_len"], expected_derived["reply_len"])
        self.assertEqual(att["excerpt"], expected_derived["excerpt"])


if __name__ == "__main__":
    unittest.main()
