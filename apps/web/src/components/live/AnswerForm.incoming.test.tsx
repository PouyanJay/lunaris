import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AnswerForm } from "./AnswerForm";
import { IncomingAnswerContext } from "./IncomingAnswerContext";

it("appends a new recording to typed work without submitting or duplicating it", () => {
  const answer = vi.fn();
  const form = <AnswerForm criterion={null} busy={false} onAnswer={answer} />;
  const { rerender } = render(
    <IncomingAnswerContext.Provider value={null}>{form}</IncomingAnswerContext.Provider>,
  );
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "My first thought." } });
  const draft = { id: "recording-1", text: "And the spoken continuation." };
  rerender(<IncomingAnswerContext.Provider value={draft}>{form}</IncomingAnswerContext.Provider>);
  expect(screen.getByRole("textbox")).toHaveValue(
    "My first thought.\nAnd the spoken continuation.",
  );
  rerender(
    <IncomingAnswerContext.Provider value={{ ...draft }}>{form}</IncomingAnswerContext.Provider>,
  );
  expect(screen.getByRole("textbox")).toHaveValue(
    "My first thought.\nAnd the spoken continuation.",
  );
  expect(answer).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(answer).toHaveBeenCalledWith("My first thought.\nAnd the spoken continuation.");
});
it("preserves typed work on overflow until the learner explicitly replaces it", () => {
  const form = <AnswerForm criterion={null} busy={false} onAnswer={vi.fn()} />;
  const { rerender } = render(
    <IncomingAnswerContext.Provider value={null}>{form}</IncomingAnswerContext.Provider>,
  );
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "x".repeat(3999) } });
  rerender(
    <IncomingAnswerContext.Provider value={{ id: "recording", text: "Spoken answer." }}>
      {form}
    </IncomingAnswerContext.Provider>,
  );
  expect(screen.getByRole("textbox")).toHaveValue("x".repeat(3999));
  fireEvent.click(screen.getByRole("button", { name: "Use recording instead" }));
  expect(screen.getByRole("textbox")).toHaveValue("Spoken answer.");
});
