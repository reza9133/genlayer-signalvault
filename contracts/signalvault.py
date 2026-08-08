# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json

class SignalVault(gl.Contract):
    owner: Address
    target_signal: str
    channels_json: str
    beneficiaries_json: str
    balance: u256
    state: str
    challenge_days: u16
    confirmed_at: u256
    last_vector: str
    last_decision: str
    last_strong: u256
    last_high: u256

    def __init__(self):
        self.owner = gl.message.sender_address
        self.target_signal = ""
        self.channels_json = "[]"
        self.beneficiaries_json = "[]"
        self.balance = u256(0)
        self.state = "ACTIVE"
        self.challenge_days = u16(14)
        self.confirmed_at = u256(0)
        self.last_vector = ""
        self.last_decision = ""
        self.last_strong = u256(0)
        self.last_high = u256(0)

    @gl.public.write.payable
    def create_vault(self, target_signal: str, channels_json: str, beneficiaries_json: str, challenge_days: u16):
        if gl.message.value < u256(10**16):
            raise Exception("Minimum 0.01 GEN required")
        channels = json.loads(channels_json)
        if len(channels) < 3 or len(channels) > 5:
            raise Exception("Need 3 to 5 channels")
        self.owner = gl.message.sender_address
        self.target_signal = target_signal
        self.channels_json = channels_json
        self.beneficiaries_json = beneficiaries_json
        self.balance = gl.message.value
        self.state = "ACTIVE"
        self.challenge_days = challenge_days
        self.confirmed_at = u256(0)
        self.last_vector = ""
        self.last_decision = ""
        self.last_strong = u256(0)
        self.last_high = u256(0)

    @gl.public.write
    def open_check(self):
        if self.state != "ACTIVE":
            raise Exception("Vault is not ACTIVE")
        self.state = "PENDING"

    @gl.public.write
    def adjudicate(self):
        if self.state != "PENDING":
            raise Exception("No pending check")

        target = self.target_signal
        channels = json.loads(self.channels_json)

        def leader_fn() -> str:
            readings = []
            for i, ch in enumerate(channels):
                try:
                    page = gl.nondet.web.render(ch["url"], mode="text")
                    truncated = "1" if len(page) > 18000 else "0"
                    page = page[:18000]
                    prompt = f"""Strict signal detector. Output ONLY valid JSON.

Target signal: "{target}"

Page text:
{page}

Rules (must follow exactly):
- relevance = "HIGH" only if the page clearly and directly discusses the exact target signal.
- relevance = "MEDIUM" if related but not exact.
- relevance = "LOW" or "NONE" otherwise.
- confirmation = "STRONG" only if there is clear positive official confirmation, announcement, or release of the target signal.
- confirmation = "WEAK" if vague or indirect.
- confirmation = "NONE" otherwise.

Return exactly:
{{"fetch":"OK","relevance":"HIGH|MEDIUM|LOW|NONE","confirmation":"STRONG|WEAK|NONE"}}
"""
                    res = gl.nondet.exec_prompt(prompt, response_format="json")
                    rel = str(res.get("relevance", "NONE")).upper()
                    conf = str(res.get("confirmation", "NONE")).upper()
                    if rel not in ("HIGH", "MEDIUM", "LOW", "NONE"):
                        rel = "NONE"
                    if conf not in ("STRONG", "WEAK", "NONE"):
                        conf = "NONE"
                    rec = f"C{i}:F0:R{rel}:C{conf}:X{truncated}"
                    readings.append(rec)
                except Exception:
                    readings.append(f"C{i}:F1:RNONE:CNONE:X0")

            vector = "|".join(readings)
            strong = vector.count(":CSTRONG")
            high = vector.count(":RHIGH")
            decision = "CONFIRMED" if (strong >= 2 and high >= 2) else "ACTIVE"
            # Return a simple canonical string (no dict)
            return f"{decision}|{strong}|{high}|{vector}"

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            try:
                leader_str = str(leader_result.calldata)
                my_str = leader_fn()
                # Exact match on the whole canonical string
                return my_str == leader_str
            except Exception:
                return False

        # Consensus
        result_str = str(gl.vm.run_nondet_unsafe(leader_fn, validator_fn))

        # Parse the simple string
        parts = result_str.split("|", 3)
        if len(parts) < 4:
            # Fallback safety
            self.state = "ACTIVE"
            self.last_decision = "ACTIVE"
            self.last_vector = result_str
            return

        decision = parts[0]
        strong = int(parts[1])
        high = int(parts[2])
        vector = parts[3]

        self.last_vector = vector
        self.last_decision = decision
        self.last_strong = u256(strong)
        self.last_high = u256(high)

        if decision == "CONFIRMED":
            self.state = "CONFIRMED"
            try:
                self.confirmed_at = u256(gl.message_raw["datetime"])
            except Exception:
                self.confirmed_at = u256(0)
        else:
            self.state = "ACTIVE"

    @gl.public.write
    def veto(self):
        if gl.message.sender_address != self.owner:
            raise Exception("Only owner")
        if self.state == "CONFIRMED":
            self.state = "ACTIVE"
            self.confirmed_at = u256(0)

    @gl.public.write
    def release(self):
        if self.state != "CONFIRMED":
            raise Exception("Not confirmed")
        now = u256(gl.message_raw.get("datetime", 0))
        if now < self.confirmed_at + u256(self.challenge_days * 86400):
            raise Exception("Challenge window still active")
        self.state = "RELEASED"

    @gl.public.write
    def claim(self):
        if self.state != "RELEASED":
            raise Exception("Not released")
        if self.balance == u256(0):
            raise Exception("Nothing to claim")
        amount = self.balance
        self.balance = u256(0)
        gl.transfer(gl.message.sender_address, amount)

    @gl.public.view
    def get_state(self) -> str:
        return self.state

    @gl.public.view
    def get_balance(self) -> u256:
        return self.balance

    @gl.public.view
    def get_target(self) -> str:
        return self.target_signal

    @gl.public.view
    def get_last_vector(self) -> str:
        return self.last_vector

    @gl.public.view
    def get_last_decision(self) -> str:
        return self.last_decision

    @gl.public.view
    def get_owner(self) -> Address:
        return self.owner

    @gl.public.view
    def get_full_info(self) -> str:
        return (
            f"state={self.state} | decision={self.last_decision} | "
            f"strong={self.last_strong} | high={self.last_high} | "
            f"balance={self.balance} | target={self.target_signal}"
        )
