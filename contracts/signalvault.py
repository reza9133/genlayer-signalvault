# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json
import typing
import re

MAX_URL_CHARS = 2048

def _is_immutable(url: str) -> bool:
    if not isinstance(url, str):
        return False
    u = url.strip()
    if not u or len(u) > MAX_URL_CHARS:
        return False
    if u.startswith("ipfs://") or u.startswith("ar://"):
        return True
    if u.startswith("https://raw.githubusercontent.com/"):
        parts = u.split("/")
        if len(parts) >= 6 and len(parts[5]) == 40:
            return True
    return False

def _sanitize_page(raw: typing.Any) -> str:
    if not isinstance(raw, str):
        return ""
    t = re.sub(r"<\s*/?\s*UNTRUSTED(?:\s+[^>]*)?\s*>", "", raw, flags=re.IGNORECASE)
    return " ".join(t.strip().split())

# Extracted non-deterministic logic to ensure Linter reachability
def _adjudicate_nondet(target: str, channels_json: str) -> str:
    channels = json.loads(channels_json)
    readings = []
    
    for i, ch in enumerate(channels):
        try:
            url = ch.get("url", "")
            res = gl.nondet.web.get(url)
            raw = res.body.decode("utf-8", errors="replace") if res.body else ""
            page = _sanitize_page(raw)
            
            prompt = f"""Strict signal detector. Output ONLY valid JSON.

Target signal: "{target}"

Page text:
<UNTRUSTED>
{page}
</UNTRUSTED>

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
            res_llm = gl.nondet.exec_prompt(prompt, response_format="json")
            rel = str(res_llm.get("relevance", "NONE")).upper()
            conf = str(res_llm.get("confirmation", "NONE")).upper()
            if rel not in ("HIGH", "MEDIUM", "LOW", "NONE"):
                rel = "NONE"
            if conf not in ("STRONG", "WEAK", "NONE"):
                conf = "NONE"
            rec = f"C{i}:F0:R{rel}:C{conf}"
            readings.append(rec)
        except Exception:
            readings.append(f"C{i}:F1:RNONE:CNONE")

    vector = "|".join(readings)
    strong = vector.count(":CSTRONG")
    high = vector.count(":RHIGH")
    decision = "CONFIRMED" if (strong >= 2 and high >= 2) else "ACTIVE"
    return f"{decision}|{strong}|{high}|{vector}"


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
    is_initialized: bool # Added boolean to track initialization

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
        self.is_initialized = False # Set to false initially

    @gl.public.write.payable
    def create_vault(self, target_signal: str, channels_json: str, beneficiaries_json: str, challenge_days: u16):
        # FIX 1: Prevent re-initialization
        if self.is_initialized:
            raise Exception("Vault is already initialized")

        if gl.message.value < u256(10**16):
            raise Exception("Minimum 0.01 GEN required")
        
        channels = json.loads(channels_json)
        if len(channels) < 3 or len(channels) > 5:
            raise Exception("Need 3 to 5 channels")
            
        for ch in channels:
             if not _is_immutable(ch.get("url", "")):
                  raise gl.vm.UserError("Security Error: Channel URLs must be immutable (IPFS, Arweave, or fixed-commit GitHub).")

        # Basic validation of beneficiaries format
        beneficiaries = json.loads(beneficiaries_json)
        if not isinstance(beneficiaries, list) or len(beneficiaries) == 0:
             raise Exception("Must specify at least one beneficiary")
        
        total_share = sum(b.get("share", 0) for b in beneficiaries)
        if total_share != 100:
             raise Exception("Beneficiary shares must sum to 100")

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
        self.is_initialized = True # Mark as initialized

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
        channels_j = self.channels_json

        def leader_fn() -> str:
            return _adjudicate_nondet(target, channels_j)

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            try:
                leader_str = str(leader_result.calldata)
                my_str = _adjudicate_nondet(target, channels_j)
                return my_str == leader_str
            except Exception:
                return False

        result_str = str(gl.vm.run_nondet_unsafe(leader_fn, validator_fn))

        parts = result_str.split("|", 3)
        if len(parts) < 4:
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
            
        caller = str(gl.message.sender_address).lower()
        beneficiaries = json.loads(self.beneficiaries_json)
        
        # FIX 2: Implement authorization and allocation
        caller_share = 0
        for b in beneficiaries:
             if str(b.get("address", "")).lower() == caller:
                  caller_share = b.get("share", 0)
                  # Remove them from the list or set share to 0 so they can't claim twice
                  b["share"] = 0
                  break
                  
        if caller_share == 0:
             raise Exception("Caller is not a beneficiary or has already claimed")

        # Calculate their portion based on the *initial* total balance
        # If we use self.balance, it will decrease with each claim, messing up percentages
        # We need to track total claimable amount if there are multiple beneficiaries.
        # For simplicity, assuming balance represents 100% of the funds to distribute.
        
        # Note: If the vault allows top-ups, we'd need a separate variable for total_locked
        # Since there is no top_up function here, self.balance is static until claims start.
        # To handle multiple claims properly without a total_locked variable, 
        # we calculate based on the current balance and adjust.
        # A better approach is calculating the absolute amount based on initial balance.
        # We'll use a simplified assumption that self.balance holds the total.
        
        # We must calculate amount before reducing balance.
        # To support multiple claims correctly, we should calculate based on total value.
        # But since we are updating beneficiaries_json to set share to 0, 
        # we can use the share percentage safely.
        
        # Since self.balance decreases, calculating percentage of current balance is wrong.
        # E.g., 50% of 100 is 50. Balance is now 50. 
        # Next person with 50% claims 50% of 50 = 25. Incorrect.
        
        # Let's use a simpler mechanism since we don't have total_locked.
        # We will iterate and find the sum of REMAINING shares.
        remaining_shares = sum(b.get("share", 0) for b in beneficiaries)
        
        # If they are the last to claim, they get everything left to avoid rounding dust
        if remaining_shares == 0:
             amount = self.balance
        else:
             # This is a basic proportional calculation based on remaining shares
             # It ensures we don't calculate based on the original 100% if balance changed
             amount = u256(int(self.balance) * caller_share // (caller_share + remaining_shares))

        self.beneficiaries_json = json.dumps(beneficiaries)
        self.balance = self.balance - amount
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
