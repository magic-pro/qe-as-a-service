package tests

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"qe-framework-golang/helpers"
)

// Example: replace with real HTTP client calls to your service.

func TestSyntheticAmountPrecision(t *testing.T) {
	amount := helpers.SyntheticAmount("0.01", "9999.99", "GBP")
	assert.Equal(t, 2, int(amount.Exponent()*-1), "GBP must have 2 decimal places")
	assert.True(t, amount.GreaterThanOrEqual(decimal.NewFromString("0.01")))
}

func TestSyntheticAmountJPY(t *testing.T) {
	amount := helpers.SyntheticAmount("1", "10000", "JPY")
	assert.Equal(t, 0, int(amount.Exponent()*-1), "JPY must have 0 decimal places")
}

func TestBoundaryAmounts(t *testing.T) {
	cases := []struct {
		name     string
		amount   decimal.Decimal
		wantSign int // -1, 0, 1
	}{
		{"min GBP", decimal.NewFromString("0.01"), 1},
		{"zero", decimal.Zero, 0},
		{"negative", decimal.NewFromString("-1.00"), -1},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := tc.amount.Sign()
			assert.Equal(t, tc.wantSign, got)
		})
	}
}

func TestSyntheticUserFields(t *testing.T) {
	name := helpers.SyntheticName()
	require.NotEmpty(t, name)

	email := helpers.SyntheticEmail(name)
	assert.Contains(t, email, "@qe.invalid", "synthetic email must use @qe.invalid domain")

	iban := helpers.SyntheticIBAN("GB")
	assert.Len(t, iban, 22, "GB IBAN must be 22 chars")
	assert.Equal(t, "GB", iban[:2])
}

func TestSyntheticTransactionID(t *testing.T) {
	id1 := helpers.SyntheticTransactionID()
	id2 := helpers.SyntheticTransactionID()
	assert.NotEmpty(t, id1)
	assert.NotEqual(t, id1, id2, "transaction IDs must be unique")
}
