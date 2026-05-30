package payments_test

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"

	"payments-service/payments"
)

func TestValidateAmount_GBPBoundaries(t *testing.T) {
	// BRD-REQ: BRD-PAY-001
	// JIRA: STORY-789
	// DATA-SCENARIO: amount-boundary
	// INFRA-LAYER: API

	cases := []struct {
		name    string
		amount  string
		wantErr error
	}{
		{"min positive GBP", "0.01", nil},
		{"zero", "0", payments.ErrInvalidAmount},
		{"negative", "-1.00", payments.ErrInvalidAmount},
		{"max valid", "999999999.99", nil},
		{"too many places", "0.001", payments.ErrPrecisionExceeded},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			amt, _ := decimal.NewFromString(tc.amount)
			err := payments.ValidateAmount(amt, "GBP")
			assert.ErrorIs(t, err, tc.wantErr)
		})
	}
}
