import type { AgentTodo } from "../../types/course";
import styles from "./TodoList.module.css";

interface TodoListProps {
  todos: AgentTodo[];
}

type TodoState = "completed" | "in_progress" | "pending";

/** Normalise the agent's free-form todo status onto the three states we render. */
function todoState(status: string): TodoState {
  const value = status.toLowerCase();
  if (value === "completed" || value === "done") return "completed";
  if (value === "in_progress" || value === "active") return "in_progress";
  return "pending";
}

/** The agent's live plan — the current `write_todos` list, each item checked/active/pending. */
export function TodoList({ todos }: TodoListProps) {
  return (
    <section className={styles.plan} aria-label="Agent plan">
      <span className={`eyebrow ${styles.label}`}>Plan</span>
      <ol className={styles.list}>
        {todos.map((todo, index) => {
          const state = todoState(todo.status);
          return (
            <li key={`${index}-${todo.content}`} className={styles.item} data-state={state}>
              <span className={styles.indicator} data-state={state} aria-hidden="true" />
              <span className={styles.content}>{todo.content}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
