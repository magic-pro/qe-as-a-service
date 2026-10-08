package payments_test

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"

	"payments-service/payments"
)

// TestValidateAmount_BoundaryExtended extends the seed TestValidateAmount_GBPBoundaries
// with the two cases not covered there: the Go zero-value struct (null equivalent)
// and amounts that exceed the platform maximum.
func TestValidateAmount_BoundaryExtended(t *testing.T) {
	// BRD-REQ: BRD-PAY-001
	// JIRA: STORY-789
	// DATA-SCENARIO: amount-boundary (null/decimal.Decimal{} zero-value struct, max-exceeded)
	// INFRA-LAYER: API

	cases := []struct {
		name    string
		amount  decimal.Decimal
		wantErr error
	}{
		{
			// decimal.Decimal{} is the Go zero value: value=nil, exp=0.
			// Sign() returns 0 for a nil-value decimal, so ValidateAmount
			// must treat it as invalid (same rule as explicit 0).
			name:    "null equivalent zero-value struct decimal.Decimal{}",
			amount:  decimal.Decimal{},
			wantErr: payments.ErrInvalidAmount,
		},
		{
			// One cent above the hard platform ceiling of 999999999.99.
			name:    "max exceeded by one cent 1000000000.00",
			amount:  mustDecimal(t, "1000000000.00"),
			wantErr: payments.ErrInvalidAmount,
		},
		{
			// Very large value well above the ceiling.
			name:    "max exceeded large value 9999999999.99",
			amount:  mustDecimal(t, "9999999999.99"),
			wantErr: payments.ErrInvalidAmount,
		},
		{
			// Confirm that the exact ceiling value itself remains valid
			// (boundary confirmation pairing the exceeded cases above).
			name:    "at exact max boundary 999999999.99",
			amount:  mustDecimal(t, "999999999.99"),
			wantErr: nil,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := payments.ValidateAmount(tc.amount, "GBP")
			assert.ErrorIs(t, err, tc.wantErr)
		})
	}
}
