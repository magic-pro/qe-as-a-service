// Package helpers provides finance-safe synthetic data generators for Go tests.
// Never use real PII. All monetary values use decimal.Decimal, never float64.
package helpers

import (
	"fmt"
	"math/rand"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"
)

var currencyDecimals = map[string]int32{
	"GBP": 2, "USD": 2, "EUR": 2, "AUD": 2, "CAD": 2,
	"JPY": 0, "BHD": 3, "KWD": 3, "OMR": 3,
}

// SyntheticAmount returns a random Decimal amount within range, respecting currency precision.
func SyntheticAmount(minStr, maxStr, currency string) decimal.Decimal {
	dp, ok := currencyDecimals[currency]
	if !ok {
		dp = 2
	}
	lo, _ := decimal.NewFromString(minStr)
	hi, _ := decimal.NewFromString(maxStr)
	diff := hi.Sub(lo)
	randFraction := decimal.NewFromFloat(rand.Float64()) //nolint:gosec
	raw := lo.Add(diff.Mul(randFraction))
	return raw.RoundBank(dp)
}

// SyntheticCurrencyCode returns a random valid ISO 4217 currency code.
func SyntheticCurrencyCode() string {
	codes := []string{"GBP", "USD", "EUR", "AUD", "JPY", "BHD"}
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

// SyntheticSWIFT returns a valid-format SWIFT/BIC code.
func SyntheticSWIFT() string {
	bank := randomUpper(4)
	countries := []string{"GB", "DE", "FR", "US", "AU"}
	country := countries[rand.Intn(len(countries))] //nolint:gosec
	location := randomUpper(2)
	return bank + country + location
}

// SyntheticBSB returns a valid-format Australian BSB.
func SyntheticBSB() string {
	return fmt.Sprintf("%03d-%03d", rand.Intn(1000), rand.Intn(1000)) //nolint:gosec
}

// SyntheticSortCode returns a valid-format UK sort code.
func SyntheticSortCode() string {
	return fmt.Sprintf("%02d-%02d-%02d",
		rand.Intn(100), rand.Intn(100), rand.Intn(100)) //nolint:gosec
}

// SyntheticName returns a non-real full name.
func SyntheticName() string {
	firsts := []string{"Alex", "Jordan", "Morgan", "Taylor", "Casey"}
	lasts := []string{"Smith", "Jones", "Williams", "Brown", "Davies"}
	return firsts[rand.Intn(len(firsts))] + " " + lasts[rand.Intn(len(lasts))] //nolint:gosec
}

// SyntheticEmail returns a non-real, format-valid email address.
func SyntheticEmail(name string) string {
	local := strings.ToLower(strings.ReplaceAll(name, " ", "."))
	return fmt.Sprintf("%s.%s@qe.invalid", local, uuid.New().String()[:4])
}

// SyntheticDOB returns a synthetic date of birth satisfying minimum age.
func SyntheticDOB(minAge, maxAge int) time.Time {
	now := time.Now()
	lo := now.AddDate(-maxAge, 0, 0)
	hi := now.AddDate(-minAge, 0, 0)
	delta := hi.Unix() - lo.Unix()
	return lo.Add(time.Duration(rand.Int63n(delta)) * time.Second) //nolint:gosec
}

// SyntheticDocumentNumber returns a format-valid (non-real) document number.
func SyntheticDocumentNumber(docType string) string {
	switch docType {
	case "passport":
		return randomUpper(2) + randomDigits(7)
	case "driving_licence":
		return randomUpper(5) + randomDigits(6)
	default:
		return randomDigits(9)
	}
}

// SyntheticTransactionID returns a UUID v4 string.
func SyntheticTransactionID() string { return uuid.New().String() }

// SyntheticCorrelationID returns a UUID v4 string.
func SyntheticCorrelationID() string { return uuid.New().String() }

// SyntheticPaymentReference returns a format-valid payment reference (max 35 chars).
func SyntheticPaymentReference() string {
	chars := "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	length := 6 + rand.Intn(30) //nolint:gosec
	b := make([]byte, length)
	for i := range b {
		b[i] = chars[rand.Intn(len(chars))] //nolint:gosec
	}
	return string(b)
}

func randomUpper(n int) string {
	chars := "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
	b := make([]byte, n)
	for i := range b {
		b[i] = chars[rand.Intn(len(chars))] //nolint:gosec
	}
	return string(b)
}

func randomDigits(n int) string {
	chars := "0123456789"
	b := make([]byte, n)
	for i := range b {
		b[i] = chars[rand.Intn(len(chars))] //nolint:gosec
	}
	return string(b)
}
