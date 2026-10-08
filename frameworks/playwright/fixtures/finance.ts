/**
 * Playwright finance fixtures.
 * Finance constraint: all monetary values use Decimal, never number.
 * All PII is synthetic.
 */

import { test as base } from "@playwright/test";
import { Decimal } from "decimal.js";
import {
  syntheticAmount,
  syntheticCorrelationId,
  syntheticDOB,
  syntheticEmail,
  syntheticIBAN,
  syntheticName,
  syntheticTransactionId,
} from "../helpers/finance";

export type FinanceFixtures = {
  correlationId: string;
  validUser: {
    name: string;
    email: string;
    dob: Date;
    iban: string;
  };
  validTransaction: {
    transactionId: string;
    amount: Decimal;
    currency: string;
    iban: string;
    reference: string;
  };
  authToken: string;
};

export const test = base.extend<FinanceFixtures>({
  correlationId: async ({}, use) => {
    await use(syntheticCorrelationId());
  },

  validUser: async ({}, use) => {
    const name = syntheticName();
    await use({
      name,
      email: syntheticEmail(name),
      dob: syntheticDOB(18),
      iban: syntheticIBAN("GB"),
    });
  },

  validTransaction: async ({ validUser }, use) => {
    await use({
      transactionId: syntheticTransactionId(),
      amount: syntheticAmount("0.01", "9999.99", "GBP"),
      currency: "GBP",
      iban: validUser.iban,
      reference: "QE-PW-TEST",
    });
  },

  authToken: async ({}, use) => {
    const token = process.env.TEST_AUTH_TOKEN ?? "replace-me";
    await use(token);
  },
});

export { expect } from "@playwright/test";
