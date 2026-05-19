"""Shared pytest fixtures. Override in your repo's conftest.py as needed."""

import os
from decimal import Decimal

import httpx
import pytest

from factories.finance import (
    synthetic_amount,
    synthetic_correlation_id,
    synthetic_dob,
    synthetic_email,
    synthetic_iban,
    synthetic_name,
    synthetic_transaction_id,
)


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("API_BASE_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def http_client(base_url: str) -> httpx.Client:
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def correlation_id() -> str:
    return synthetic_correlation_id()


@pytest.fixture
def auth_headers(correlation_id: str) -> dict[str, str]:
    token = os.environ.get("TEST_AUTH_TOKEN", "test-token-replace-me")
    return {
        "Authorization": f"Bearer {token}",
        "X-Correlation-ID": correlation_id,
        "X-Request-ID": synthetic_transaction_id(),
    }


@pytest.fixture
def valid_user() -> dict:
    name = synthetic_name()
    return {
        "name": name,
        "email": synthetic_email(name),
        "dob": synthetic_dob(min_age=18).isoformat(),
        "account_iban": synthetic_iban("GB"),
    }


@pytest.fixture
def valid_transaction(valid_user: dict) -> dict:
    return {
        "transaction_id": synthetic_transaction_id(),
        "amount": str(synthetic_amount("0.01", "9999.99", "GBP")),  # string → Decimal on service side
        "currency": "GBP",
        "account_iban": valid_user["account_iban"],
        "reference": "QE-TEST-REF",
    }


# Finance boundary fixtures

@pytest.fixture(params=[
    ("0.01", "GBP", True),   # min valid
    ("0.00", "GBP", False),  # zero — invalid for most flows
    ("-1.00", "GBP", False), # negative
    ("1", "JPY", True),      # JPY: 0dp
    ("0.5", "JPY", False),   # JPY: no decimal places
    (None, "GBP", False),    # null
])
def amount_boundary(request: pytest.FixtureRequest):
    amount_str, currency, is_valid = request.param
    return {
        "amount": Decimal(amount_str) if amount_str is not None else None,
        "currency": currency,
        "is_valid": is_valid,
    }
