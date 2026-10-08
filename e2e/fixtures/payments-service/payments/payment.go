// Package payments validates and processes financial payments.
// Monetary values are always decimal.Decimal — never float64.
package payments

import (
	"errors"

	"github.com/shopspring/decimal"
)

// currencyDecimals maps ISO 4217 codes to their permitted decimal places.
var currencyDecimals = map[string]int32{
	"GBP": 2, "USD": 2, "EUR": 2, "JPY": 0, "BHD": 3,
}

// maxAmount is the largest payment the platform accepts.
const maxAmount = "999999999.99"

// Sentinel errors. Error strings double as machine error codes.
var (
	ErrInvalidAmount       = errors.New("INVALID_AMOUNT")
	ErrUnsupportedCurrency = errors.New("UNSUPPORTED_CURRENCY")
	ErrPrecisionExceeded   = errors.New("PRECISION_EXCEEDED")
	ErrMissingIBAN         = errors.New("MISSING_IBAN")
)

// Payment is a single payment instruction.
type Payment struct {
	Amount      decimal.Decimal
	Currency    string
	CrossBorder bool
	IBAN        string
}

// ValidateAmount checks an amount against currency rules.
// Returns nil when valid, or a sentinel error code.
func ValidateAmount(amount decimal.Decimal, currency string) error {
	dp, ok := currencyDecimals[currency]
	if !ok {
		return ErrUnsupportedCurrency
	}
	if amount.Sign() <= 0 {
		return ErrInvalidAmount
	}
	max, _ := decimal.NewFromString(maxAmount)
	if amount.GreaterThan(max) {
		return ErrInvalidAmount
	}
	// Exponent is negative for fractional places; -3 means 3 dp.
	if amount.Exponent() < -dp {
		return ErrPrecisionExceeded
	}
	return nil
}

// ProcessPayment validates a payment and enforces cross-border rules.
func ProcessPayment(p Payment) error {
	if err := ValidateAmount(p.Amount, p.Currency); err != nil {
		return err
	}
	if p.CrossBorder && p.IBAN == "" {
		return ErrMissingIBAN
	}
	return nil
}
