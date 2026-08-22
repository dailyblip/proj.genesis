import importlib.util
import pathlib

p = pathlib.Path(__file__).parent / "worker.py"
spec = importlib.util.spec_from_file_location("cw", p)
cw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cw)

assert cw.reward_usdc({"price_usdc": "0.03"}) == 0.03
assert cw.reward_usdc({"price": 30000}) == 0.03
assert cw.reward_usdc({"price": "$5.00"}) == 5.0

assert cw.deterministic_deliverable({"title": "Create a glossary of agent economy terms"})
assert cw.deterministic_deliverable({"title": "Write a JSON schema validator for agent profiles"})
assert cw.deterministic_deliverable({"title": "Build a simple API rate limiter", "description": "Implement in Python"})
assert cw.deterministic_deliverable({"title": "Research an obscure topic"}) is None

assert cw.deterministic_deliverable({"title": "Welcome to Clawlancer! Introduce yourself, SomeOtherAgent"}) is None

assert cw.transaction_id({"transaction_id": "abc"}) == "abc"
assert cw.transaction_id({"transaction": {"id": "def"}}) == "def"

print("Clawlancer worker tests passed")
