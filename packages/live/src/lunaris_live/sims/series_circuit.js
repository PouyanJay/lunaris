(() => {
  const mount = () => {
    const host = document.querySelector('[data-lunaris-renderer="series-resistor-v1"]');
    if (!host || host.shadowRoot) throw new Error('Invalid circuit mount');
    const root = host.attachShadow({mode: 'open'});
    root.innerHTML = `<style>
      :host{display:block;min-width:240px}svg{display:block;width:100%;max-height:440px;
      background:var(--paper,#f7f8fa);color:var(--ink,#12151c);font:14px system-ui}
      .wire{stroke:var(--ink,#12151c);stroke-width:3;fill:none}
      .component{stroke:var(--ink,#12151c);stroke-width:3;fill:var(--paper,#f7f8fa)}
      text{fill:var(--ink,#12151c)}.accent{fill:var(--accent,#2563eb)}
      @media(prefers-color-scheme:dark){svg{--paper:#12151c;--ink:#f7f8fa;--accent:#60a5fa}}
    </style><svg viewBox="0 0 460 300" role="img" aria-label="One voltage source and resistor in a closed series circuit">
      <g class="wire">
        <line data-circuit-wire x1="80" y1="135" x2="80" y2="60"/>
        <line data-circuit-wire x1="80" y1="60" x2="220" y2="60"/>
        <line data-circuit-wire x1="300" y1="60" x2="400" y2="60"/>
        <line data-circuit-wire x1="400" y1="60" x2="400" y2="240"/>
        <line data-circuit-wire x1="400" y1="240" x2="80" y2="240"/>
        <line data-circuit-wire x1="80" y1="240" x2="80" y2="165"/>
        <line data-circuit-electrode="positive" x1="55" y1="135" x2="105" y2="135"/>
        <line data-circuit-electrode="negative" x1="65" y1="165" x2="95" y2="165"/>
      </g>
      <rect data-circuit-resistor class="component" x="220" y="45" width="80" height="30"/>
      <polygon data-circuit-arrow class="accent" points="400,165 391,148 409,148"/>
      <text x="115" y="140">+</text><text x="115" y="170">-</text>
      <text data-circuit-voltage x="135" y="195" text-anchor="start"></text>
      <text data-circuit-resistance x="260" y="100" text-anchor="middle"></text>
      <text data-circuit-current x="240" y="280" text-anchor="middle" aria-live="polite"></text>
    </svg>`;
    const draw = state => {
      const voltage = Number(state.voltage), resistance = Number(state.resistance);
      if (!Number.isFinite(voltage) || !Number.isFinite(resistance) || voltage < 0 || resistance <= 0) return;
      const current = voltage / resistance;
      root.querySelector('[data-circuit-voltage]').textContent = `${voltage} V`;
      root.querySelector('[data-circuit-resistance]').textContent = `${resistance} \u03a9`;
      root.querySelector('[data-circuit-current]').textContent = `I = ${current.toFixed(2)} A`;
      root.querySelector('[data-circuit-arrow]').style.visibility = current === 0 ? 'hidden' : 'visible';
    };
    const controls = () => draw({
      voltage: document.querySelector('[data-sim-param="voltage"]').value,
      resistance: document.querySelector('[data-sim-param="resistance"]').value,
    });
    document.addEventListener('input', controls, true);
    document.addEventListener('change', controls, true);
    window.addEventListener('message', event => {
      const message = event.data;
      if (event.source === parent && message?.version === 1 && message.state &&
          ['lunaris.sim.init', 'lunaris.sim.command'].includes(message.type)) draw(message.state);
    });
    controls();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once:true});
  else mount();
})();
