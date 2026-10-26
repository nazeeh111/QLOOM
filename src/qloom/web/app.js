'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const fmt = (value, digits = 0) => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, {maximumFractionDigits: digits}) : '—';
  const pct = (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : '—';
  const sci = (value) => Number.isFinite(Number(value)) ? Number(value).toExponential(2) : '—';
  const time = (value) => !Number.isFinite(Number(value)) ? '—' : Number(value) < 1 ? `${fmt(Number(value) * 1000, 1)} ms` : `${fmt(value, 2)} s`;
  const ns = (value) => finite(value) >= 1000 ? `${fmt(finite(value) / 1000, 2)} µs` : `${fmt(value)} ns`;
  const state = {examples: [], devices: [], report: null, candidateId: null, historyIndex: 0, selectedQubit: null, replay: null, busy: false};
  const svg = (w, h, body, label = '') => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}"${label ? ` aria-label="${esc(label)}"` : ''}>${body}</svg>`;
  const setError = (message) => { $('error-message').textContent = message || ''; $('error-message').hidden = !message; };
  async function api(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) { let detail; try { detail = (await response.json()).detail; } catch (_) { detail = response.statusText; } throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail)); }
    return response.json();
  }
  function candidate() { return state.report?.candidates?.find((c) => c.id === state.candidateId) || state.report?.candidates?.[0]; }
  function status(message) { $('request-status').textContent = message; }
  function stopReplay() {
    if (state.replay) clearInterval(state.replay);
    state.replay = null;
    $('replay-button').textContent = '▶';
    $('replay-button').setAttribute('aria-pressed', 'false');
    $('replay-button').setAttribute('aria-label', 'Play recorded routing steps');
  }
  function setBusy(busy) {
    state.busy = busy;
    $('compile-button').disabled = busy;
    $('demo-button').disabled = busy;
    $('compile-button').setAttribute('aria-busy', String(busy));
    $('compile-button').querySelector('.button-label').textContent = busy ? 'Compiling & checking…' : 'Compile & verify';
  }
  function download(name, content, type = 'application/json') {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const link = document.createElement('a'); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function nameForExport() { return `qloom-${String(state.candidateId || 'report').replace(/[^a-zA-Z0-9_-]/g, '-')}`; }
  function updateDeviceSummary() {
    const device = state.devices.find((d) => d.name === $('device-select').value);
    if (!device) return;
    $('device-summary').textContent = `${device.n_qubits} qubits · ${device.edges?.length || 0} connections · ${device.noise_source || 'synthetic calibration'}`;
  }
  function loadExample(id) {
    const example = state.examples.find((e) => e.id === id);
    if (!example) return;
    $('qasm-input').value = example.qasm;
    $('example-description').textContent = example.description || 'OpenQASM 2 circuit';
    matchCircuitWidth();
    setError('');
  }
  function matchCircuitWidth() {
    const source = $('qasm-input').value;
    const matches = [...source.matchAll(/qreg\s+\w+\s*\[\s*(\d+)\s*\]/g)];
    const width = matches.reduce((total, match) => total + Number(match[1]), 0);
    if (!width || !state.devices.length) return;
    const current = state.devices.find((d) => d.name === $('device-select').value);
    if (current?.n_qubits === width) return;
    const topology = current?.name?.split('-')[0];
    const matched = state.devices.find((d) => d.n_qubits === width && d.name.startsWith(topology + '-')) || state.devices.find((d) => d.n_qubits === width);
    if (matched) { $('device-select').value = matched.name; updateDeviceSummary(); }
  }
  function operations(input) { return Array.isArray(input?.operations) ? input.operations : []; }
  function renderCircuit(target, ops, n, prefix, measurements = []) {
    n = Math.max(1, finite(n, 1));
    const wireGap = n > 6 ? 30 : 36;
    const start = 55, step = 38;
    const levels = Array(n).fill(0);
    const positioned = ops.filter((o) => o.gate !== 'barrier').map((op) => {
      const qubits = Array.isArray(op.qubits) ? op.qubits.map(Number) : [];
      const min = Math.max(0, Math.min(...qubits)), max = Math.min(n - 1, Math.max(...qubits));
      const touched = Array.from({length: max - min + 1}, (_, i) => min + i);
      const column = Math.max(0, ...touched.map((q) => levels[q]));
      touched.forEach((q) => { levels[q] = column + 1; });
      return {op, qubits, x: start + 23 + column * step};
    });
    const columns = Math.max(1, ...levels);
    const width = Math.max(380, start + (columns + (measurements.length ? 1 : 0)) * step + 35);
    const height = n * wireGap + 26;
    let body = '';
    for (let q = 0; q < n; q++) {
      const y = 26 + q * wireGap;
      body += `<text x="9" y="${y + 3}" font-family="monospace" font-size="9" fill="#758084">${prefix}${q}</text><line x1="${start}" y1="${y}" x2="${width - 18}" y2="${y}" stroke="#cfd7d2" stroke-width="1"/>`;
    }
    positioned.forEach(({op, qubits, x}) => {
      const ys = qubits.map((q) => 26 + q * wireGap);
      const gate = String(op.gate || '').toLowerCase();
      const label = gate === 'u' || gate === 'u3' ? 'U' : gate.toUpperCase();
      const title = `${gate} ${qubits.map((q) => `${prefix}${q}`).join(', ')}${op.params?.length ? ` (${op.params.map((p) => fmt(p, 4)).join(', ')})` : ''}`;
      if (ys.length === 2 && (gate === 'cx' || gate === 'cnot')) {
        body += `<g><title>${esc(title)}</title><line x1="${x}" x2="${x}" y1="${ys[0]}" y2="${ys[1]}" stroke="#bc7e35" stroke-width="1.4"/><circle cx="${x}" cy="${ys[0]}" r="3.5" fill="#bc7e35"/><circle cx="${x}" cy="${ys[1]}" r="8.5" fill="#fffefa" stroke="#bc7e35" stroke-width="1.4"/><path d="M${x - 5} ${ys[1]}h10M${x} ${ys[1] - 5}v10" stroke="#bc7e35" stroke-width="1.2"/></g>`;
      } else if (gate === 'swap' && ys.length === 2) {
        body += `<g><title>${esc(title)}</title><line x1="${x}" x2="${x}" y1="${ys[0]}" y2="${ys[1]}" stroke="#bc7e35"/>${ys.map((y) => `<path d="M${x - 4} ${y - 4}l8 8M${x - 4} ${y + 4}l8-8" stroke="#bc7e35" stroke-width="1.5"/>`).join('')}</g>`;
      } else if (ys.length === 2 && gate === 'cz') {
        body += `<g><title>${esc(title)}</title><line x1="${x}" x2="${x}" y1="${ys[0]}" y2="${ys[1]}" stroke="#bc7e35"/>${ys.map((y) => `<circle cx="${x}" cy="${y}" r="3.5" fill="#bc7e35"/>`).join('')}</g>`;
      } else {
        const y = ys[0] ?? 26;
        body += `<g><title>${esc(title)}</title><rect x="${x - 11}" y="${y - 11}" width="22" height="22" rx="2" fill="#f4f7f6" stroke="#6b8999" stroke-width="1"/><text x="${x}" y="${y + 3}" text-anchor="middle" font-family="monospace" font-size="${label.length > 2 ? 7 : 9}" fill="#315d7a">${esc(label.slice(0, 4))}</text></g>`;
      }
    });
    measurements.forEach(([q, c]) => {
      const x = start + 23 + columns * step, y = 26 + q * wireGap;
      body += `<g><title>measure ${prefix}${q} → classical bit ${c}</title><rect x="${x - 11}" y="${y - 11}" width="22" height="22" rx="2" fill="#f2f2e9" stroke="#9ba79c"/><path d="M${x - 6} ${y + 4}a6 6 0 0 1 12 0M${x} ${y + 4}l4-8" fill="none" stroke="#758084"/></g>`;
    });
    target.innerHTML = svg(width, height, body);
    target.querySelector('svg').setAttribute('width', String(width));
    target.querySelector('svg').setAttribute('height', String(height));
  }
  function renderMetrics(c) {
    const m = c.metrics || {}, v = c.verification || {};
    $('metric-gates').textContent = fmt(m.two_qubit_gates);
    $('metric-depth').textContent = fmt(m.depth);
    $('metric-duration').textContent = finite(m.duration_ns) >= 1000 ? fmt(finite(m.duration_ns) / 1000, 2) : fmt(m.duration_ns);
    $('duration-unit').textContent = finite(m.duration_ns) >= 1000 ? 'µs' : 'ns';
    $('metric-verified').textContent = v.passed ? 'Equivalent' : 'Not verified';
    $('verification-icon').textContent = v.passed ? '✓' : '!';
    $('verification-icon').style.color = v.passed ? 'var(--green)' : 'var(--rust)';
    $('metric-error').textContent = `Max residual ${sci(v.max_error)} · full-unitary check`;
    const baseline = (state.report.baselines || []).find((b) => b.name?.toLowerCase().includes('qiskit') && (b.name.includes('3') || b.id?.includes('3')) && b.metrics);
    if (baseline) {
      const difference = finite(baseline.metrics.two_qubit_gates) - finite(m.two_qubit_gates);
      $('metric-gates-note').textContent = difference > 0 ? `${difference} fewer than ${baseline.name}` : difference < 0 ? `${Math.abs(difference)} more than ${baseline.name}` : `Same count as ${baseline.name}`;
    } else $('metric-gates-note').textContent = 'Physical gate count';
  }
  function historySteps(c) {
    const initial = {kind:'layout', label:'Initial placement', qubits:[], mapping:c.initial_mapping};
    const stored = Array.isArray(c.history) ? c.history : [];
    return stored[0]?.kind === 'layout' ? stored : [initial, ...stored];
  }
  function renderHardware() {
    const c = candidate(); if (!c) return;
    const device = state.report.device || {}, n = finite(device.n_qubits, state.report.input.n_qubits);
    const history = historySteps(c);
    state.historyIndex = Math.min(state.historyIndex, history.length - 1);
    const entry = history[state.historyIndex];
    let mapping = entry.mapping;
    if (!Array.isArray(mapping)) {
      for (let i = state.historyIndex; i >= 0; i--) { if (Array.isArray(history[i].mapping)) { mapping = history[i].mapping; break; } }
    }
    mapping ||= c.initial_mapping || Array.from({length:n}, (_, i) => i);
    const active = Array.isArray(entry.qubits) ? entry.qubits : [];
    const W = 260, H = 225, radius = n < 5 ? 69 : 79;
    const points = Array.from({length:n}, (_, q) => ({x:W/2 + radius * Math.cos(-Math.PI/2 + q * 2 * Math.PI/n),y:H/2 + radius * Math.sin(-Math.PI/2 + q * 2 * Math.PI/n)}));
    let body = '';
    (device.edges || []).forEach(([a,b]) => {
      const pa=points[a],pb=points[b]; if (!pa || !pb) return;
      const selected = active.includes(a) && active.includes(b);
      body += `<line x1="${pa.x}" y1="${pa.y}" x2="${pb.x}" y2="${pb.y}" stroke="${selected ? '#bc7e35' : '#c9d4d5'}" stroke-width="${selected ? 3.5 : 2}"/>`;
    });
    points.forEach((p,q) => {
      const logical = mapping.indexOf(q), selected = state.selectedQubit === q, isActive = active.includes(q);
      body += `<g class="graph-node" tabindex="0" role="button" data-qubit="${q}" aria-label="Physical qubit ${q}, ${logical >= 0 ? `logical qubit ${logical}` : 'unassigned'}" aria-pressed="${selected}"><circle cx="${p.x}" cy="${p.y}" r="21" fill="${selected || isActive ? '#f6eddc' : '#fffefa'}" stroke="${selected || isActive ? '#bc7e35' : '#547b8e'}" stroke-width="${selected ? 2.5 : 1.4}"/><text x="${p.x}" y="${p.y - 2}" text-anchor="middle" font-family="monospace" font-size="11" fill="#203239">p${q}</text><text x="${p.x}" y="${p.y + 10}" text-anchor="middle" font-family="monospace" font-size="8" fill="#758084">${logical >= 0 ? `q${logical}` : 'idle'}</text></g>`;
    });
    $('hardware-graph').innerHTML = svg(W,H,body);
    $('hardware-graph').querySelectorAll('[data-qubit]').forEach((el) => {
      const activate = () => { state.selectedQubit = Number(el.dataset.qubit); renderHardware(); };
      el.addEventListener('click', activate);
      el.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); } });
    });
    $('mapping-list').innerHTML = mapping.map((p,q) => `<div class="mapping-item${state.selectedQubit === p || active.includes(p) ? ' active' : ''}">q${q}<span class="mapping-arrow">→</span>p${esc(p)}</div>`).join('');
    $('topology-label').textContent = String(device.name || 'SIMULATED').replace(/_/g,' ').toUpperCase();
    $('history-input').max = String(history.length - 1);
    $('history-input').value = String(state.historyIndex);
    $('history-position').textContent = `${state.historyIndex} / ${history.length - 1}`;
    $('history-label').textContent = entry.label || `${entry.kind || 'Transformation'} ${entry.step ?? state.historyIndex}`;
    $('replay-button').disabled = history.length <= 1;
    if (state.selectedQubit !== null) {
      const logical = mapping.indexOf(state.selectedQubit);
      const degree = (device.edges || []).filter(([a,b]) => a === state.selectedQubit || b === state.selectedQubit).length;
      $('qubit-detail').textContent = `p${state.selectedQubit} carries ${logical >= 0 ? `logical q${logical}` : 'no logical qubit'} at this step. ${degree} physical connection${degree === 1 ? '' : 's'}.`;
    } else $('qubit-detail').textContent = 'Select a physical qubit to inspect its logical assignment.';
  }
  function range(values, pad = .14) {
    let low = Math.min(...values), high = Math.max(...values);
    if (low === high) { low -= Math.max(1, Math.abs(low) * .1); high += Math.max(1, Math.abs(high) * .1); }
    const delta = high - low;
    return [Math.max(0, low - delta*pad), high + delta*pad];
  }
  function renderPareto() {
    const list = state.report.candidates || [], pareto = state.report.pareto_ids || [];
    const W=440,H=222,L=48,R=18,T=13,B=44;
    const [xmin,xmax]=range(list.map((c)=>finite(c.metrics.two_qubit_gates)));
    const [ymin,ymax]=range(list.map((c)=>finite(c.metrics.duration_ns)/1000));
    const x=(v)=>L+(v-xmin)/(xmax-xmin)*(W-L-R), y=(v)=>H-B-(v-ymin)/(ymax-ymin)*(H-T-B);
    let body='';
    for(let i=0;i<4;i++){
      const value=ymin+(ymax-ymin)*i/3,py=y(value);
      body+=`<line class="chart-grid" x1="${L}" x2="${W-R}" y1="${py}" y2="${py}"/><text class="chart-label" x="${L-9}" y="${py+3}" text-anchor="end">${fmt(value,1)}</text>`;
    }
    for(let i=0;i<4;i++){
      const value=xmin+(xmax-xmin)*i/3,px=x(value);
      body+=`<text class="chart-label" x="${px}" y="${H-B+18}" text-anchor="middle">${fmt(value)}</text>`;
    }
    body+=`<line class="chart-axis" x1="${L}" x2="${W-R}" y1="${H-B}" y2="${H-B}"/><text class="chart-title" x="${(W+L-R)/2}" y="${H-5}" text-anchor="middle">Two-qubit gate count →</text><text class="chart-title" transform="translate(12 ${(H-B+T)/2}) rotate(-90)" text-anchor="middle">Duration (µs) →</text>`;
    const front=list.filter((c)=>pareto.includes(c.id)).sort((a,b)=>a.metrics.two_qubit_gates-b.metrics.two_qubit_gates);
    if(front.length>1) body+=`<path d="${front.map((c,i)=>`${i?'L':'M'}${x(c.metrics.two_qubit_gates)} ${y(c.metrics.duration_ns/1000)}`).join(' ')}" fill="none" stroke="#bc7e35" stroke-width="1" stroke-dasharray="3 4"/>`;
    // Identical cost points remain truthful; the candidate selector exposes every overlapping candidate.
    list.forEach((c)=>{
      const px=x(finite(c.metrics.two_qubit_gates)),py=y(finite(c.metrics.duration_ns)/1000),isFront=pareto.includes(c.id),selected=c.id===state.candidateId;
      body+=`<g class="chart-point" tabindex="0" role="button" data-candidate="${esc(c.id)}" aria-label="Candidate ${esc(c.id)}, ${fmt(c.metrics.two_qubit_gates)} two-qubit gates, ${ns(c.metrics.duration_ns)}${selected?', selected':''}"><title>${esc(c.id)} · ${fmt(c.metrics.two_qubit_gates)} CX · ${ns(c.metrics.duration_ns)}</title>${selected?`<circle cx="${px}" cy="${py}" r="8.5" fill="none" stroke="#203239" stroke-width="1"/>`:''}<circle cx="${px}" cy="${py}" r="${selected?4.5:4}" fill="${isFront?'#bc7e35':'#6b91a5'}" stroke="#fffefa" stroke-width="1.5"/></g>`;
    });
    $('pareto-chart').innerHTML=svg(W,H,body);
    $('pareto-chart').querySelectorAll('[data-candidate]').forEach((el)=>{
      const activate=()=>selectCandidate(el.dataset.candidate);
      el.addEventListener('click',activate);
      el.addEventListener('keydown',(event)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();activate();}});
    });
    $('evaluated-count').textContent=`${list.length} EVALUATED`;
    $('search-time').textContent=`${time(state.report.optimizer_time_s ?? state.report.search_time_s)} search + verification`;
    renderProgress(list);
  }
  function renderProgress(list) {
    if(!list.length)return;
    const W=400,H=62,L=3,R=5,T=7,B=17;
    const xs=list.map((c,i)=>finite(c.elapsed_s, i+1)),maxX=Math.max(...xs, .001);
    let best=Infinity;
    const vals=list.map((c)=>{best=Math.min(best,finite(c.metrics.objective));return best;});
    const [low,high]=range(vals,.1);
    const x=(v)=>L+v/maxX*(W-L-R), y=(v)=>H-B-(v-low)/(high-low)*(H-T-B);
    let d='';
    vals.forEach((v,i)=>{if(i===0)d+=`M${x(0)} ${y(v)}L${x(xs[i])} ${y(v)}`;else d+=`L${x(xs[i])} ${y(vals[i-1])}L${x(xs[i])} ${y(v)}`;});
    $('progress-chart').innerHTML=svg(W,H,`<line class="chart-grid" x1="${L}" x2="${W-R}" y1="${H-B}" y2="${H-B}"/><path d="${d}" fill="none" stroke="#315d7a" stroke-width="1.5"/><circle cx="${x(xs.at(-1))}" cy="${y(vals.at(-1))}" r="2.5" fill="#315d7a"/><text class="chart-label" x="${L}" y="${H-3}">0 s</text><text class="chart-label" x="${W-R}" y="${H-3}" text-anchor="end">${fmt(maxX,3)} s</text>`);
  }
  function renderCandidateDetails(c) {
    const conf=c.config||{},v=c.verification||{},model=state.report.model||{};
    const values=[['INITIAL LAYOUT',conf.layout],['ROUTING POLICY',conf.routing],['LOOKAHEAD',conf.lookahead],['REWRITE',conf.rewrite ? 'Enabled' : 'Disabled'],['SURROGATE SCORE',c.model_prediction === null || c.model_prediction === undefined ? 'Not used' : fmt(c.model_prediction,4)]];
    $('candidate-config').innerHTML=values.map(([label,value])=>`<div class="config-item"><span>${esc(label)}</span><strong>${esc(value ?? '—')}</strong></div>`).join('');
    const measurement=state.report.input.measurements||[];
    $('verification-detail').innerHTML=`<div><h4>${v.passed?'Verified logical equivalence':'Candidate has not passed verification'}</h4><p>Method: <code>${esc(v.method||'unreported')}</code><br>Matrix residual: <code>${sci(v.max_error)}</code><br>Global phase error: <code>${sci(v.global_phase_error)}</code><br>Random input residual: <code>${sci(v.randomized_max_error)}</code> over <code>${fmt(v.trials)}</code> trials.</p><p>Initial mapping: <code>${esc(JSON.stringify(c.initial_mapping))}</code><br>Final mapping: <code>${esc(JSON.stringify(c.final_mapping))}</code><br>Global phase: <code>${esc(c.global_phase ?? 0)}</code> rad.<br>Classical outputs: <code>${esc(JSON.stringify(measurement))}</code></p></div><div><h4>Reproduce this experiment</h4><p>Strategy <code>${esc(state.report.strategy)}</code>, seed <code>${esc(state.report.seed)}</code>, budget <code>${esc(state.report.budget)}</code>.<br>Model <code>${esc(model.name||'none')}</code>; ${fmt(model.training_rows)} evaluated training rows from ${fmt(model.training_circuits)} circuits.<br>Model SHA-256: <code>${esc(model.sha256||'not supplied')}</code></p><p>${esc(state.report.export_note||'OpenQASM 2 does not encode global phase. Preserve the JSON report or mapping and phase sidecar with your exported circuit.')}</p></div>`;
    $('model-label').textContent=`${model.name||'QLOOM'} / ${fmt(model.training_rows)} TRAINING EVALUATIONS`;
  }
  function renderBaselines(c) {
    const entries=[{...c,metrics:{...c.metrics,compile_time_s:state.report.optimizer_time_s ?? state.report.search_time_s},name:'QLOOM · search',selected:true},...(state.report.baselines||[])];
    $('baseline-table').innerHTML=entries.map((b)=>{
      const m=b.metrics,v=b.verification;
      if(!m)return `<tr><td>${esc(b.name||b.id)}</td><td colspan="4" class="failure-pill" title="${esc(b.reason||b.status||'Unavailable')}">${esc(b.status||'Unavailable')}: ${esc(b.reason||'No measurements reported')}</td></tr>`;
      return `<tr class="${b.selected?'selected-baseline':''}"><td>${esc(b.name||b.id)}</td><td>${fmt(m.two_qubit_gates)}</td><td>${fmt(m.depth)}</td><td>${time(m.compile_time_s)}</td><td class="${v?.passed?'check-text':'fail-text'}">${v?.passed?'✓ Yes':'! No'}</td></tr>`;
    }).join('');
    const unavailable=(state.report.baselines||[]).filter((b)=>!b.metrics).length;
    $('baseline-note').textContent=`QLOOM time covers ranking, search and verification; baseline times cover their compiler calls. Effort can differ.${unavailable?` ${unavailable} baseline${unavailable===1?' is':'s are'} unavailable in this run; reasons are recorded above.`:''} All reported compiled circuits use the selected device constraints.`;
  }
  function probabilityEntries(value) {
    if(Array.isArray(value))return value.map((p,i)=>[i.toString(2).padStart(state.report.input.n_qubits,'0'),finite(p)]);
    if(value&&typeof value==='object')return Object.entries(value).map(([k,p])=>[k,finite(p)]);
    return [];
  }
  function renderNoise() {
    const noise=state.report.noise;
    if(!noise){
      $('noise-summary').innerHTML='<p class="noise-empty">No noisy simulation was included in this report.</p>';
      $('noise-chart').innerHTML='';$('noise-assumptions').textContent='Logical equivalence evidence remains available independently.';return;
    }
    $('noise-summary').innerHTML=`<div class="noise-stat compiled"><span>Compiled output fidelity</span><strong>${pct(noise.optimized_fidelity)}</strong></div><div class="noise-stat reference"><span>Reference output fidelity</span><strong>${pct(noise.input_fidelity)}</strong></div>`;
    const ideal=Object.fromEntries(probabilityEntries(noise.ideal_probabilities)),compiled=Object.fromEntries(probabilityEntries(noise.optimized_probabilities)),reference=Object.fromEntries(probabilityEntries(noise.input_probabilities));
    const keys=[...new Set([...Object.keys(ideal),...Object.keys(compiled),...Object.keys(reference)])].sort((a,b)=>Math.max(ideal[b]||0,compiled[b]||0,reference[b]||0)-Math.max(ideal[a]||0,compiled[a]||0,reference[a]||0)).slice(0,8);
    const W=440,H=145,L=37,R=12,T=10,B=29,max=Math.max(...keys.flatMap((k)=>[ideal[k]||0,compiled[k]||0,reference[k]||0]),.01)*1.1;
    let body='';
    for(let i=0;i<3;i++){const v=max*i/2,y=H-B-v/max*(H-T-B);body+=`<line class="chart-grid" x1="${L}" x2="${W-R}" y1="${y}" y2="${y}"/><text class="chart-label" x="${L-8}" y="${y+3}" text-anchor="end">${fmt(v*100)}%</text>`;}
    const group=(W-L-R)/Math.max(keys.length,1),bar=Math.min(10,group/4);
    keys.forEach((key,i)=>{const center=L+group*(i+.5);[[ideal,'#b7c5be'],[compiled,'#315d7a'],[reference,'#bc7e35']].forEach(([values,color],j)=>{const value=values[key]||0,height=value/max*(H-T-B);body+=`<rect x="${center+(j-1.5)*bar}" y="${H-B-height}" width="${Math.max(2,bar-1.5)}" height="${height}" rx="1" fill="${color}"><title>${esc(key)}: ${pct(value)}</title></rect>`;});body+=`<text class="chart-label" x="${center}" y="${H-11}" text-anchor="middle" font-size="${key.length>6?7:9}">${esc(key)}</text>`;});
    $('noise-chart').innerHTML=keys.length?svg(W,H,body):'<p class="noise-empty">Probability distribution unavailable.</p>';
    const assumptions=Array.isArray(noise.assumptions)?noise.assumptions.join('\n'):typeof noise.assumptions==='object'?JSON.stringify(noise.assumptions,null,2):noise.assumptions||'';
    $('noise-assumptions').textContent=`${noise.method||'Simulator output comparison'}. ${noise.shots?`${noise.shots} shots. `:''}${assumptions}\nTop ${keys.length} outcomes shown, ordered by probability. Similarity of noisy outputs is not proof of logical equivalence. Noise comparison belongs to the experiment’s best candidate, even when inspecting another candidate.`;
  }
  function selectCandidate(id) {
    state.candidateId=id;state.historyIndex=0;state.selectedQubit=null;stopReplay();
    const c=candidate();if(!c)return;
    $('candidate-select').value=c.id;
    renderMetrics(c);
    const input=state.report.input;
    const measurements=(input.measurements||[]).map(([q,bit])=>[c.final_mapping?.[q]??q,bit]);
    renderCircuit($('output-circuit'),operations(c),state.report.device.n_qubits,'p',measurements);
    $('output-circuit-meta').textContent=`${operations(c).length} operations · ${c.id===state.report.best_id?'best found':'candidate '+c.id}`;
    renderHardware();renderPareto();renderCandidateDetails(c);renderBaselines(c);
  }
  function renderReport(report,recorded=false) {
    if(!report?.candidates?.length||!report.input||!report.device)throw new Error('The compiler returned no inspectable candidates. See the server log for details.');
    stopReplay();state.report=report;state.candidateId=report.best_id||report.candidates[0].id;
    $('results').hidden=false;$('empty-state').hidden=true;$('recorded-badge').hidden=!recorded;
    $('export-report').disabled=false;
    $('experiment-title').textContent=`${report.input.name||'Quantum circuit'} / ${report.device.name||'simulated device'}`;
    $('experiment-subtitle').textContent=`${report.input.n_qubits} logical qubits · ${report.strategy||'learned'} search · ${report.candidates.length} real evaluations · seed ${report.seed}`;
    $('input-circuit-meta').textContent=`${operations(report.input).length} operations · ${report.input.n_qubits} qubits`;
    renderCircuit($('input-circuit'),operations(report.input),report.input.n_qubits,'q',report.input.measurements||[]);
    $('candidate-select').innerHTML=report.candidates.map((c,i)=>`<option value="${esc(c.id)}">${c.id===report.best_id?'★ ':''}Candidate ${i+1} · ${fmt(c.metrics.two_qubit_gates)} CX</option>`).join('');
    selectCandidate(state.candidateId);renderNoise();
    if(recorded&&report.input.qasm){$('qasm-input').value=report.input.qasm;$('example-select').value='';$('example-description').textContent='Source from the recorded experiment';}
    const device=state.devices.find((d)=>d.name===report.device.name);if(device){$('device-select').value=device.name;updateDeviceSummary();}
    if(recorded){$('budget-input').value=String(Math.min(24,report.budget||8));$('budget-output').textContent=`${$('budget-input').value} candidates`;$('seed-input').value=String(report.seed??7);if(['learned','heuristic','random'].includes(report.strategy))$('strategy-select').value=report.strategy;}
  }
  async function loadDemo() {
    if(state.busy)return;setBusy(true);setError('');status('Loading a recorded, reproducible compiler experiment…');
    try{const report=await api('/api/demo');renderReport(report,true);status(`Recorded experiment loaded. ${report.candidates.length} evaluated candidates; original runtime ${time(report.elapsed_s)}.`);}catch(error){setError(`Could not load the recorded experiment: ${error.message}`);status('You can still import a circuit and start a new compilation.');}finally{setBusy(false);}
  }
  $('compile-form').addEventListener('submit',async(event)=>{
    event.preventDefault();if(state.busy)return;
    if(!$('qasm-input').value.trim()){setError('Add an OpenQASM circuit or choose an example before compiling.');return;}
    if(!$('device-select').value){setError('Choose an available simulated processor.');return;}
    setBusy(true);stopReplay();setError('');status('Running real compiler evaluations and independent equivalence checks. This may take a moment; results appear when the request completes.');
    try{
      const report=await api('/api/compile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qasm:$('qasm-input').value,device:$('device-select').value,budget:Number($('budget-input').value),seed:Number($('seed-input').value),strategy:$('strategy-select').value})});
      renderReport(report,false);status(`Complete: ${report.candidates.length} candidates evaluated in ${time(report.elapsed_s)}. Export the report to reproduce this run.`);
    }catch(error){setError(`Compilation could not complete: ${error.message}`);status('Your source is preserved. Correct the input or device selection and try again.');}finally{setBusy(false);}
  });
  $('example-select').addEventListener('change',()=>loadExample($('example-select').value));
  $('device-select').addEventListener('change',updateDeviceSummary);
  $('budget-input').addEventListener('input',()=>{$('budget-output').textContent=`${$('budget-input').value} candidates`;});
  $('qasm-input').addEventListener('input',()=>{$('example-select').value='';$('example-description').textContent='Custom OpenQASM source';});
  $('demo-button').addEventListener('click',loadDemo);
  $('import-button').addEventListener('click',()=>$('file-input').click());
  $('file-input').addEventListener('change',async()=>{
    const file=$('file-input').files?.[0];if(!file)return;
    if(file.size>100000){setError('Choose an OpenQASM file smaller than 100 KB.');$('file-input').value='';return;}
    try{$('qasm-input').value=await file.text();$('example-select').value='';$('example-description').textContent=`Imported ${file.name}`;matchCircuitWidth();setError('');}catch(error){setError(`Could not read the file: ${error.message}`);}finally{$('file-input').value='';}
  });
  $('candidate-select').addEventListener('change',()=>selectCandidate($('candidate-select').value));
  $('history-input').addEventListener('input',()=>{stopReplay();state.historyIndex=Number($('history-input').value);renderHardware();});
  $('replay-button').addEventListener('click',()=>{
    if(state.replay){stopReplay();return;}
    const steps=historySteps(candidate());if(steps.length<=1)return;
    if(state.historyIndex>=steps.length-1)state.historyIndex=0;
    $('replay-button').textContent='Ⅱ';$('replay-button').setAttribute('aria-pressed','true');$('replay-button').setAttribute('aria-label','Pause recorded routing steps');
    const interval=window.matchMedia('(prefers-reduced-motion: reduce)').matches?1200:850;
    state.replay=setInterval(()=>{state.historyIndex++;renderHardware();if(state.historyIndex>=steps.length-1)stopReplay();},interval);
  });
  $('export-report').addEventListener('click',()=>{if(state.report)download('qloom-experiment.json',JSON.stringify(state.report,null,2));});
  $('export-qasm').addEventListener('click',()=>{
    const c=candidate();if(!c)return;
    const header=`// QLOOM physical implementation. Metadata is required for logical interpretation.\n// initial_mapping: ${JSON.stringify(c.initial_mapping)}\n// final_mapping: ${JSON.stringify(c.final_mapping)}\n// global_phase_radians: ${c.global_phase??0}\n// OpenQASM 2 cannot encode global phase. Preserve the JSON report or metadata sidecar.\n`;
    download(`${nameForExport()}.qasm`,header+(c.qasm||''),'text/plain');
  });
  $('export-metadata').addEventListener('click',()=>{
    const c=candidate();if(!c)return;
    download(`${nameForExport()}.metadata.json`,JSON.stringify({schema_version:state.report.schema_version,candidate_id:c.id,device:state.report.device,initial_mapping:c.initial_mapping,final_mapping:c.final_mapping,global_phase:c.global_phase,measurements:state.report.input.measurements,verification:c.verification,seed:state.report.seed,config:c.config,model:state.report.model,export_note:state.report.export_note},null,2));
  });
  async function init(){
    const results=await Promise.allSettled([api('/api/examples'),api('/api/devices')]);
    if(results[0].status==='fulfilled'){
      state.examples=results[0].value;
      $('example-select').innerHTML='<option value="">Custom circuit</option>'+state.examples.map((e)=>`<option value="${esc(e.id)}">${esc(e.name)}</option>`).join('');
      if(state.examples.length){$('example-select').value=state.examples[0].id;loadExample(state.examples[0].id);}
    }else{$('example-select').innerHTML='<option value="">Custom circuit</option>';setError(`Could not load examples: ${results[0].reason.message}`);}
    if(results[1].status==='fulfilled'){
      state.devices=results[1].value;
      $('device-select').innerHTML=state.devices.map((d)=>`<option value="${esc(d.name)}">${esc(d.name.replace(/_/g,' '))} · ${d.n_qubits} qubits</option>`).join('');
      matchCircuitWidth(); updateDeviceSummary();
    }else{$('device-select').innerHTML='<option value="">Devices unavailable</option>';setError(`Could not load devices: ${results[1].reason.message}`);}
    await loadDemo();
  }
  init();
})();
