import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { TopicForm } from "./TopicForm";

describe("TopicForm", () => {
  it("submits the trimmed topic", () => {
    const onSubmit = vi.fn();
    render(<TopicForm value="  merge sort  " onChange={vi.fn()} onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onSubmit).toHaveBeenCalledWith("merge sort");
  });

  it("reports the controlled value as the user types", () => {
    const onChange = vi.fn();
    render(<TopicForm value="" onChange={onChange} onSubmit={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "graphs" } });

    expect(onChange).toHaveBeenCalledWith("graphs");
  });

  it("surfaces an error and does not submit when the topic is empty", () => {
    const onSubmit = vi.fn();
    render(<TopicForm value="   " onChange={vi.fn()} onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/enter a topic/i);
  });

  it("dismisses the empty-topic error as soon as the user types", () => {
    function Harness() {
      const [value, setValue] = useState("");
      return <TopicForm value={value} onChange={setValue} onSubmit={vi.fn()} />;
    }
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));
    expect(screen.getByRole("alert")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "g" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("submits on Enter (the single-field keyboard path)", () => {
    const onSubmit = vi.fn();
    render(<TopicForm value="graphs" onChange={vi.fn()} onSubmit={onSubmit} />);

    fireEvent.submit(screen.getByLabelText("Topic").closest("form")!);

    expect(onSubmit).toHaveBeenCalledWith("graphs");
  });

  it("generates straight from an example chip", () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();
    render(<TopicForm value="" onChange={onChange} onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: "How merge sort works" }));

    // The chip pre-fills the field and builds in one click.
    expect(onChange).toHaveBeenCalledWith("How merge sort works");
    expect(onSubmit).toHaveBeenCalledWith("How merge sort works");
  });
});
