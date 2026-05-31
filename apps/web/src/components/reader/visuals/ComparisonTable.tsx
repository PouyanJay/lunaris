import type { ComparisonSpec } from "../../../types/course";
import styles from "./visuals.module.css";

interface ComparisonTableProps {
  spec: ComparisonSpec;
}

/** A branded comparison table: a leading row-label column plus the spec's columns. */
export function ComparisonTable({ spec }: ComparisonTableProps) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <td className={styles.corner} />
            {spec.columns.map((column, index) => (
              <th key={index} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              <th scope="row" className={styles.rowLabel}>
                {row.label}
              </th>
              {row.values.map((value, cellIndex) => (
                <td key={cellIndex}>{value}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
