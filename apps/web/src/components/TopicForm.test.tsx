import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { TopicForm } from "./TopicForm";

/** The heading and action label now come from the parent, which owns the mode. Studio's are the
 *  defaults here so each test states only what it is actually about. */
const HEADING = { lead: "What do you want to ", accent: "learn", tail: "?" };
const SUBMIT = "Generate course";

describe("TopicForm", () => {
  it("submits the trimmed topic", () => {
    const onSubmit = vi.fn();
    render(
      <TopicForm
        value="  merge sort  "
        onChange={vi.fn()}
        onSubmit={onSubmit}
        heading={HEADING}
        submitLabel={SUBMIT}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onSubmit).toHaveBeenCalledWith("merge sort");
  });

  it("reports the controlled value as the user types", () => {
    const onChange = vi.fn();
    render(
      <TopicForm
        value=""
        onChange={onChange}
        onSubmit={vi.fn()}
        heading={HEADING}
        submitLabel={SUBMIT}
      />,
    );

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "graphs" } });

    expect(onChange).toHaveBeenCalledWith("graphs");
  });

  it("surfaces an error and does not submit when the topic is empty", () => {
    const onSubmit = vi.fn();
    render(
      <TopicForm
        value="   "
        onChange={vi.fn()}
        onSubmit={onSubmit}
        heading={HEADING}
        submitLabel={SUBMIT}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/enter a topic/i);
  });

  it("dismisses the empty-topic error as soon as the user types", () => {
    function Harness() {
      const [value, setValue] = useState("");
      return (
        <TopicForm
          value={value}
          onChange={setValue}
          onSubmit={vi.fn()}
          heading={HEADING}
          submitLabel={SUBMIT}
        />
      );
    }
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    expect(screen.getByRole("alert")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "g" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("submits when the form is submitted by any means", () => {
    const onSubmit = vi.fn();
    render(
      <TopicForm
        value="graphs"
        onChange={vi.fn()}
        onSubmit={onSubmit}
        heading={HEADING}
        submitLabel={SUBMIT}
      />,
    );

    fireEvent.submit(screen.getByLabelText("Topic").closest("form")!);

    expect(onSubmit).toHaveBeenCalledWith("graphs");
  });

  it("generates straight from an example chip", () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();
    render(
      <TopicForm
        value=""
        onChange={onChange}
        onSubmit={onSubmit}
        heading={HEADING}
        submitLabel={SUBMIT}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "How merge sort works" }));

    // The chip pre-fills the field and builds in one click.
    expect(onChange).toHaveBeenCalledWith("How merge sort works");
    expect(onSubmit).toHaveBeenCalledWith("How merge sort works");
  });

  // The field is a textarea, so Enter would insert a newline by default. The composer inverts that
  // deliberately, and the inversion has to be verified in BOTH directions or it is not verified at
  // all: a test that only fires the form's submit event never touches the key handler.

  it("submits on Enter, because a topic is one line of intent", () => {
    const onSubmit = vi.fn();
    render(
      <TopicForm
        value="graphs"
        onChange={vi.fn()}
        onSubmit={onSubmit}
        heading={HEADING}
        submitLabel={SUBMIT}
      />,
    );

    fireEvent.keyDown(screen.getByLabelText("Topic"), { key: "Enter" });

    expect(onSubmit).toHaveBeenCalledWith("graphs");
  });

  it("does not submit on Shift+Enter, which breaks the line instead", () => {
    const onSubmit = vi.fn();
    render(
      <TopicForm
        value="graphs"
        onChange={vi.fn()}
        onSubmit={onSubmit}
        heading={HEADING}
        submitLabel={SUBMIT}
      />,
    );

    fireEvent.keyDown(screen.getByLabelText("Topic"), { key: "Enter", shiftKey: true });

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
