import { forwardRef } from "react";
import { Link, type LinkProps } from "react-router";

import { buttonClassName, type ButtonVariant } from "./buttonVariants";

type ButtonLinkProps = LinkProps & {
  variant?: ButtonVariant;
};

/** A destination that looks like an action.
 *
 *  The same skin as {@link Button}, over a real `<a>`: navigation must be a link so Cmd-click,
 *  middle-click, "open in new tab" and the browser's own context menu all work. A `<button>` that
 *  navigates takes all of that away, and a bare `<a>` wearing a button's layout class without the
 *  button's own styles is the other half of the same mistake (found in this rail's review).
 *
 *  Shares `Button.module.css` deliberately: one definition of what an action looks like, so a
 *  restyle reaches both at once. */
export const ButtonLink = forwardRef<HTMLAnchorElement, ButtonLinkProps>(function ButtonLink(
  { variant = "secondary", className, ...props },
  ref,
) {
  return <Link ref={ref} className={buttonClassName(variant, className)} {...props} />;
});
