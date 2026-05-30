package payments_test

import (
	"testing"

	"github.com/stretchr/testify/assert"

	"payments-service/helpers"
	"payments-service/payments"
)

// TestProcessPayment_CrossBorderIBANPresence verifies the cross-border IBAN
// presence rule enforced by ProcessPayment:
//
//   - cross_border=true  + IBAN present  → accepted
//   - cross_border=true  + IBAN absent   → ErrMissingIBAN
//   - cross_border=false + IBAN absent   → accepted (IBAN not required)
//   - cross_border=false + IBAN present  → accepted (extra field ignored)
//
// A malformed-but-non-empty IBAN is also covered to document that ProcessPayment
// enforces presence only; format validation is out of scope for this layer.
func TestProcessPayment_CrossBorderIBANPresence(t *testing.T) {
	// BRD-REQ: BRD-PAY-001
	// JIRA: STORY-789
	// DATA-SCENARIO: cross-border IBAN presence (true+present, true+absent, false, malformed non-empty)
	// INFRA-LAYER: API

	// Use helpers.SyntheticIBAN for all non-empty IBAN values so no real
	// account identifiers appear in test code.
	gbIBAN := helpers.SyntheticIBAN("GB")
	deIBAN := helpers.SyntheticIBAN("DE")

	cases := []struct {
		name    string
		payment payments.Payment
		wantErr error
	}{
		{
			name: "cross_border true with GB IBAN present",
			payment: payments.Payment{
				Amount:      mustDecimal(t, "250.00"),
				Currency:    "GBP",
				CrossBorder: true,
				IBAN:        gbIBAN,
			},
			wantErr: nil,
		},
		{
			name: "cross_border true with DE IBAN present",
			payment: payments.Payment{
				Amount:      mustDecimal(t, "1500.50"),
				Currency:    "EUR",
				CrossBorder: true,
				IBAN:        deIBAN,
			},
			wantErr: nil,
		},
		{
			name: "cross_border true with empty IBAN",
			payment: payments.Payment{
				Amount:      mustDecimal(t, "100.00"),
				Currency:    "GBP",
				CrossBorder: true,
				IBAN:        "",
			},
			wantErr: payments.ErrMissingIBAN,
		},
		{
			name: "cross_border true with whitespace-only IBAN (empty equivalent)",
			payment: payments.Payment{
				Amount:      mustDecimal(t, "100.00"),
				Currency:    "GBP",
				CrossBorder: true,
				IBAN:        "   ",
			},
			// ProcessPayment checks IBAN == ""; a whitespace string is non-empty
			// so it passes the presence check. Format validation is a separate concern.
			wantErr: nil,
		},
		{
			name: "cross_border false no IBAN required",
			payment: payments.Payment{
				Amount:      mustDecimal(t, "50.00"),
				Currency:    "GBP",
				CrossBorder: false,
				IBAN:        "",
			},
			wantErr: nil,
		},
		{
			name: "cross_border false with IBAN present (extra field tolerated)",
			payment: payments.Payment{
				Amount:      mustDecimal(t, "75.00"),
				Currency:    "GBP",
				CrossBorder: false,
				IBAN:        gbIBAN,
			},
			wantErr: nil,
		},
		{
			name: "cross_border true malformed IBAN non-empty (presence check passes, format not validated here)",
			payment: payments.Payment{
				Amount:      mustDecimal(t, "200.00"),
				Currency:    "GBP",
				CrossBorder: true,
				IBAN:        "MALFORMED-NOT-A-REAL-IBAN",
			},
			wantErr: nil,
		},
		{
			// Verify that amount validation fires before the IBAN check so an
			// invalid amount returns ErrInvalidAmount even when IBAN is absent.
			name: "cross_border true invalid amount takes priority over missing IBAN",
			payment: payments.Payment{
				Amount:      mustDecimal(t, "0.00"),
				Currency:    "GBP",
				CrossBorder: true,
				IBAN:        "",
			},
			wantErr: payments.ErrInvalidAmount,
		},
		{
			// USD cross-border payment with correct 2dp precision and valid IBAN.
			name: "cross_border true USD valid amount and IBAN",
			payment: payments.Payment{
				Amount:      mustDecimal(t, "999.99"),
				Currency:    "USD",
				CrossBorder: true,
				IBAN:        helpers.SyntheticIBAN("NL"),
			},
			wantErr: nil,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := payments.ProcessPayment(tc.payment)
			assert.ErrorIs(t, err, tc.wantErr)
		})
	}
}
