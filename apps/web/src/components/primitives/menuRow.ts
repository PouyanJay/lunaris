import styles from "./Menu.module.css";

/** The menu panel's row styling, for a footer entry that leads somewhere rather than choosing a
 *  value. Lives apart from the component so a consumer can compose a row in the menu's own language
 *  without the module exporting both a component and constants. */
export const menuRowClass = styles.row;
export const menuRowCaretClass = styles.rowCaret;
