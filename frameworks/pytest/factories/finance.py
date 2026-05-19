"""Finance-safe synthetic data factories. Never use real PII."""

import random
import string
import uuid
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal


# --- Monetary ---

CURRENCY_DECIMALS: dict[str, int] = {
    "GBP": 2, "USD": 2, "EUR": 2, "AUD": 2, "CAD": 2,
    "JPY": 0, "BHD": 3, "KWD": 3, "OMR": 3,
}


def synthetic_amount(
    min_val: str = "0.01",
    max_val: str = "9999.99",
    currency: str = "GBP",
) -> Decimal:
    dp = CURRENCY_DECIMALS.get(currency, 2)
    quantize_str = Decimal(10) ** -dp
    lo = Decimal(min_val)
    hi = Decimal(max_val)
    raw = lo + Decimal(str(random.uniform(float(lo), float(hi))))
    return raw.quantize(quantize_str, rounding=ROUND_HALF_UP)


def synthetic_currency_code() -> str:
    return random.choice(list(CURRENCY_DECIMALS.keys()))


# --- Account identifiers ---

def synthetic_bsb() -> str:
    """Valid BSB format: XXX-XXX"""
    digits = "".join(random.choices(string.digits, k=6))
    return f"{digits[:3]}-{digits[3:]}"


def synthetic_iban(country: str = "GB") -> str:
    """Plausible IBAN format per country (not checksum-valid — use for format tests only)."""
    lengths = {"GB": 22, "DE": 22, "FR": 27, "NL": 18, "AU": 20}
    length = lengths.get(country, 22)
    body = "".join(random.choices(string.ascii_uppercase + string.digits, k=length - 2))
    return f"{country}{body}"


def synthetic_swift() -> str:
    """Valid-format SWIFT/BIC (8 or 11 chars)."""
    bank = "".join(random.choices(string.ascii_uppercase, k=4))
    country = random.choice(["GB", "DE", "FR", "US", "AU"])
    location = "".join(random.choices(string.ascii_uppercase + string.digits, k=2))
    return f"{bank}{country}{location}"


def synthetic_sort_code() -> str:
    """UK sort code: XX-XX-XX"""
    digits = "".join(random.choices(string.digits, k=6))
    return f"{digits[:2]}-{digits[2:4]}-{digits[4:]}"


# --- PII (synthetic, non-real) ---

_FIRST_NAMES = ["Alex", "Jordan", "Morgan", "Taylor", "Casey", "Riley", "Avery"]
_LAST_NAMES = ["Smith", "Jones", "Williams", "Brown", "Davies", "Wilson", "Evans"]


def synthetic_name() -> str:
    return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"


def synthetic_email(name: str | None = None) -> str:
    local = (name or synthetic_name()).lower().replace(" ", ".")
    domain = random.choice(["example.com", "test.invalid", "qe.invalid"])
    return f"{local}.{uuid.uuid4().hex[:4]}@{domain}"


def synthetic_dob(min_age: int = 18, max_age: int = 80) -> date:
    today = date.today()
    start = today - timedelta(days=max_age * 365)
    end = today - timedelta(days=min_age * 365)
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def synthetic_phone() -> str:
    return f"+44{''.join(random.choices(string.digits, k=10))}"


# --- Transaction / reference ---

def synthetic_transaction_id() -> str:
    return str(uuid.uuid4())


def synthetic_payment_reference() -> str:
    """Alphanumeric, max 35 chars."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=random.randint(6, 35)))


def synthetic_correlation_id() -> str:
    return str(uuid.uuid4())


# --- Document (KYC) ---

_DOC_FORMATS = {
    "passport": lambda: "".join(random.choices(string.ascii_uppercase, k=2))
    + "".join(random.choices(string.digits, k=7)),
    "driving_licence": lambda: "".join(random.choices(string.ascii_uppercase, k=5))
    + "".join(random.choices(string.digits, k=6)),
    "national_id": lambda: "".join(random.choices(string.digits, k=9)),
}


def synthetic_document_number(doc_type: str = "passport") -> str:
    generator = _DOC_FORMATS.get(doc_type, _DOC_FORMATS["passport"])
    return generator()


def synthetic_document_expiry(days_from_now: int = 365) -> date:
    return date.today() + timedelta(days=days_from_now)
