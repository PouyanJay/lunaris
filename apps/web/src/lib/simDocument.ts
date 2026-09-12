const CSP =
  "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; " +
  "img-src data:; connect-src 'none'; frame-src 'none'; worker-src 'none'; " +
  "form-action 'none'; base-uri 'none'";

/** A trusted enclosing document enforces frame-src against generated self-navigation. */
export function simDocument(html: string): string {
  const escaped = html
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return `<!doctype html><html><head>
<meta http-equiv="Content-Security-Policy" content="${CSP}">
<style>html,body,iframe{width:100%;height:100%;margin:0;border:0}body{overflow:hidden}</style>
</head><body><iframe title="Simulator controls" sandbox="allow-scripts" referrerpolicy="no-referrer" srcdoc="${escaped}"></iframe>
<script>
const instrument=document.querySelector('iframe');
window.addEventListener('message', event => {
  if(event.source===parent) instrument.contentWindow.postMessage(event.data,'*');
  else if(event.source===instrument.contentWindow) parent.postMessage(event.data,'*');
});
</script></body></html>`;
}
