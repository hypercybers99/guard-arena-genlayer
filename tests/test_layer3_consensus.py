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
import genlayer
from genlayer import gl, GlVM, Return
from contracts.GuardArena import GuardArena
from contracts.GuardGate import GuardGate


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
            # First 3 calls are leader, next 3 calls are validator
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
        A faulty or adversarial leader returns invalid JSON or forged verdict.
        The validator must inspect and reject instead of blindly accepting.
        """
        # Save original run_nondet
        original_run_nondet = gl.vm.run_nondet

        try:
            # 1. Leader returns non-JSON garbage
            def corrupt_leader_run_nondet(leader_fn, validator_fn):
                fake_res = Return("MALFORMED_GARBAGE_NOT_JSON")
                ok = validator_fn(fake_res)
                if not ok:
                    raise GlVM.UserError("validator disagreed with leader")
                return fake_res.calldata

            gl.vm.run_nondet = corrupt_leader_run_nondet
            with self.assertRaises(Exception): # UserError or json decode error
                self.arena.attempt_breach(self.guard_id, "Attack against bad leader")

            # 2. Leader returns forged verdict 'PASS_EVERYTHING'
            def forged_verdict_run_nondet(leader_fn, validator_fn):
                fake_res = Return(json.dumps({"verdict": "FORGED_SUPER_BREACH"}))
                ok = validator_fn(fake_res)
                if not ok:
                    raise GlVM.UserError("validator disagreed with leader")
                return fake_res.calldata

            gl.vm.run_nondet = forged_verdict_run_nondet
            with self.assertRaises(GlVM.UserError) as cm:
                self.arena.attempt_breach(self.guard_id, "Attack against forged leader")
            self.assertIn("validator disagreed with leader", str(cm.exception))

        finally:
            gl.vm.run_nondet = original_run_nondet


if __name__ == "__main__":
    unittest.main()
