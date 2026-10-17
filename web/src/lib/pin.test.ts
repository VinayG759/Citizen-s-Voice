import { expect, test } from "vitest";
import { pinHtml, pinSize } from "./pin";

test("a pin is a teardrop in the urgency colour, its point on the spot", () => {
  const html = pinHtml("#b91c1c", 1, false);
  expect(html).toContain("<svg");
  expect(html).toContain('fill="#b91c1c"');
  const [w, h] = pinSize(false);
  expect(h).toBeGreaterThan(w); // taller than wide: the point sits at the bottom centre
});

test("a pin reported by several people shows how many; a single report shows no badge", () => {
  expect(pinHtml("#b45309", 4, false)).toContain(">4<");
  expect(pinHtml("#b45309", 1, false)).not.toContain("pin__count");
  expect(pinHtml("#b45309", 120, false)).toContain(">99+<");
});

test("the selected pin is bigger", () => {
  expect(pinSize(true)[1]).toBeGreaterThan(pinSize(false)[1]);
  expect(pinHtml("#b45309", 1, true)).toContain("pin--selected");
});

test("a colour that is not a plain hex value never reaches the markup", () => {
  expect(pinHtml('red" onload="x', 1, false)).not.toContain("onload");
});
