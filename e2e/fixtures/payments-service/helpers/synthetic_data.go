// Package helpers provides finance-safe synthetic data generators.
// Never use real PII. All monetary values use decimal.Decimal, never float64.
package helpers

import (
	"fmt"
	"math/rand"
	"strings"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"
)

var currencyDecimals = map[string]int32{
	"GBP": 2, "USD": 2, "EUR": 2, "JPY": 0, "BHD": 3,
}

// SyntheticAmount returns a random Decimal within range, respecting currency precision.
func SyntheticAmount(minStr, maxStr, currency string) decimal.Decimal {
	dp, ok := currencyDecimals[currency]
	if !ok {
		dp = 2
	}
	lo, _ := decimal.NewFromString(minStr)
	hi, _ := decimal.NewFromString(maxStr)
	diff := hi.Sub(lo)
	frac := decimal.NewFromFloat(rand.Float64()) //nolint:gosec
	return lo.Add(diff.Mul(frac)).RoundBank(dp)
}

// SyntheticCurrencyCode returns a random valid ISO 4217 currency code.
func SyntheticCurrencyCode() string {
	codes := []string{"GBP", "USD", "EUR", "JPY", "BHD"}
	return codes[rand.Intn(len(codes))] //nolint:gosec
}

// SyntheticIBAN returns a plausible IBAN format string (not checksum-valid).
func SyntheticIBAN(country string) string {
	lengths := map[string]int{"GB": 22, "DE": 22, "FR": 27, "NL": 18}
	length, ok := lengths[country]
	if !ok {
		length = 22
	}
	chars := "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	b := make([]byte, length-2)
	for i := range b {
		b[i] = chars[rand.Intn(len(chars))] //nolint:gosec
	}
	return country + string(b)
}

// SyntheticName returns a non-real full name.
func SyntheticName() string {
	firsts := []string{"Alex", "Jordan", "Morgan", "Taylor", "Casey"}
	lasts := []string{"Smith", "Jones", "Williams", "Brown", "Davies"}
	return firsts[rand.Intn(len(firsts))] + " " + lasts[rand.Intn(len(lasts))] //nolint:gosec
}

// SyntheticEmail returns a non-real, format-valid email using the @qe.invalid domain.
func SyntheticEmail(name string) string {
	local := strings.ToLower(strings.ReplaceAll(name, " ", "."))
	return fmt.Sprintf("%s.%s@qe.invalid", local, uuid.New().String()[:4])
}

// SyntheticTransactionID returns a UUID v4 string.
func SyntheticTransactionID() string { return uuid.New().String() }

// SyntheticCorrelationID returns a UUID v4 string.
func SyntheticCorrelationID() string { return uuid.New().String() }
