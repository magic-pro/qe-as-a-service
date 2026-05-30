package payments_test

import (
	"testing"

	"github.com/stretchr/testify/assert"

	"payments-service/payments"
)

// TestValidateAmount_CurrencyPrecision verifies that ValidateAmount enforces
// the ISO 4217 decimal-place rules for every supported currency:
//
//	GBP / USD / EUR → 2 dp
//	JPY             → 0 dp  (whole units only)
//	BHD             → 3 dp
//
// Amounts with more decimal places than the currency permits must be rejected
// with ErrPrecisionExceeded. Amounts with fewer (or equal) decimal places must
// pass when they are otherwise valid.
func TestValidateAmount_CurrencyPrecision(t *testing.T) {
	// BRD-REQ: BRD-PAY-001
	// JIRA: STORY-789
	// DATA-SCENARIO: amount-precision (per-currency decimal places GBP/USD/EUR 2dp, JPY 0dp, BHD 3dp)
	// INFRA-LAYER: API

	cases := []struct {
		name     string
		amount   string
		currency string
		wantErr  error
	}{
		// ── GBP (2 decimal places) ──────────────────────────────────────────
		{"GBP valid 2dp 12.34", "12.34", "GBP", nil},
		{"GBP valid 1dp 12.3", "12.3", "GBP", nil},
		{"GBP invalid 3dp 12.345", "12.345", "GBP", payments.ErrPrecisionExceeded},

		// ── USD (2 decimal places) ──────────────────────────────────────────
		{"USD valid 2dp 99.99", "99.99", "USD", nil},
		{"USD valid 1dp 99.9", "99.9", "USD", nil},
		{"USD invalid 3dp 99.999", "99.999", "USD", payments.ErrPrecisionExceeded},

		// ── EUR (2 decimal places) ──────────────────────────────────────────
		{"EUR valid 2dp 0.01", "0.01", "EUR", nil},
		{"EUR invalid 3dp 0.001", "0.001", "EUR", payments.ErrPrecisionExceeded},

		// ── JPY (0 decimal places — whole yen only) ─────────────────────────
		{"JPY valid integer 1000", "1000", "JPY", nil},
		{"JPY invalid 1dp 100.5", "100.5", "JPY", payments.ErrPrecisionExceeded},
		{"JPY invalid 2dp 100.12", "100.12", "JPY", payments.ErrPrecisionExceeded},

		// ── BHD (3 decimal places) ──────────────────────────────────────────
		{"BHD valid 3dp 1.234", "1.234", "BHD", nil},
		{"BHD valid 2dp 1.23", "1.23", "BHD", nil},
		{"BHD valid 1dp 1.2", "1.2", "BHD", nil},
		{"BHD invalid 4dp 1.2345", "1.2345", "BHD", payments.ErrPrecisionExceeded},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			amt := mustDecimal(t, tc.amount)
			err := payments.ValidateAmount(amt, tc.currency)
			assert.ErrorIs(t, err, tc.wantErr)
		})
	}
}
