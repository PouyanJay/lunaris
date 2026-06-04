import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TopicForm } from "./TopicForm";

describe("TopicForm", () => {
  it("submits the trimmed topic", () => {
    const onGenerate = vi.fn();
    render(<TopicForm onGenerate={onGenerate} onPersonalize={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "  merge sort  " } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).toHaveBeenCalledWith("merge sort");
  });

  it("surfaces an error and does not submit when the topic is empty", () => {
    const onGenerate = vi.fn();
    render(<TopicForm onGenerate={onGenerate} onPersonalize={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/enter a topic/i);
  });

  it("generates straight from an example chip", () => {
    const onGenerate = vi.fn();
    render(<TopicForm onGenerate={onGenerate} onPersonalize={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "How merge sort works" }));

    expect(onGenerate).toHaveBeenCalledWith("How merge sort works");
  });

  it("opts into personalize with the trimmed topic, not generating", () => {
    const onGenerate = vi.fn();
    const onPersonalize = vi.fn();
    render(<TopicForm onGenerate={onGenerate} onPersonalize={onPersonalize} />);

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "  merge sort  " } });
    fireEvent.click(screen.getByRole("button", { name: /personalize before building/i }));

    expect(onPersonalize).toHaveBeenCalledWith("merge sort");
    expect(onGenerate).not.toHaveBeenCalled();
  });

  it("surfaces the empty-topic error when personalizing without a topic", () => {
    const onPersonalize = vi.fn();
    render(<TopicForm onGenerate={vi.fn()} onPersonalize={onPersonalize} />);

    fireEvent.click(screen.getByRole("button", { name: /personalize before building/i }));

    expect(onPersonalize).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/enter a topic/i);
  });
});
