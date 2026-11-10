import { expect, test } from "vitest";
import { addFact, duplicateFact, errorsAt, linksTo, move, removeFact, setIn, slug, type DraftCase } from "../lib/case-draft";

const draft: DraftCase = {
  id: "c", facts: [
    { id: "quantity", content: "A litre a day", disclosure: "on_direct_question", asked_about: ["how much"], domain: "alcohol" },
    { id: "withdrawal", content: "Shakes", disclosure: "on_direct_question", asked_about: ["withdrawal"], domain: "alcohol" },
  ],
  tasks: [{ id: "ask-withdrawal", description: "Ask about withdrawal", domain: "alcohol", evidence_fact: "withdrawal" }],
  questions: [{ id: "q", text: "Is that bad?", after_fact: "withdrawal" }],
};

test("setIn is immutable and undefined removes a key so defaults stay unwritten", () => {
  const next = setIn(draft, ["facts", 0, "key"], true);
  expect(next.facts?.[0]?.key).toBe(true);
  expect(draft.facts?.[0]?.key).toBeUndefined();
  expect(Object.keys(setIn(next, ["facts", 0, "key"], undefined).facts?.[0] ?? {})).not.toContain("key");
});

test("new and duplicated facts get stable, collision-checked IDs", () => {
  expect(slug("Morning drinking!", [])).toBe("morning-drinking");
  expect(slug("quantity", ["quantity", "quantity-2"])).toBe("quantity-3");
  const added = addFact(draft, "How much");
  expect(added.facts?.at(-1)?.id).toBe("how-much");
  expect(added.facts?.at(-1)?.asked_about).toEqual(["How much"]);
  const copy = duplicateFact(draft, 0);
  expect(copy.facts?.map((f) => f?.id)).toEqual(["quantity", "quantity-copy", "withdrawal"]);
});

test("moving keeps every item and stops at the ends", () => {
  expect(move(draft, "facts", 0, 1).facts?.map((f) => f?.id)).toEqual(["withdrawal", "quantity"]);
  expect(move(draft, "facts", 0, -1)).toBe(draft);
});

test("deleting a referenced fact repairs its links", () => {
  expect(linksTo(draft, "withdrawal")).toEqual({ tasks: ["ask-withdrawal"], questions: ["q"] });
  const next = removeFact(draft, "withdrawal");
  expect(next.facts?.map((f) => f?.id)).toEqual(["quantity"]);
  expect(next.tasks?.[0]).not.toHaveProperty("evidence_fact");  // now self-review
  expect(next.questions).toEqual([]);
});

test("errors are found by their exact field path", () => {
  const errors = [{ loc: ["facts", 1, "content"], message: "Field required" }, { loc: ["title"], message: "x" }];
  expect(errorsAt(errors, ["facts", 1, "content"])).toEqual(["Field required"]);
  expect(errorsAt(errors, ["facts", 0, "content"])).toEqual([]);
});
