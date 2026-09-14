import { fireEvent, render, screen } from "@testing-library/react";
import { it, expect, vi } from "vitest";
import { AnswerForm } from "./AnswerForm";

it("lets a learner edit a transcribed draft before using the ordinary answer callback", () => {
  const onAnswer = vi.fn();
  render(
    <AnswerForm
      criterion="Explain scaling"
      busy={false}
      onAnswer={onAnswer}
      initialAnswer="Scaling doubles"
    />,
  );
  const draft = screen.getByRole("textbox", { name: "Your answer" });
  expect(draft).toHaveValue("Scaling doubles");
  expect(onAnswer).not.toHaveBeenCalled();
  fireEvent.change(draft, { target: { value: "Doubling x doubles y." } });
  fireEvent.submit(draft.closest("form")!);
  expect(onAnswer).toHaveBeenCalledTimes(1);
  expect(onAnswer).toHaveBeenCalledWith("Doubling x doubles y.");
});
