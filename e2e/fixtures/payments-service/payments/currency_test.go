package payments_test

import (
	"testing"

	"github.com/stretchr/testify/assert"

	"payments-service/payments"
)

// TestValidateAmount_CurrencySupport verifies that ValidateAmount accepts every
// supported ISO 4217 currency code and rejects unsupported or malformed codes
// with ErrUnsupportedCurrency.
//
// This covers the currency-unsupported scenario from the data-type-map and
// acts as a regression guard if the supported-currency list changes.
func TestValidateAmount_CurrencySupport(t *testing.T) {
	// BRD-REQ: BRD-PAY-001
	// JIRA: STORY-789
	// DATA-SCENARIO: currency-unsupported (ZZZ, empty, lowercase, unknown code)
	// INFRA-LAYER: API

	// A valid two-decimal amount used across all currency cases; the test is
	// about the currency code, not the amount value.
	validAmount := mustDecimal(t, "100.00")

	cases := []struct {
		name     string
		currency string
		wantErr  error
	}{
		// ── Supported currencies ────────────────────────────────────────────
		{"supported GBP", "GBP", nil},
		{"supported USD", "USD", nil},
		{"supported EUR", "EUR", nil},
		// JPY and BHD use non-standard decimal places; 100.00 has 2dp which
		// exceeds JPY's 0dp limit → ErrPrecisionExceeded, not Unsupported.
		// This also confirms the currency IS recognised before the dp check fires.
		{"supported JPY precision error not unsupported", "JPY", payments.ErrPrecisionExceeded},
		{"supported BHD 2dp valid within 3dp limit", "BHD", nil},

		// ── Unsupported / invalid currency codes ───────────────────────────
		{"unsupported ZZZ", "ZZZ", payments.ErrUnsupportedCurrency},
		{"unsupported XYZ", "XYZ", payments.ErrUnsupportedCurrency},
		{"empty string", "", payments.ErrUnsupportedCurrency},
		// ISO 4217 codes are uppercase; lowercase must be rejected.
		{"lowercase gbp", "gbp", payments.ErrUnsupportedCurrency},
		{"mixed-case Gbp", "Gbp", payments.ErrUnsupportedCurrency},
		{"numeric string 840", "840", payments.ErrUnsupportedCurrency}, // numeric USD code
		{"whitespace only", "   ", payments.ErrUnsupportedCurrency},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := payments.ValidateAmount(validAmount, tc.currency)
			assert.ErrorIs(t, err, tc.wantErr)
		})
	}
}
