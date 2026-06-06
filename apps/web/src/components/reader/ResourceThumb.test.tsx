import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResourceThumb } from "./ResourceThumb";

describe("ResourceThumb", () => {
  it("renders the real YouTube frame and a play affordance for a video", () => {
    render(
      <ResourceThumb
        kind="video"
        url="https://www.youtube.com/watch?v=cGqMFk20Sco"
        title="Accuracy and Fluency"
      />,
    );

    const image = screen.getByRole("img", { name: "Accuracy and Fluency" });
    expect(image).toHaveAttribute("src", "https://i.ytimg.com/vi/cGqMFk20Sco/hqdefault.jpg");
    // explicit dimensions reserve space (no layout shift)
    expect(image).toHaveAttribute("width", "320");
    expect(image).toHaveAttribute("height", "180");
  });

  it("shows a skeleton placeholder until the thumbnail loads, then removes it", () => {
    const { container } = render(
      <ResourceThumb kind="video" url="https://www.youtube.com/watch?v=cGqMFk20Sco" title="V" />,
    );
    const image = container.querySelector("img");
    expect(image).toBeInTheDocument();
    // Before load: skeleton + play overlay are both rendered (aria-hidden decoration).
    const hiddenBefore = container.querySelectorAll('[aria-hidden="true"]').length;

    fireEvent.load(image!);

    // After load: the skeleton placeholder is gone (one fewer aria-hidden decoration).
    expect(container.querySelectorAll('[aria-hidden="true"]').length).toBeLessThan(hiddenBefore);
  });

  it("parses youtu.be short links", () => {
    render(<ResourceThumb kind="video" url="https://youtu.be/_fzTPg08Q64" title="Shadowing" />);

    expect(screen.getByRole("img", { name: "Shadowing" })).toHaveAttribute(
      "src",
      "https://i.ytimg.com/vi/_fzTPg08Q64/hqdefault.jpg",
    );
  });

  it("falls back to a kind glyph when the thumbnail fails to load", () => {
    render(
      <ResourceThumb kind="video" url="https://www.youtube.com/watch?v=cGqMFk20Sco" title="V" />,
    );
    const image = screen.getByRole("img", { name: "V" });

    fireEvent.error(image);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("VIDEO")).toBeInTheDocument();
  });

  it("shows a kind glyph (no image) for a non-YouTube video", () => {
    render(<ResourceThumb kind="video" url="https://vimeo.com/12345" title="On Vimeo" />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("VIDEO")).toBeInTheDocument();
  });

  it("shows a kind glyph and no play affordance for a non-video resource", () => {
    const { container } = render(
      <ResourceThumb kind="docs" url="https://ies.ed.gov/guide.pdf" title="Guide" />,
    );

    expect(screen.getByText("DOCS")).toBeInTheDocument();
    expect(container.querySelector("svg")).toBeNull(); // the play triangle is video-only
  });
});
