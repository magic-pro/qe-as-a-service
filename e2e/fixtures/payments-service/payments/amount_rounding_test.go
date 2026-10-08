package payments_test

import (
	"testing"

	"github.com/stretchr/testify/assert"

	"payments-service/payments"
)

// TestAmountRounding_HalfUp verifies that decimal.Round (half-up) produces the
// correct amount at the sub-unit boundary for each supported currency.
//
// Callers are responsible for rounding raw input BEFORE passing it to
// ValidateAmount. This test asserts both the rounded value itself and that
// the rounded result subsequently passes ValidateAmount (when positive).
func TestAmountRounding_HalfUp(t *testing.T) {
	// BRD-REQ: BRD-PAY-001
	// JIRA: STORY-789
	// DATA-SCENARIO: amount-rounding (half-up at currency sub-unit boundary)
	// INFRA-LAYER: API

	cases := []struct {
		name     string
		raw      string // raw input string with extra precision
		currency string
		dp       int32
		expected string // expected StringFixed output after Round
	}{
		// GBP — 2dp; half-up at the 3rd decimal position
		{"GBP 0.005 → 0.01 (half-up)", "0.005", "GBP", 2, "0.01"},
		{"GBP 0.004 → 0.00 (round-down)", "0.004", "GBP", 2, "0.00"},
		{"GBP 0.014 → 0.01 (round-down)", "0.014", "GBP", 2, "0.01"},
		{"GBP 0.015 → 0.02 (half-up)", "0.015", "GBP", 2, "0.02"},
		{"GBP 0.995 → 1.00 (half-up carry)", "0.995", "GBP", 2, "1.00"},
		// USD — 2dp
		{"USD 0.005 → 0.01 (half-up)", "0.005", "USD", 2, "0.01"},
		{"USD 0.004 → 0.00 (round-down)", "0.004", "USD", 2, "0.00"},
		// JPY — 0dp; half-up at the 1st decimal position
		{"JPY 0.5 → 1 (half-up)", "0.5", "JPY", 0, "1"},
		{"JPY 0.4 → 0 (round-down)", "0.4", "JPY", 0, "0"},
		// BHD — 3dp; half-up at the 4th decimal position
		{"BHD 1.2345 → 1.235 (half-up)", "1.2345", "BHD", 3, "1.235"},
		{"BHD 1.2344 → 1.234 (round-down)", "1.2344", "BHD", 3, "1.234"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			raw := mustDecimal(t, tc.raw)
			rounded := raw.Round(tc.dp)

			assert.Equal(t, tc.expected, rounded.StringFixed(tc.dp),
				"Round(%d) of %s", tc.dp, tc.raw)

			// Positive rounded amounts must clear ValidateAmount without error.
			if rounded.Sign() > 0 {
				err := payments.ValidateAmount(rounded, tc.currency)
				assert.NoError(t, err,
					"rounded amount %s should pass ValidateAmount for %s",
					rounded.StringFixed(tc.dp), tc.currency)
			}
		})
	}
}

// TestAmountRounding_Bankers verifies that RoundBank (banker's / half-to-even
// rounding) rounds midpoint values to the nearest even last digit, producing
// different results from half-up when the last-kept digit is even.
//
// Pattern: last-kept digit even → round DOWN; odd → round UP.
func TestAmountRounding_Bankers(t *testing.T) {
	// BRD-REQ: BRD-PAY-001
	// JIRA: STORY-789
	// DATA-SCENARIO: amount-rounding (bankers half-to-even rounding)
	// INFRA-LAYER: API

	cases := []struct {
		name     string
		raw      string
		dp       int32
		expected string // expected StringFixed output after RoundBank
	}{
		// last-kept digit is 0 (even) → round down
		{"0.005 bankers → 0.00 (0 is even)", "0.005", 2, "0.00"},
		// last-kept digit is 1 (odd) → round up
		{"0.015 bankers → 0.02 (1 is odd)", "0.015", 2, "0.02"},
		// last-kept digit is 2 (even) → round down
		{"0.025 bankers → 0.02 (2 is even)", "0.025", 2, "0.02"},
		// last-kept digit is 3 (odd) → round up
		{"0.035 bankers → 0.04 (3 is odd)", "0.035", 2, "0.04"},
		// last-kept digit is 4 (even) → round down
		{"0.045 bankers → 0.04 (4 is even)", "0.045", 2, "0.04"},
		// last-kept digit is 5 (odd) → round up
		{"0.055 bankers → 0.06 (5 is odd)", "0.055", 2, "0.06"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			raw := mustDecimal(t, tc.raw)
			rounded := raw.RoundBank(tc.dp)
			assert.Equal(t, tc.expected, rounded.StringFixed(tc.dp),
				"RoundBank(%d) of %s", tc.dp, tc.raw)
		})
	}
}
