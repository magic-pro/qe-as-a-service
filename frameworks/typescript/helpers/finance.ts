/**
 * Finance-safe synthetic data helpers for TypeScript tests.
 * Monetary values use Decimal (decimal.js) — never number/float.
 * All PII is synthetic — never real customer data.
 */

import { Decimal } from "decimal.js";
import { faker } from "@faker-js/faker";

// Monetary precision per ISO 4217
const CURRENCY_DECIMALS: Record<string, number> = {
  GBP: 2, USD: 2, EUR: 2, AUD: 2, CAD: 2,
  JPY: 0, BHD: 3, KWD: 3, OMR: 3,
};

Decimal.set({ rounding: Decimal.ROUND_HALF_UP });

export function syntheticAmount(
  min = "0.01",
  max = "9999.99",
  currency = "GBP"
): Decimal {
  const dp = CURRENCY_DECIMALS[currency] ?? 2;
  const lo = new Decimal(min);
  const hi = new Decimal(max);
  const raw = lo.plus(hi.minus(lo).times(Decimal.random()));
  return raw.toDecimalPlaces(dp);
}

export function syntheticCurrencyCode(): string {
  const codes = Object.keys(CURRENCY_DECIMALS);
  return codes[Math.floor(Math.random() * codes.length)];
}

export function syntheticIBAN(country = "GB"): string {
  const lengths: Record<string, number> = { GB: 22, DE: 22, FR: 27, NL: 18 };
  const length = lengths[country] ?? 22;
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  const body = Array.from({ length: length - 2 }, () =>
    chars[Math.floor(Math.random() * chars.length)]
  ).join("");
  return `${country}${body}`;
}

export function syntheticSWIFT(): string {
  const bank = faker.string.alpha({ length: 4, casing: "upper" });
  const country = faker.helpers.arrayElement(["GB", "DE", "FR", "US", "AU"]);
  const location = faker.string.alphanumeric({ length: 2, casing: "upper" });
  return `${bank}${country}${location}`;
}

export function syntheticName(): string {
  return faker.person.fullName();
}

export function syntheticEmail(name?: string): string {
  const local = (name ?? syntheticName()).toLowerCase().replace(/\s+/g, ".");
  return `${local}.${faker.string.alphanumeric(4)}@qe.invalid`;
}

export function syntheticDOB(minAge = 18, maxAge = 80): Date {
  const now = new Date();
  const lo = new Date(now.getFullYear() - maxAge, now.getMonth(), now.getDate());
  const hi = new Date(now.getFullYear() - minAge, now.getMonth(), now.getDate());
  return faker.date.between({ from: lo, to: hi });
}

export function syntheticTransactionId(): string {
  return faker.string.uuid();
}

export function syntheticCorrelationId(): string {
  return faker.string.uuid();
}

export function syntheticPaymentReference(): string {
  return faker.string.alphanumeric({ length: faker.number.int({ min: 6, max: 35 }), casing: "upper" });
}

export function syntheticDocumentNumber(docType = "passport"): string {
  switch (docType) {
    case "passport":
      return faker.string.alpha({ length: 2, casing: "upper" }) + faker.string.numeric(7);
    case "driving_licence":
      return faker.string.alpha({ length: 5, casing: "upper" }) + faker.string.numeric(6);
    default:
      return faker.string.numeric(9);
  }
}

// Boundary value helpers
export const BOUNDARY = {
  amountMinGBP: new Decimal("0.01"),
  amountZero: new Decimal("0.00"),
  amountNegative: new Decimal("-1.00"),
  amountMaxGBP: new Decimal("999999999.99"),
  amountRoundingBoundary: new Decimal("0.005"), // must round to 0.01 for GBP
  jpyMin: new Decimal("1"),
  jpyZero: new Decimal("0"),
} as const;
