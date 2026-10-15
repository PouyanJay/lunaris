const ACCESS_CONTACT_EMAIL = "contact@pouyan.ai";

/** The notice a visitor sees while production is offline. */
export function ServiceOffline() {
  return (
    <main>
      <h1>Lunaris is offline</h1>
      <p>
        To request access, contact{" "}
        <a href={`mailto:${ACCESS_CONTACT_EMAIL}`}>{ACCESS_CONTACT_EMAIL}</a>.
      </p>
    </main>
  );
}
