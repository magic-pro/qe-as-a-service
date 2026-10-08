package payments_test

import (
	"testing"

	"github.com/shopspring/decimal"
)

// mustDecimal parses a decimal string in test code.
// Calls t.Fatalf on parse failure so a typo in a literal surfaces immediately
// rather than silently producing a zero-value amount.
// Never use float64 in monetary test helpers — all amounts go through this helper.
func mustDecimal(t *testing.T, s string) decimal.Decimal {
	t.Helper()
	d, err := decimal.NewFromString(s)
	if err != nil {
		t.Fatalf("mustDecimal: invalid literal %q: %v", s, err)
	}
	return d
}
