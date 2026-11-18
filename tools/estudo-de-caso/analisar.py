#!/usr/bin/env python3
"""Análise do estudo de caso do SONDAR (Capítulo 5 do TCC).

Lê os CSV gerados por exportar.sh e produz, na pasta de saída:
  figuras/*.pdf e *.png   gráficos prontos para o LaTeX (16 cm de largura)
  tabelas/*.csv e *.tex   tabelas (o .tex traz só o tabular, com vírgula decimal)
  resumo.md               principais números, para apoiar a escrita

Uso:
  python3 analisar.py dados/ --saida resultados/
  python3 analisar.py dados/ --janela "2026-11-10 13:30" "2026-11-10 14:00"   (figura de um intervalo)

Os períodos válidos de cada sonda, os grupos de destinos, o horário de uso e os
feriados ficam em config.json (ou no arquivo indicado em --config).
Requer pandas e matplotlib.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

# --------------------------------------------------------------------------
# Estilo
# --------------------------------------------------------------------------
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.5,
    "axes.titlesize": 9,
    "axes.labelsize": 8.5,
    "legend.fontsize": 7.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "pdf.fonttype": 42,
    "savefig.bbox": "tight",
})
LARGURA = 6.3  # polegadas, cerca de 16 cm
VIRGULA = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))
CORES_ETAPA = {"DNS": "#8e7cc3", "Conexão TCP": "#3d85c6", "TLS": "#e69138",
               "Espera do servidor": "#cc4125", "Transferência": "#999999"}
DIA_UTIL, FIM_SEMANA = "Dia útil", "Fim de semana e feriado"
USO, FORA = "Horário de uso", "Fora do horário de uso"


def num(v, casas=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "--"
    return f"{v:.{casas}f}".replace(".", ",")


def pct(v, casas=1):
    return num(v, casas) + "%" if v == v and v is not None else "--"


# --------------------------------------------------------------------------
# Carga e preparação
# --------------------------------------------------------------------------
class Contexto:
    def __init__(self, cfg_path, dados, saida):
        with open(cfg_path, encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.base_cfg = os.path.dirname(os.path.abspath(cfg_path))
        self.tz = self.cfg.get("fuso", "America/Sao_Paulo")
        self.dados = dados
        self.saida = saida
        self.fig_dir = os.path.join(saida, "figuras")
        self.tab_dir = os.path.join(saida, "tabelas")
        os.makedirs(self.fig_dir, exist_ok=True)
        os.makedirs(self.tab_dir, exist_ok=True)
        self.sondas = self.cfg["sondas"]
        self.resumo = []
        hu = self.cfg.get("horario_uso", {})
        self.dias_uso = set(hu.get("dias_semana", [0, 1, 2, 3, 4]))
        self.h_ini, self.h_fim = hu.get("inicio_h", 8), hu.get("fim_h", 18)
        self.feriados = {pd.Timestamp(d).date() for d in self.cfg.get("feriados", [])}

        self.dest_nome = {}
        d = self.ler("destinos")
        if d is not None:
            self.dest_nome = dict(zip(d["address"], d["name"]))
        self.end_sonda = {}
        s = self.ler("sondas", tempo=False)
        if s is not None:
            for pid, addr in zip(s["probe_id"], s["address"]):
                if isinstance(addr, str) and addr:
                    self.end_sonda[addr] = pid
        self.grupos = self.cfg.get("grupos_destino", {})

    def ler(self, nome, tempo=True):
        p = os.path.join(self.dados, nome + ".csv")
        if not os.path.exists(p):
            return None
        df = pd.read_csv(p, low_memory=False)
        if tempo and "observed_at" in df.columns:
            df["t"] = pd.to_datetime(df["observed_at"], utc=True, format="mixed").dt.tz_convert(self.tz)
        return df

    def rotulo(self, pid):
        return self.sondas.get(pid, {}).get("rotulo", pid)

    def curto(self, pid):
        return self.rotulo(pid).split(" (")[0]

    def cor(self, pid):
        return self.sondas.get(pid, {}).get("cor", "#555555")

    def nome_destino(self, alvo):
        if alvo in self.end_sonda:
            return self.rotulo(self.end_sonda[alvo])
        if alvo in self.dest_nome:
            return self.dest_nome[alvo]
        host = str(alvo).split("://")[-1].split("/")[0]
        for k, v in self.dest_nome.items():
            if host and host in str(k):
                return v
        return str(alvo)

    def grupo(self, alvo):
        for k, g in self.grupos.items():
            if alvo in g.get("enderecos", []):
                return k
        if alvo in self.end_sonda:
            return "malha"
        return "outro"

    def rotulo_grupo(self, k):
        if k == "malha":
            return "Malha entre sondas"
        return self.grupos.get(k, {}).get("rotulo", k)

    def intervalos(self, pid, chave):
        out = []
        for it in self.sondas.get(pid, {}).get(chave, []):
            ini = pd.Timestamp(it["inicio"]).tz_convert(self.tz)
            fim = pd.Timestamp(it["fim"]).tz_convert(self.tz) if it.get("fim") else None
            out.append((ini, fim))
        return out

    def filtrar(self, df, chave="estudo", col="probe_id"):
        """Mantém as linhas dentro dos intervalos de cada sonda."""
        if df is None or df.empty:
            return df
        mask = pd.Series(False, index=df.index)
        for pid in df[col].unique():
            ints = self.intervalos(pid, chave)
            m_p = df[col] == pid
            for ini, fim in ints:
                m = m_p & (df["t"] >= ini)
                if fim is not None:
                    m &= df["t"] < fim
                mask |= m
        return df[mask].copy()

    def sonda_do_alvo(self, alvo):
        host = str(alvo).split("://")[-1].split("/")[0].split(":")[0]
        return self.end_sonda.get(host)

    def filtrar_alvos(self, df, chave="estudo"):
        """Descarta medições cujo destino é uma sonda fora do seu período válido."""
        if df is None or df.empty:
            return df
        alvo = df["target"].map(self.sonda_do_alvo)
        keep = pd.Series(True, index=df.index)
        for pid in alvo.dropna().unique():
            ints = self.intervalos(pid, chave)
            if not ints:
                continue
            dentro = pd.Series(False, index=df.index)
            for ini, fim in ints:
                m = df["t"] >= ini
                if fim is not None:
                    m &= df["t"] < fim
                dentro |= m
            keep &= (alvo != pid) | dentro
        return df[keep].copy()

    def classificar(self, df):
        df["hora"] = df["t"].dt.hour
        dia = df["t"].dt.date
        util = df["t"].dt.dayofweek.isin(self.dias_uso) & ~dia.isin(self.feriados)
        df["tipo_dia"] = np.where(util, DIA_UTIL, FIM_SEMANA)
        df["uso"] = np.where(util & (df["hora"] >= self.h_ini) & (df["hora"] < self.h_fim), USO, FORA)
        return df

    def salvar_fig(self, fig, nome):
        for ext in ("pdf", "png"):
            fig.savefig(os.path.join(self.fig_dir, f"{nome}.{ext}"), dpi=200)
        plt.close(fig)
        print("  figura:", nome)

    def salvar_tab(self, df, nome, colunas_tex=None, alinhamento=None):
        df.to_csv(os.path.join(self.tab_dir, f"{nome}.csv"), index=False)
        cols = colunas_tex or list(df.columns)
        al = alinhamento or ("l" * 2 + "r" * (len(cols) - 2))
        esc = lambda s: str(s).replace("\\", "\\textbackslash{}").replace("%", "\\%").replace("_", "\\_").replace("&", "\\&").replace("#", "\\#")  # noqa: E731
        linhas = ["\\begin{tabular}{" + al + "}", "\\hline",
                  " & ".join(esc(c) for c in cols) + " \\\\", "\\hline"]
        for _, r in df.iterrows():
            linhas.append(" & ".join(esc(v) for v in r.values) + " \\\\")
        linhas += ["\\hline", "\\end{tabular}"]
        with open(os.path.join(self.tab_dir, f"{nome}.tex"), "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
        print("  tabela:", nome)

    def nota(self, texto):
        self.resumo.append(texto)

    def incidentes(self):
        p = self.cfg.get("incidentes")
        if not p:
            return []
        p = p if os.path.isabs(p) else os.path.join(self.base_cfg, p)
        if not os.path.exists(p):
            return []
        try:
            df = pd.read_csv(p, sep=";")
        except Exception:  # noqa: BLE001
            return []
        out = []
        for _, r in df.iterrows():
            try:
                t = pd.Timestamp(f"{r['data']} {r['hora_inicio']}", tz=self.tz)
            except Exception:  # noqa: BLE001
                try:
                    t = pd.Timestamp(pd.to_datetime(f"{r['data']} {r['hora_inicio']}", dayfirst=True)).tz_localize(self.tz)
                except Exception:  # noqa: BLE001
                    continue
            out.append((t, str(r.get("sintoma_relatado", ""))))
        return out


def mediana_p(serie, q):
    s = serie.dropna()
    return float(np.percentile(s, q)) if len(s) else np.nan


# --------------------------------------------------------------------------
# Sombreamento de noites e fins de semana
# --------------------------------------------------------------------------
def sombrear(ax, ctx, ini, fim):
    dia = ini.normalize()
    while dia <= fim:
        d = dia.date()
        util = dia.dayofweek in ctx.dias_uso and d not in ctx.feriados
        if not util:
            ax.axvspan(dia, dia + pd.Timedelta(days=1), color="#000000", alpha=0.07, lw=0)
        else:
            ax.axvspan(dia, dia + pd.Timedelta(hours=ctx.h_ini), color="#000000", alpha=0.035, lw=0)
            ax.axvspan(dia + pd.Timedelta(hours=ctx.h_fim), dia + pd.Timedelta(days=1), color="#000000", alpha=0.035, lw=0)
        dia += pd.Timedelta(days=1)


def eixo_datas(ax, ctx, intervalo=1):
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=intervalo, tz=ctx.tz))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m", tz=ctx.tz))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[12], tz=ctx.tz))


# --------------------------------------------------------------------------
# ICMP
# --------------------------------------------------------------------------
def preparar_icmp(ctx):
    icmp = ctx.ler("icmp")
    ex = ctx.ler("execucoes")
    if icmp is None:
        return None
    if ex is not None:
        f = ex[(ex["measurement_type"] == "icmp") & (ex["status"] != "success")].copy()
        if not f.empty:
            f = f[["observed_at", "probe_id", "target", "t"]].assign(loss_pct=100.0)
            icmp = pd.concat([icmp, f], ignore_index=True)
    icmp["grupo"] = icmp["target"].map(ctx.grupo)
    return icmp


def fig_serie_icmp(ctx, icmp_todos, grupo, campo="rtt_avg_ms", alvo=None):
    sondas = [p for p in ctx.sondas if p in set(icmp_todos["probe_id"])]
    d = icmp_todos[icmp_todos["target"] == alvo] if alvo else icmp_todos[icmp_todos["grupo"] == grupo]
    if d.empty:
        return
    est = ctx.filtrar_alvos(ctx.filtrar(d, "estudo"))
    ref = ctx.filtrar(d, "referencia")
    if est.empty:
        return
    fig, ax = plt.subplots(figsize=(LARGURA, 2.6))
    ini, fim = est["t"].min(), est["t"].max()
    if not ref.empty:
        ini = min(ini, ref["t"].min())
    sombrear(ax, ctx, ini, fim)
    for pid in sondas:
        for dd, alpha, rot in ((ref, 0.45, " (referência)"), (est, 1.0, "")):
            s = dd[dd["probe_id"] == pid].set_index("t")[campo].dropna()
            if s.empty:
                continue
            s = s.resample("15min").median().dropna()
            ax.plot(s.index, s.values, lw=0.9, color=ctx.cor(pid), alpha=alpha, label=ctx.rotulo(pid) + rot)
    for pid in sondas:
        for (ini_e, _f) in ctx.intervalos(pid, "estudo"):
            if not ref[ref["probe_id"] == pid].empty:
                ax.axvline(ini_e, color=ctx.cor(pid), ls="--", lw=0.8)
    for t, _txt in ctx.incidentes():
        if ini <= t <= fim:
            ax.axvline(t, color="#b00000", ls=":", lw=0.9)
    ax.set_ylabel("RTT médio (ms), mediana de 15 min")
    ax.yaxis.set_major_formatter(VIRGULA)
    eixo_datas(ax, ctx)
    ax.legend(ncol=3, loc="upper left", frameon=False)
    if alvo:
        ax.set_title(ctx.nome_destino(alvo))
        ctx.salvar_fig(fig, "serie_rtt_destino_" + "".join(c if c.isalnum() else "_" for c in ctx.nome_destino(alvo)))
    else:
        ax.set_title(ctx.rotulo_grupo(grupo))
        ctx.salvar_fig(fig, f"serie_rtt_{grupo}")


def fig_perfil_horario(ctx, est, grupo, campo, nome, rotulo_y, agg="median"):
    d = est[est["grupo"] == grupo]
    sondas = [p for p in ctx.sondas if p in set(d["probe_id"])]
    if not sondas:
        return
    fig, axs = plt.subplots(1, len(sondas), figsize=(LARGURA, 2.3), sharey=True, squeeze=False)
    for ax, pid in zip(axs[0], sondas):
        dp = d[d["probe_id"] == pid]
        ax.axvspan(ctx.h_ini, ctx.h_fim, color="#000000", alpha=0.05, lw=0)
        for tipo, ls in ((DIA_UTIL, "-"), (FIM_SEMANA, "--")):
            g = dp[dp["tipo_dia"] == tipo].groupby("hora")[campo]
            if g.ngroups == 0:
                continue
            y = g.median() if agg == "median" else g.mean()
            ax.plot(y.index, y.values, ls=ls, color=ctx.cor(pid), lw=1.3, label=tipo)
            if agg == "median":
                q90 = g.quantile(0.9)
                ax.fill_between(q90.index, y.reindex(q90.index), q90.values, color=ctx.cor(pid),
                                alpha=0.12 if ls == "-" else 0.06, lw=0)
        ax.set_title(ctx.rotulo(pid))
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.set_xlabel("Hora do dia")
        ax.yaxis.set_major_formatter(VIRGULA)
    axs[0][0].set_ylabel(rotulo_y)
    from matplotlib.lines import Line2D
    fig.legend(handles=[Line2D([], [], color="#444", ls="-", label=DIA_UTIL),
                        Line2D([], [], color="#444", ls="--", label=FIM_SEMANA)],
               ncol=2, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    ctx.salvar_fig(fig, f"{nome}_{grupo}")


def fig_box_uso(ctx, est, grupo):
    d = est[(est["grupo"] == grupo) & est["rtt_avg_ms"].notna()]
    sondas = [p for p in ctx.sondas if p in set(d["probe_id"])]
    if not sondas:
        return
    fig, ax = plt.subplots(figsize=(LARGURA, 2.4))
    pos, dados, cores, rot = [], [], [], []
    for i, pid in enumerate(sondas):
        for j, per in enumerate((USO, FORA)):
            v = d[(d["probe_id"] == pid) & (d["uso"] == per)]["rtt_avg_ms"].values
            if len(v):
                pos.append(i * 3 + j)
                dados.append(v)
                cores.append(ctx.cor(pid))
                rot.append(per)
    bp = ax.boxplot(dados, positions=pos, widths=0.7, whis=(5, 95), showfliers=False, patch_artist=True)
    for k, b in enumerate(bp["boxes"]):
        b.set_facecolor(cores[k])
        b.set_alpha(0.75 if rot[k] == USO else 0.3)
    for m in bp["medians"]:
        m.set_color("black")
    ax.set_xticks([i * 3 + 0.5 for i in range(len(sondas))])
    ax.set_xticklabels([ctx.rotulo(p) for p in sondas])
    ax.set_ylabel("RTT médio (ms)")
    ax.yaxis.set_major_formatter(VIRGULA)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor="#777", alpha=0.75, label=USO), Patch(facecolor="#777", alpha=0.3, label=FORA)],
              frameon=False, loc="upper right")
    ax.set_title(ctx.rotulo_grupo(grupo) + " (caixas de 25% a 75%, hastes de 5% a 95%)")
    ctx.salvar_fig(fig, f"box_rtt_uso_{grupo}")


def tabela_icmp(ctx, est):
    linhas = []
    for pid in ctx.sondas:
        for g in list(ctx.grupos) + ["malha"]:
            d = est[(est["probe_id"] == pid) & (est["grupo"] == g)]
            if d.empty:
                continue
            for per in (USO, FORA):
                x = d[d["uso"] == per]
                if x.empty:
                    continue
                rtt = x["rtt_avg_ms"]
                linhas.append({
                    "Sonda": ctx.rotulo(pid), "Destinos": ctx.rotulo_grupo(g), "Período": per,
                    "Medições": len(x),
                    "RTT mediano (ms)": num(mediana_p(rtt, 50), 2), "RTT p95 (ms)": num(mediana_p(rtt, 95), 2),
                    "Perda média": pct(x["loss_pct"].mean(), 2),
                    "Medições com perda": pct(100 * (x["loss_pct"] > 0).mean(), 1),
                })
    if linhas:
        ctx.salvar_tab(pd.DataFrame(linhas), "icmp_resumo", alinhamento="lllrrrrr")
    return linhas


# --------------------------------------------------------------------------
# HTTP por etapas
# --------------------------------------------------------------------------
def preparar_http(ctx):
    h = ctx.ler("http")
    if h is None or h.empty:
        return None
    h = h[h["http_status"].notna()].copy()
    h["https"] = h["target"].astype(str).str.startswith("https")
    soma = h["dns_ms"].fillna(0) + h["tcp_connect_ms"].fillna(0) + h["tls_handshake_ms"].fillna(0)
    h["espera_ms"] = (h["ttfb_ms"] - soma).clip(lower=0)
    h["transf_ms"] = (h["total_ms"] - h["ttfb_ms"]).clip(lower=0)
    h["destino"] = h["target"].map(ctx.nome_destino)
    return h


ETAPAS = [("DNS", "dns_ms"), ("Conexão TCP", "tcp_connect_ms"), ("TLS", "tls_handshake_ms"),
          ("Espera do servidor", "espera_ms"), ("Transferência", "transf_ms")]


def fig_http_etapas(ctx, h):
    d = h[h["https"]]
    if d.empty:
        return
    grupos = d.groupby(["destino", "probe_id"])
    chaves = sorted(grupos.groups.keys(), key=lambda k: (k[0], list(ctx.sondas).index(k[1]) if k[1] in ctx.sondas else 9))
    fig, ax = plt.subplots(figsize=(LARGURA, 0.35 * len(chaves) + 0.9))
    y = np.arange(len(chaves))[::-1]
    esquerda = np.zeros(len(chaves))
    for nome, col in ETAPAS:
        vals = np.array([grupos.get_group(k)[col].median() for k in chaves])
        ax.barh(y, vals, left=esquerda, color=CORES_ETAPA[nome], label=nome, height=0.65)
        esquerda += np.nan_to_num(vals)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{k[0]}  ·  {ctx.rotulo(k[1])}" for k in chaves])
    ax.set_xlabel("Tempo mediano (ms)")
    ax.xaxis.set_major_formatter(VIRGULA)
    ax.legend(ncol=5, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0))
    ax.grid(axis="y", alpha=0)
    ctx.salvar_fig(fig, "http_etapas")


def fig_http_horario(ctx, h):
    d = h[h["https"] & (h["tipo_dia"] == DIA_UTIL)]
    if d.empty:
        return
    for destino in sorted(d["destino"].unique()):
        dd = d[d["destino"] == destino]
        sondas = [p for p in ctx.sondas if p in set(dd["probe_id"])]
        fig, axs = plt.subplots(1, len(sondas), figsize=(LARGURA, 2.3), sharey=True, squeeze=False)
        for ax, pid in zip(axs[0], sondas):
            dp = dd[dd["probe_id"] == pid].groupby("hora")
            horas = np.arange(24)
            base = np.zeros(24)
            for nome, col in ETAPAS:
                v = dp[col].median().reindex(horas).values
                ax.bar(horas, np.nan_to_num(v), bottom=base, color=CORES_ETAPA[nome], width=0.85, label=nome)
                base += np.nan_to_num(v)
            ax.set_title(ctx.rotulo(pid))
            ax.set_xticks([0, 6, 12, 18, 23])
            ax.set_xlabel("Hora do dia (dias úteis)")
            ax.yaxis.set_major_formatter(VIRGULA)
        axs[0][0].set_ylabel("Tempo mediano (ms)")
        h_, l_ = axs[0][0].get_legend_handles_labels()
        fig.legend(h_, l_, ncol=5, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 0.0))
        fig.tight_layout(rect=(0, 0.1, 1, 1))
        seguro = "".join(c if c.isalnum() else "_" for c in destino)[:40]
        ctx.salvar_fig(fig, f"http_horario_{seguro}")


def tabela_http(ctx, h, ex):
    linhas = []
    for (destino, pid), g in sorted(h.groupby(["destino", "probe_id"]), key=lambda x: (x[0][0], x[0][1])):
        falhas = 0
        if ex is not None:
            alvo = g["target"].iloc[0]
            e = ex[(ex["measurement_type"] == "http") & (ex["probe_id"] == pid) & (ex["target"] == alvo)]
            falhas = int((e["status"] != "success").sum())
        linhas.append({
            "Destino": destino, "Sonda": ctx.rotulo(pid), "Medições": len(g), "Falhas": falhas,
            "DNS": num(g["dns_ms"].median(), 1), "TCP": num(g["tcp_connect_ms"].median(), 1),
            "TLS": num(g["tls_handshake_ms"].median(), 1) if g["https"].iloc[0] else "--",
            "Espera": num(g["espera_ms"].median(), 1), "Total": num(g["total_ms"].median(), 1),
            "Total p95": num(mediana_p(g["total_ms"], 95), 1),
        })
    if linhas:
        ctx.salvar_tab(pd.DataFrame(linhas), "http_etapas", alinhamento="llrrrrrrrr")


def fig_janela(ctx, h, ini, fim, destino=None):
    t0 = pd.Timestamp(ini, tz=ctx.tz)
    t1 = pd.Timestamp(fim, tz=ctx.tz)
    d = h[(h["t"] >= t0) & (h["t"] <= t1)]
    if destino:
        d = d[d["destino"].str.contains(destino, case=False) | d["target"].str.contains(destino, case=False)]
    if d.empty:
        print("  janela sem dados HTTP")
        return
    fig, axs = plt.subplots(1, 3, figsize=(LARGURA, 2.2), sharex=True)
    for ax, (nome, col) in zip(axs, (("Conexão TCP", "tcp_connect_ms"), ("TLS", "tls_handshake_ms"),
                                       ("Espera do servidor", "espera_ms"))):
        estilos = {dd: ls for dd, ls in zip(sorted(d["destino"].unique()), ["-", "--", ":", "-."])}
        for (dest, pid), g in d.groupby(["destino", "probe_id"]):
            ax.plot(g["t"], g[col], marker="o", ms=2.5, lw=0.9, color=ctx.cor(pid), ls=estilos[dest],
                    label=f"{dest} · {ctx.rotulo(pid)}")
        ax.set_title(nome)
        ax.yaxis.set_major_formatter(VIRGULA)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=ctx.tz))
        ax.tick_params(axis="x", rotation=45)
    axs[0].set_ylabel("ms")
    h_, l_ = axs[0].get_legend_handles_labels()
    fig.legend(h_, l_, ncol=3, frameon=False, fontsize=6.5, loc="lower center", bbox_to_anchor=(0.5, -0.18))
    ctx.salvar_fig(fig, "http_janela_" + t0.strftime("%Y%m%d_%H%M"))


# --------------------------------------------------------------------------
# Vazão
# --------------------------------------------------------------------------
def preparar_vazao(ctx):
    v = ctx.ler("iperf")
    if v is None or v.empty:
        return None
    v = v[v["throughput_bps"].notna()].copy()
    v["Mbps"] = v["throughput_bps"] / 1e6
    alvo = v["target_probe"].fillna("")
    rev = v["direction"].astype(str) == "target_to_source"
    v["de"] = np.where(rev, alvo, v["probe_id"])
    v["para"] = np.where(rev, v["probe_id"], alvo)
    v["fluxo"] = [f"{ctx.curto(a)} → {ctx.curto(b)}" for a, b in zip(v["de"], v["para"])]
    return v


def filtrar_vazao(ctx, v, chave):
    """Um fluxo vale no período se ambas as sondas estiverem no período informado
    (sondas sem intervalo nessa chave não restringem)."""
    keep = pd.Series(True, index=v.index)
    algum = pd.Series(False, index=v.index)
    for col in ("de", "para"):
        for pid in v[col].unique():
            ints = ctx.intervalos(pid, chave)
            m_p = v[col] == pid
            if not ints:
                continue
            dentro = pd.Series(False, index=v.index)
            for ini, fim in ints:
                m = v["t"] >= ini
                if fim is not None:
                    m &= v["t"] < fim
                dentro |= m
            keep &= ~m_p | dentro
            algum |= m_p & dentro
    if chave == "referencia":
        keep &= algum
    return v[keep].copy()


def fig_vazao_serie(ctx, v_todos):
    fluxos = sorted(v_todos["fluxo"].unique())
    if not fluxos:
        return
    fig, ax = plt.subplots(figsize=(LARGURA, 2.6))
    ini, fim = v_todos["t"].min(), v_todos["t"].max()
    sombrear(ax, ctx, ini, fim)
    marcadores = "os^vD<>p"
    for i, f in enumerate(fluxos):
        d = v_todos[v_todos["fluxo"] == f]
        pid = d["de"].iloc[0] if d["de"].iloc[0] in ctx.sondas and d["de"].iloc[0] != "probe-srv-01" else d["para"].iloc[0]
        ax.scatter(d["t"], d["Mbps"], s=7, marker=marcadores[i % len(marcadores)], color=ctx.cor(pid),
                   alpha=0.8, label=f, lw=0)
    for pid in ctx.sondas:
        if ctx.intervalos(pid, "referencia"):
            for ini_e, _ in ctx.intervalos(pid, "estudo"):
                ax.axvline(ini_e, color=ctx.cor(pid), ls="--", lw=0.8)
    ax.set_yscale("log")
    ax.set_yticks([10, 30, 100, 300, 1000])
    ax.yaxis.set_major_formatter(VIRGULA)
    ax.set_ylabel("Vazão (Mb/s, escala logarítmica)")
    eixo_datas(ax, ctx)
    ax.legend(ncol=3, frameon=False, fontsize=6.5, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ctx.salvar_fig(fig, "vazao_serie")


def fig_vazao_horario(ctx, v):
    fluxos = [f for f in sorted(v["fluxo"].unique())]
    if not fluxos:
        return
    n = len(fluxos)
    cols = min(2, n)
    lin = int(np.ceil(n / cols))
    fig, axs = plt.subplots(lin, cols, figsize=(LARGURA, 1.75 * lin), sharex=True, squeeze=False)
    for k, f in enumerate(fluxos):
        ax = axs[k // cols][k % cols]
        d = v[v["fluxo"] == f]
        pid = d["de"].iloc[0] if d["de"].iloc[0] != "probe-srv-01" else d["para"].iloc[0]
        ax.axvspan(ctx.h_ini, ctx.h_fim, color="#000000", alpha=0.05, lw=0)
        for tipo, mk in ((DIA_UTIL, "o"), (FIM_SEMANA, "x")):
            dd = d[d["tipo_dia"] == tipo]
            ax.scatter(dd["hora"] + (0.15 if tipo == FIM_SEMANA else -0.15), dd["Mbps"], s=8, marker=mk,
                       color=ctx.cor(pid), alpha=0.6 if tipo == DIA_UTIL else 0.9, label=tipo, lw=0.8)
            med = dd.groupby("hora")["Mbps"].median()
            if tipo == DIA_UTIL and len(med):
                ax.plot(med.index, med.values, color=ctx.cor(pid), lw=1)
        ax.set_title(f, fontsize=8)
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.yaxis.set_major_formatter(VIRGULA)
    for k in range(n, lin * cols):
        axs[k // cols][k % cols].axis("off")
    for a in axs[-1]:
        a.set_xlabel("Hora do dia")
    for a in axs[:, 0]:
        a.set_ylabel("Vazão (Mb/s)")
    h_, l_ = axs[0][0].get_legend_handles_labels()
    fig.legend(h_[:2], l_[:2], ncol=2, frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.03))
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    ctx.salvar_fig(fig, "vazao_horario")


def tabela_vazao(ctx, v, ex):
    linhas = []
    for f, g in v.groupby("fluxo"):
        for per in (USO, FORA):
            x = g[g["uso"] == per]["Mbps"]
            if x.empty:
                continue
            linhas.append({"Fluxo": f, "Período": per, "Testes": len(x),
                           "Mediana (Mb/s)": num(x.median(), 1), "p10 (Mb/s)": num(mediana_p(x, 10), 1),
                           "Mínimo (Mb/s)": num(x.min(), 1), "Máximo (Mb/s)": num(x.max(), 1)})
    if linhas:
        ctx.salvar_tab(pd.DataFrame(linhas), "vazao_resumo", alinhamento="llrrrrr")
    if ex is not None:
        e = ex[ex["measurement_type"] == "iperf3"]
        if len(e):
            ctx.nota(f"Testes de vazão no período exportado: {len(e)} execuções, "
                     f"{int((e['status'] != 'success').sum())} com falha.")


# --------------------------------------------------------------------------
# DNS, rotas, consumo, falhas, antes e depois
# --------------------------------------------------------------------------
def tabela_dns(ctx, est_dns, ex):
    if est_dns is None or est_dns.empty:
        return
    linhas = []
    for (pid, res), g in est_dns.groupby(["probe_id", "resolver"]):
        for per in (USO, FORA):
            x = g[g["uso"] == per]["elapsed_ms"]
            if x.empty:
                continue
            linhas.append({"Sonda": ctx.rotulo(pid), "Resolvedor": ctx.nome_destino(res), "Período": per,
                           "Consultas": len(x), "Mediana (ms)": num(x.median(), 1),
                           "p95 (ms)": num(mediana_p(x, 95), 1)})
    if linhas:
        ctx.salvar_tab(pd.DataFrame(linhas), "dns_resumo", alinhamento="lllrrr")


def tabela_rotas(ctx, tr):
    if tr is None or tr.empty:
        return
    linhas, mudancas = [], []
    for (pid, alvo), g in tr.sort_values("t").groupby(["probe_id", "target"]):
        assin = []
        for hops in g["hops"]:
            try:
                hh = json.loads(hops) if isinstance(hops, str) else []
            except Exception:  # noqa: BLE001
                hh = []
            assin.append(">".join(str(x.get("address") or "*") for x in hh))
        g = g.assign(assinatura=assin)
        troca = g["assinatura"] != g["assinatura"].shift()
        n_trocas = int(troca.sum()) - 1
        for _, r in g[troca].iloc[1:].iterrows():
            mudancas.append({"Quando": r["t"].strftime("%d/%m %H:%M"), "Sonda": ctx.rotulo(pid),
                             "Destino": ctx.nome_destino(alvo), "Saltos": r["hop_count"]})
        linhas.append({"Sonda": ctx.rotulo(pid), "Destino": ctx.nome_destino(alvo), "Medições": len(g),
                       "Caminhos distintos": g["assinatura"].nunique(), "Mudanças de caminho": max(n_trocas, 0),
                       "Saltos (mediana)": num(g["hop_count"].median(), 0)})
    ctx.salvar_tab(pd.DataFrame(linhas), "rotas_resumo", alinhamento="llrrrr")
    if mudancas:
        ctx.salvar_tab(pd.DataFrame(mudancas), "rotas_mudancas", alinhamento="lllr")


def tabela_consumo(ctx, saude):
    if saude is None or saude.empty:
        return
    linhas = []
    for pid, g in saude.groupby("probe_id"):
        mem_uso = 100 * (1 - g["mem_available_kb"] / g["mem_total_kb"])
        linhas.append({
            "Sonda": ctx.rotulo(pid), "Amostras": len(g),
            "CPU do agente média": pct(g["agent_cpu_pct"].mean(), 2),
            "CPU do agente p95": pct(mediana_p(g["agent_cpu_pct"], 95), 2),
            "Memória do agente média (MB)": num(g["agent_rss_kb"].mean() / 1024, 1),
            "Memória do agente máx. (MB)": num(g["agent_rss_kb"].max() / 1024, 1),
            "CPU da sonda média": pct(g["cpu_usage_pct"].mean(), 1),
            "Memória em uso média": pct(mem_uso.mean(), 1),
            "Temperatura média (°C)": num(g["cpu_temp_c"].mean(), 1),
            "Temperatura máx. (°C)": num(g["cpu_temp_c"].max(), 1),
            "Amostras com limitação": int((g["throttled_now"] > 0).sum()),
        })
    ctx.salvar_tab(pd.DataFrame(linhas), "consumo_sondas", alinhamento="l" + "r" * 10)
    for pid, g in saude.groupby("probe_id"):
        if g["link_speed_mbps"].notna().any():
            ctx.nota(f"{ctx.rotulo(pid)}: velocidade do enlace mais frequente "
                     f"{int(g['link_speed_mbps'].mode().iloc[0])} Mb/s.")


def fig_consumo(ctx, saude):
    if saude is None or saude.empty or saude["agent_cpu_pct"].isna().all():
        return
    fig, axs = plt.subplots(1, 2, figsize=(LARGURA, 2.2))
    for pid, g in saude.groupby("probe_id"):
        s = g.set_index("t")
        axs[0].plot(s["agent_cpu_pct"].resample("2h").mean(), color=ctx.cor(pid), lw=0.9, label=ctx.rotulo(pid))
        axs[1].plot(s["cpu_temp_c"].resample("1h").mean(), color=ctx.cor(pid), lw=0.9)
    axs[0].set_ylabel("CPU do agente (%)")
    axs[1].set_ylabel("Temperatura (°C)")
    for a in axs:
        eixo_datas(a, ctx, intervalo=2)
        a.yaxis.set_major_formatter(VIRGULA)
    h_, l_ = axs[0].get_legend_handles_labels()
    fig.legend(h_, l_, ncol=3, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    ctx.salvar_fig(fig, "consumo_sondas")


def tabela_falhas(ctx, ex):
    if ex is None or ex.empty:
        return
    ex = ctx.filtrar(ex, "estudo")
    linhas = []
    for (pid, tipo), g in ex.groupby(["probe_id", "measurement_type"]):
        linhas.append({"Sonda": ctx.rotulo(pid), "Tipo": tipo, "Execuções": len(g),
                       "Sucesso": pct(100 * (g["status"] == "success").mean(), 1)})
    ctx.salvar_tab(pd.DataFrame(linhas), "execucoes_sucesso", alinhamento="llrr")


def tabela_antes_depois(ctx, icmp, v):
    linhas = []
    for pid in ctx.sondas:
        if not ctx.intervalos(pid, "referencia"):
            continue
        for chave, rot in (("referencia", "Antes"), ("estudo", "Depois")):
            loc = ", ".join(i.get("local", "") for i in ctx.sondas[pid].get(chave, []))
            linha = {"Sonda": ctx.rotulo(pid), "Fase": f"{rot} ({loc})"}
            if icmp is not None:
                d = ctx.filtrar(icmp[(icmp["probe_id"] == pid) & (icmp["grupo"] == "infra")], chave)
                if not d.empty:
                    d = ctx.classificar(d)
                    linha["RTT infra, mediana (ms)"] = num(mediana_p(d["rtt_avg_ms"], 50), 2)
                    linha["RTT infra, p95 em uso (ms)"] = num(mediana_p(d[d["uso"] == USO]["rtt_avg_ms"], 95), 2)
                    linha["Perda média"] = pct(d["loss_pct"].mean(), 2)
            if v is not None:
                vv = filtrar_vazao(ctx, v[(v["de"] == pid) | (v["para"] == pid)], chave)
                for sentido, mask in (("envio", vv["de"] == pid), ("recebimento", vv["para"] == pid)):
                    x = vv[mask]["Mbps"]
                    linha[f"Vazão {sentido}, mediana (Mb/s)"] = num(x.median(), 1) if len(x) else "--"
            linhas.append(linha)
    if linhas:
        df = pd.DataFrame(linhas).fillna("--")
        ctx.salvar_tab(df, "antes_depois", alinhamento="ll" + "r" * (len(df.columns) - 2))


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dados")
    ap.add_argument("--saida", default="resultados")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
    ap.add_argument("--janela", nargs=2, metavar=("INICIO", "FIM"))
    ap.add_argument("--destino", default=None, help="filtro de destino para --janela")
    args = ap.parse_args()
    ctx = Contexto(args.config, args.dados, args.saida)
    ex = ctx.ler("execucoes")

    print("ICMP")
    icmp = preparar_icmp(ctx)
    if icmp is not None and not icmp.empty:
        for g in list(ctx.grupos) + ["malha"]:
            fig_serie_icmp(ctx, icmp, g)
        for alvo in ctx.grupos.get("externo", {}).get("enderecos", []):
            fig_serie_icmp(ctx, icmp, "externo", alvo=alvo)
        est = ctx.classificar(ctx.filtrar_alvos(ctx.filtrar(icmp, "estudo")))
        for g in list(ctx.grupos) + ["malha"]:
            fig_perfil_horario(ctx, est, g, "rtt_avg_ms", "perfil_rtt", "RTT médio (ms)")
            fig_perfil_horario(ctx, est, g, "loss_pct", "perfil_perda", "Perda média (%)", agg="mean")
        fig_box_uso(ctx, est, "infra")
        for l in tabela_icmp(ctx, est):
            if l["Destinos"] == ctx.rotulo_grupo("infra"):
                ctx.nota(f"ICMP {l['Sonda']}, {l['Período'].lower()}: RTT mediano {l['RTT mediano (ms)']} ms, "
                         f"p95 {l['RTT p95 (ms)']} ms, perda média {l['Perda média']}.")

    print("HTTP")
    h = preparar_http(ctx)
    if h is not None and not h.empty:
        if args.janela:
            fig_janela(ctx, h, args.janela[0], args.janela[1], args.destino)
        he = ctx.classificar(ctx.filtrar_alvos(ctx.filtrar(h, "estudo")))
        if not he.empty:
            fig_http_etapas(ctx, he)
            fig_http_horario(ctx, he)
            tabela_http(ctx, he, ex)
            maior = he[he["https"]].nlargest(5, "tls_handshake_ms")
            for _, r in maior.iterrows():
                ctx.nota(f"Maior TLS: {r['t'].strftime('%d/%m %H:%M')} {r['destino']} ({ctx.rotulo(r['probe_id'])}): "
                         f"TLS {num(r['tls_handshake_ms'])} ms com conexão TCP {num(r['tcp_connect_ms'])} ms.")

    print("Vazão")
    v = preparar_vazao(ctx)
    if v is not None and not v.empty:
        validos = pd.concat([filtrar_vazao(ctx, v, "estudo"), filtrar_vazao(ctx, v, "referencia")]).drop_duplicates()
        fig_vazao_serie(ctx, validos)
        ve = ctx.classificar(filtrar_vazao(ctx, v, "estudo"))
        fig_vazao_horario(ctx, ve)
        tabela_vazao(ctx, ve, ex)

    print("DNS, rotas, consumo")
    dns = ctx.ler("dns")
    if dns is not None and not dns.empty:
        tabela_dns(ctx, ctx.classificar(ctx.filtrar(dns, "estudo")), ex)
    tr = ctx.ler("traceroute")
    if tr is not None and not tr.empty:
        tabela_rotas(ctx, ctx.filtrar(tr, "estudo"))
    saude = ctx.ler("saude")
    if saude is not None and not saude.empty:
        s_est = ctx.filtrar(saude, "estudo")
        tabela_consumo(ctx, s_est)
        fig_consumo(ctx, s_est)
    tabela_falhas(ctx, ex)
    tabela_antes_depois(ctx, icmp, v)

    with open(os.path.join(args.saida, "resumo.md"), "w", encoding="utf-8") as f:
        f.write("# Resumo automático do estudo de caso\n\n")
        for n in ctx.resumo:
            f.write(f"- {n}\n")
    print(f"pronto: {args.saida}/")


if __name__ == "__main__":
    sys.exit(main())
