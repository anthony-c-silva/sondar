import React, { useEffect, useState } from "react";
import {
  Plus, Pencil, Trash2, Waypoints, ArrowUp, ArrowDown, X, Gauge, Route, Activity,
  Server, Network, Lock, Hourglass, GitCompare, CircleCheckBig, TriangleAlert, History,
} from "lucide-react";
import { api } from "../api.js";
import { fmtAgo, fmtTime } from "../format.js";
import Modal from "../components/Modal.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import { SkeletonTable } from "../components/Skeleton.jsx";

const MODES = [
  { id: "sonda", label: "Por sonda", icon: Server, desc: "Uma sonda participa de um teste de vazão por vez." },
  { id: "trecho", label: "Por trecho compartilhado", icon: Network, desc: "Também aguardam os testes que passam por um mesmo enlace cadastrado." },
  { id: "global", label: "Um teste por vez", icon: Lock, desc: "Apenas um teste de vazão em toda a rede." },
];
const MODE_LABEL = Object.fromEntries(MODES.map((m) => [m.id, m.label]));

const emptyLink = { name: "", description: "", capacity_mbps: "" };
const emptyPair = { src: "", dst: "" };

// "enlace:uplink-x" -> "uplink-x"; "sonda:probe-ct-01" -> "probe-ct-01"
const resName = (r) => r.replace(/^(enlace|sonda):/, "");
const isLink = (r) => r.startsWith("enlace:");

function ResChips({ list, busy }) {
  if (!list?.length) return <span className="muted">—</span>;
  return (
    <span className="enl-chips">
      {list.map((r) => (
        <span key={r} className={"enl-chip " + (isLink(r) ? "link" : r === "global" ? "global" : "probe") + (busy?.has(r) ? " busy" : "")}>
          {isLink(r) ? <Waypoints size={11} /> : r === "global" ? <Lock size={11} /> : <Server size={11} />}
          {resName(r)}
        </span>
      ))}
    </span>
  );
}

export default function Enlaces({ notify, refreshKey }) {
  const [coord, setCoord] = useState(null);
  const [links, setLinks] = useState([]);
  const [uplinks, setUplinks] = useState({});
  const [probes, setProbes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savingMode, setSavingMode] = useState(false);

  const [linkForm, setLinkForm] = useState(null);
  const [linkMode, setLinkMode] = useState("create");
  const [saving, setSaving] = useState(false);
  const [toDelete, setToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const [chainOf, setChainOf] = useState(null); // { probe_id, links: [] }
  const [addSel, setAddSel] = useState("");

  const [pairA, setPairA] = useState(emptyPair);
  const [pairB, setPairB] = useState(emptyPair);
  const [check, setCheck] = useState(null);
  const [checking, setChecking] = useState(false);

  const loadStatic = () =>
    Promise.all([api.links(), api.uplinks(), api.probes()])
      .then(([l, u, p]) => { setLinks(l); setUplinks(u); setProbes(p); });

  const loadCoord = (silent) =>
    api.coordination()
      .then(setCoord)
      .catch((e) => { if (!silent) notify("Falha ao carregar a coordenação: " + e.message, "err"); });

  useEffect(() => {
    setLoading(true);
    Promise.all([loadStatic(), loadCoord(false)])
      .catch((e) => notify("Falha ao carregar enlaces: " + e.message, "err"))
      .finally(() => setLoading(false));
    const t = setInterval(() => loadCoord(true), 3000);
    return () => clearInterval(t);
    /* eslint-disable-next-line */
  }, [refreshKey]);

  const changeMode = async (mode) => {
    if (mode === coord?.mode) return;
    setSavingMode(true);
    try {
      await api.setCoordinationMode(mode);
      notify(`Coordenação: ${MODE_LABEL[mode]}`, "ok");
      setCheck(null);
      loadCoord(true);
    } catch (e) {
      notify("Erro ao mudar o modo: " + e.message, "err");
    } finally { setSavingMode(false); }
  };

  // ----- enlaces
  const openCreate = () => { setLinkMode("create"); setLinkForm({ ...emptyLink }); };
  const openEdit = (l) => { setLinkMode("edit"); setLinkForm({ name: l.name, description: l.description || "", capacity_mbps: l.capacity_mbps ?? "" }); };
  const saveLink = async () => {
    if (!linkForm.name.trim()) return notify("Informe o nome do enlace", "err");
    setSaving(true);
    try {
      const cap = String(linkForm.capacity_mbps).trim();
      await api.saveLink({ name: linkForm.name.trim(), description: linkForm.description, capacity_mbps: cap ? Number(cap) : null });
      notify(`Enlace '${linkForm.name}' salvo`, "ok");
      setLinkForm(null);
      loadStatic();
    } catch (e) {
      notify("Erro ao salvar o enlace: " + e.message, "err");
    } finally { setSaving(false); }
  };
  const confirmDelete = async () => {
    setDeleting(true);
    try {
      await api.delLink(toDelete.name);
      notify(`Enlace '${toDelete.name}' removido`, "ok");
      setToDelete(null);
      loadStatic();
    } catch (e) {
      notify("Erro ao remover: " + e.message, "err");
    } finally { setDeleting(false); }
  };

  // ----- cadeia por sonda
  const openChain = (pid) => { setChainOf({ probe_id: pid, links: [...(uplinks[pid] || [])] }); setAddSel(""); };
  const move = (i, d) => setChainOf((c) => {
    const l = [...c.links];
    const j = i + d;
    if (j < 0 || j >= l.length) return c;
    [l[i], l[j]] = [l[j], l[i]];
    return { ...c, links: l };
  });
  const removeAt = (i) => setChainOf((c) => ({ ...c, links: c.links.filter((_, k) => k !== i) }));
  const addLink = () => {
    if (!addSel) return;
    setChainOf((c) => (c.links.includes(addSel) ? c : { ...c, links: [...c.links, addSel] }));
    setAddSel("");
  };
  const saveChain = async () => {
    setSaving(true);
    try {
      await api.setUplinks(chainOf.probe_id, chainOf.links);
      notify(`Caminho de '${chainOf.probe_id}' salvo`, "ok");
      setChainOf(null);
      setCheck(null);
      loadStatic();
    } catch (e) {
      notify("Erro ao salvar o caminho: " + e.message, "err");
    } finally { setSaving(false); }
  };

  // ----- verificação de conflito
  const runCheck = async () => {
    if (!pairA.src || !pairA.dst || !pairB.src || !pairB.dst) return notify("Escolha origem e destino dos dois testes", "err");
    setChecking(true);
    try {
      const pairs = [pairA, pairB].map((p) => ({ source_probe: p.src, target_probe: p.dst }));
      setCheck(await api.checkConflicts({ pairs }));
    } catch (e) {
      notify("Erro ao verificar: " + e.message, "err");
    } finally { setChecking(false); }
  };

  if (loading && !coord) {
    return (<><div className="section-title"><Waypoints size={14} /> Enlaces</div><SkeletonTable rows={5} cols={4} /></>);
  }

  const mode = coord?.mode || "trecho";
  const running = coord?.running || [];
  const queue = coord?.queue || [];
  const busySet = new Set((coord?.busy || []).map((b) => b.resource));
  const busyLinks = new Set([...busySet].filter(isLink).map(resName));
  const recent = (coord?.recent || []).slice(0, 6);
  const capOf = Object.fromEntries(links.map((l) => [l.name, l.capacity_mbps]));
  const probeIds = probes.map((p) => p.probe_id);

  const PairPicker = ({ label, value, onChange }) => (
    <div className="enl-pair">
      <span className="enl-pair-label">{label}</span>
      <select value={value.src} onChange={(e) => { setCheck(null); onChange({ ...value, src: e.target.value }); }}>
        <option value="">origem…</option>
        {probeIds.map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
      <span className="enl-arrow">→</span>
      <select value={value.dst} onChange={(e) => { setCheck(null); onChange({ ...value, dst: e.target.value }); }}>
        <option value="">destino…</option>
        {probeIds.filter((p) => p !== value.src).map((p) => <option key={p} value={p}>{p}</option>)}
      </select>
    </div>
  );

  return (
    <div className="enl">
      {/* linha 1: modo e estado ao vivo */}
      <div className="enl-row">
        <div className="card">
          <div className="hd"><h3><Gauge size={15} /> Coordenação dos testes de vazão</h3></div>
          <div className="bd">
            <div className="enl-modes">
              {MODES.map(({ id, label, icon: Icon, desc }) => (
                <button key={id} type="button" disabled={savingMode}
                  className={"enl-mode" + (mode === id ? " active" : "")} onClick={() => changeMode(id)}>
                  <span className="enl-mode-hd"><Icon size={15} /> {label}</span>
                  <span className="enl-mode-desc">{desc}</span>
                </button>
              ))}
            </div>
            <div className="enl-kpis">
              <div><span className="enl-kpi-v">{running.length}</span><span className="enl-kpi-l">em execução</span></div>
              <div><span className="enl-kpi-v">{queue.length}</span><span className="enl-kpi-l">aguardando</span></div>
              <div><span className="enl-kpi-v">{links.length}</span><span className="enl-kpi-l">enlaces cadastrados</span></div>
              <div><span className="enl-kpi-v">{Object.values(uplinks).filter((l) => l.length).length}</span><span className="enl-kpi-l">sondas com caminho</span></div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="hd">
            <h3><Activity size={15} /> Agora</h3>
            <span className={"badge " + (running.length ? "ok" : "muted")}>{running.length ? "teste em andamento" : "ocioso"}</span>
          </div>
          <div className="bd enl-live">
            {running.length === 0 && queue.length === 0 && (
              <div className="enl-empty">Nenhum teste de vazão em andamento. Os testes aparecem aqui quando um plano de vazão é executado.</div>
            )}
            {running.map((r) => (
              <div key={r.id} className="enl-live-item run">
                <div className="enl-live-top">
                  <span className="badge ok">executando</span>
                  <span className="mono">{r.source_probe} → {r.target_probe || r.target}</span>
                  <span className="muted enl-right">despachado {fmtAgo(r.dispatched_at)}</span>
                </div>
                <ResChips list={r.resources} />
              </div>
            ))}
            {queue.map((q, i) => (
              <div key={i} className="enl-live-item wait">
                <div className="enl-live-top">
                  <span className="badge warn"><Hourglass size={11} /> aguardando {Math.round(q.waiting_s)} s</span>
                  <span className="mono">{q.source_probe} → {q.target_probe || q.target}</span>
                </div>
                <div className="enl-live-why">liberado quando sair: <ResChips list={q.blocked_by} busy={busySet} /></div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* linha 2: topologia e enlaces */}
      <div className="enl-row">
        <div className="card">
          <div className="hd"><h3><Route size={15} /> Caminho de cada sonda até o núcleo</h3></div>
          <div className="bd enl-topo">
            {probes.map((p) => {
              const chain = uplinks[p.probe_id] || [];
              return (
                <div key={p.probe_id} className="enl-topo-row">
                  <span className="enl-node probe"><Server size={12} /> {p.probe_id}</span>
                  {chain.map((l) => (
                    <React.Fragment key={l}>
                      <span className="enl-wire" />
                      <span className={"enl-node link" + (busyLinks.has(l) ? " busy" : "")}>
                        <Waypoints size={12} /> {l}{capOf[l] ? <em>{capOf[l]} Mb/s</em> : null}
                      </span>
                    </React.Fragment>
                  ))}
                  <span className="enl-wire" />
                  <span className="enl-node core"><Network size={12} /> núcleo</span>
                  <button className="iconbtn enl-edit" onClick={() => openChain(p.probe_id)} title="Editar caminho" aria-label="editar caminho"><Pencil size={13} /></button>
                </div>
              );
            })}
            {probes.length === 0 && <div className="enl-empty">Nenhuma sonda cadastrada.</div>}
            <div className="hint enl-foot">Testes entre duas sondas reservam os enlaces que aparecem em apenas um dos dois caminhos.</div>
          </div>
        </div>

        <div className="card">
          <div className="hd">
            <h3><Waypoints size={15} /> Enlaces</h3>
            <button className="btn small primary" onClick={openCreate}><Plus size={14} /> Adicionar</button>
          </div>
          <div className="bd enl-links">
            {links.map((l) => (
              <div key={l.name} className="enl-link">
                <div className="enl-link-main">
                  <span className="mono enl-link-name">{l.name}</span>
                  {l.capacity_mbps ? <span className="badge blue">{l.capacity_mbps} Mb/s</span> : null}
                  {busyLinks.has(l.name) && <span className="badge warn">em uso</span>}
                </div>
                <div className="enl-link-sub">
                  <span className="muted">{l.description || "sem descrição"}</span>
                  <span className="muted">· usado por {l.used_by.length ? l.used_by.join(", ") : "nenhuma sonda"}</span>
                </div>
                <div className="enl-link-act">
                  <button className="iconbtn" onClick={() => openEdit(l)} title="Editar" aria-label="editar"><Pencil size={13} /></button>
                  <button className="iconbtn danger" onClick={() => setToDelete(l)} title="Remover" aria-label="remover"><Trash2 size={13} /></button>
                </div>
              </div>
            ))}
            {links.length === 0 && <div className="enl-empty">Nenhum enlace cadastrado. Cadastre os trechos que as sondas compartilham, como o uplink de um switch.</div>}
          </div>
        </div>
      </div>

      {/* linha 3: verificador e histórico */}
      <div className="enl-row">
        <div className="card">
          <div className="hd"><h3><GitCompare size={15} /> Verificar dois testes</h3><span className="muted enl-small">modo {MODE_LABEL[mode].toLowerCase()}</span></div>
          <div className="bd">
            <PairPicker label="A" value={pairA} onChange={setPairA} />
            <PairPicker label="B" value={pairB} onChange={setPairB} />
            <div className="enl-check-act">
              <button className="btn small primary" onClick={runCheck} disabled={checking}>{checking ? <span className="spinner" /> : <GitCompare size={13} />} Verificar</button>
            </div>
            {check && (() => {
              const c = check.conflicts[0];
              return (
                <div className={"enl-verdict " + (c ? "conflict" : "free")}>
                  {c ? <TriangleAlert size={16} /> : <CircleCheckBig size={16} />}
                  <div>
                    <b>{c ? "Os dois testes não rodam juntos" : "Os dois testes podem rodar juntos"}</b>
                    <div className="enl-verdict-sub">
                      {c ? <>disputam <ResChips list={c.shared} /></> : "nenhum recurso em comum neste modo"}
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>

        <div className="card">
          <div className="hd"><h3><History size={15} /> Últimos testes de vazão</h3></div>
          <div className="bd enl-recent">
            {recent.length === 0 && <div className="enl-empty">Nenhum teste de vazão despachado desde que o controlador iniciou.</div>}
            {recent.map((r) => {
              const lk = r.resources.filter(isLink);
              return (
                <div key={r.id} className="enl-recent-row" title={fmtTime(r.dispatched_at)}>
                  <span className="muted enl-when">{fmtAgo(r.dispatched_at)}</span>
                  <span className="mono enl-test">{r.source_probe} → {r.target_probe || r.target}</span>
                  {r.waited_s >= 1
                    ? <span className="badge warn" title={(r.blocked_by || []).map(resName).join(", ")}><Hourglass size={11} /> esperou {Math.round(r.waited_s)} s</span>
                    : <span className="badge ok">sem espera</span>}
                  {lk.length ? <ResChips list={lk} /> : <span className="muted enl-small">sem enlace</span>}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* modal enlace */}
      <Modal
        open={!!linkForm}
        onClose={() => !saving && setLinkForm(null)}
        title={linkMode === "edit" ? "Editar enlace" : "Novo enlace"}
        icon={Waypoints}
        busy={saving}
        footer={
          <>
            <button className="btn" onClick={() => setLinkForm(null)} disabled={saving}>Cancelar</button>
            <button className="btn primary" onClick={saveLink} disabled={saving}>{saving ? <span className="spinner" /> : <Plus size={14} />} Salvar</button>
          </>
        }
      >
        {linkForm && (
          <div className="form-grid">
            <label className="fld">nome
              <input value={linkForm.name} disabled={linkMode === "edit"} onChange={(e) => setLinkForm({ ...linkForm, name: e.target.value })} placeholder="uplink-anexo-c" />
              <span className="hint">identificador curto do trecho</span>
            </label>
            <label className="fld">capacidade (Mb/s)
              <input type="number" min="1" value={linkForm.capacity_mbps} onChange={(e) => setLinkForm({ ...linkForm, capacity_mbps: e.target.value })} placeholder="1000" />
              <span className="hint">opcional, apenas informativo</span>
            </label>
            <label className="fld" style={{ gridColumn: "1 / -1" }}>descrição
              <input value={linkForm.description} onChange={(e) => setLinkForm({ ...linkForm, description: e.target.value })} placeholder="switch do anexo C até o núcleo do CT" />
            </label>
          </div>
        )}
      </Modal>

      {/* modal caminho */}
      <Modal
        open={!!chainOf}
        onClose={() => !saving && setChainOf(null)}
        title={chainOf ? <>Caminho de <span className="mono">{chainOf.probe_id}</span></> : ""}
        icon={Route}
        busy={saving}
        footer={
          <>
            <button className="btn" onClick={() => setChainOf(null)} disabled={saving}>Cancelar</button>
            <button className="btn primary" onClick={saveChain} disabled={saving}>{saving ? <span className="spinner" /> : null} Salvar caminho</button>
          </>
        }
      >
        {chainOf && (
          <>
            <div className="hint" style={{ marginBottom: 10 }}>
              Liste os enlaces na ordem em que o tráfego da sonda sobe até o núcleo da rede. Enlaces que duas sondas têm em
              comum acima do ponto de encontro dos caminhos não são contados no teste entre elas.
            </div>
            {chainOf.links.length === 0 && <div className="muted" style={{ marginBottom: 10 }}>Nenhum enlace no caminho.</div>}
            {chainOf.links.map((l, i) => (
              <div key={l} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span className="badge blue">{i + 1}</span>
                <span className="mono" style={{ flex: 1 }}>{l}</span>
                <button className="btn small" onClick={() => move(i, -1)} disabled={i === 0} aria-label="subir"><ArrowUp size={13} /></button>
                <button className="btn small" onClick={() => move(i, 1)} disabled={i === chainOf.links.length - 1} aria-label="descer"><ArrowDown size={13} /></button>
                <button className="btn small danger" onClick={() => removeAt(i)} aria-label="remover"><X size={13} /></button>
              </div>
            ))}
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <select value={addSel} onChange={(e) => setAddSel(e.target.value)}>
                <option value="">adicionar enlace…</option>
                {links.filter((l) => !chainOf.links.includes(l.name)).map((l) => <option key={l.name} value={l.name}>{l.name}</option>)}
              </select>
              <button className="btn small primary" onClick={addLink} disabled={!addSel}><Plus size={13} /> Adicionar</button>
            </div>
          </>
        )}
      </Modal>

      <ConfirmDialog
        open={!!toDelete}
        onClose={() => !deleting && setToDelete(null)}
        busy={deleting}
        onConfirm={confirmDelete}
        confirmLabel="Remover enlace"
        message={toDelete && <>Remover o enlace <b className="mono">{toDelete.name}</b>? Ele também sai do caminho das sondas que o usam.</>}
      />
    </div>
  );
}
