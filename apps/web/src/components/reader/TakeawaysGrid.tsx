import styles from "./TakeawaysGrid.module.css";

/** The lesson's key takeaways as the mockup's labelled column grid — each an eyebrow ("TAKEAWAY N")
 *  over its line. The caller renders it only for a non-empty list. */
export function TakeawaysGrid({ takeaways }: { takeaways: string[] }) {
  return (
    <section className={styles.grid} aria-label="Key takeaways">
      {takeaways.map((takeaway, index) => (
        <div key={index} className={styles.item}>
          <p className={`eyebrow ${styles.label}`}>Takeaway {index + 1}</p>
          <p className={styles.text}>{takeaway}</p>
        </div>
      ))}
    </section>
  );
}
