import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Input } from "./Input";

describe("Input", () => {
  it("associates the label with the field", () => {
    render(<Input label="Email" type="email" />);
    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
  });

  it("is valid and undescribed without an error", () => {
    render(<Input label="Topic" />);
    const field = screen.getByLabelText("Topic");
    expect(field).not.toHaveAttribute("aria-invalid");
    expect(field).not.toHaveAttribute("aria-describedby");
  });

  it("marks the field invalid and announces the error message", () => {
    render(<Input label="Email" error="Enter a valid address" />);
    const field = screen.getByLabelText("Email");
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription("Enter a valid address");
    expect(screen.getByText("Enter a valid address")).toBeInTheDocument();
  });

  it("accepts typing and change handlers", () => {
    const onChange = vi.fn();
    render(<Input label="Topic" onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Topic"), {
      target: { value: "how a hash map works" },
    });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Topic")).toHaveValue("how a hash map works");
  });

  it("respects a caller-provided id for external label wiring", () => {
    render(<Input id="topic-input" aria-label="Topic" />);
    expect(screen.getByLabelText("Topic")).toHaveAttribute("id", "topic-input");
  });

  it("forwards its ref to the underlying input", () => {
    const ref = { current: null as HTMLInputElement | null };
    render(<Input ref={ref} label="Topic" />);
    expect(ref.current).toBe(screen.getByLabelText("Topic"));
  });
});
