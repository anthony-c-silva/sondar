#!/usr/bin/env python3
"""Relatório do teste de escalabilidade no formato do TCC.

Lê, numa pasta, os arquivos gerados pelo teste:
  loadgen_log.csv          carga em degraus
  maximo_log.csv           modo máximo com confirmação (opcional)
  maximo_rapido_log.csv    modo máximo sem confirmação (opcional)
  monitor_log.csv          métricas do servidor

Gera em --saida: figuras (PDF e PNG, 16 cm), tabelas (CSV e trecho LaTeX com
vírgula decimal) e resumo.md.

Uso: python3 relatorio.py pasta_dos_logs --saida resultados_escalabilidade
"""
import argparse
import os

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5, "axes.titlesize": 9, "legend.fontsize": 7.5,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "pdf.fonttype": 42, "savefig.bbox": "tight",
})
LARGURA = 6.3
VIRG = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))
TZ = "America/Sao_Paulo"
CONT = {"ufsm-ingestion": ("Ingestão", "#cc4125"), "ufsm-timescaledb": ("Banco de dados", "#3d85c6"),
        "ufsm-rabbitmq": ("Barramento (RabbitMQ)", "#e69138"), "ufsm-controller": ("Controlador", "#6aa84f")}
PERFIL_MSG_S = 5.13 / 60  # mensagens por segundo de uma sonda com os planos usados


def n(v, c=1):
    return "--" if v is None or v != v else f"{v:.{c}f}".replace(".", ",")


def ler(p):
    df = pd.read_csv(p)
    df["ts"] = pd.to_datetime(df["ts"], utc=True, format="mixed")
    return df


def salvar_fig(fig, saida, nome):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(saida, "figuras", f"{nome}.{ext}"), dpi=200)
    plt.close(fig)


def salvar_tab(df, saida, nome, al):
    df.to_csv(os.path.join(saida, "tabelas", f"{nome}.csv"), index=False)
    esc = lambda s: str(s).replace("%", "\\%").replace("_", "\\_").replace("&", "\\&")  # noqa: E731
    lin = ["\\begin{tabular}{" + al + "}", "\\hline", " & ".join(esc(c) for c in df.columns) + " \\\\", "\\hline"]
    lin += [" & ".join(esc(v) for v in r) + " \\\\" for r in df.values]
    lin += ["\\hline", "\\end{tabular}"]
    with open(os.path.join(saida, "tabelas", f"{nome}.tex"), "w", encoding="utf-8") as f:
        f.write("\n".join(lin) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pasta")
    ap.add_argument("--saida", default="resultados_escalabilidade")
    a = ap.parse_args()
    for sub in ("figuras", "tabelas"):
        os.makedirs(os.path.join(a.saida, sub), exist_ok=True)
    mon = ler(os.path.join(a.pasta, "monitor_log.csv"))
    lg = ler(os.path.join(a.pasta, "loadgen_log.csv"))
    lg = lg[lg["degrau"] > 0]
    resumo = []

    # ---------------- degraus ----------------
    linhas = []
    for passo, g in lg.groupby("degrau"):
        ini, fim = g["ts"].min(), g["ts"].max()
        corte = ini + (fim - ini) * 0.3  # descarta o aquecimento
        m = mon[(mon["ts"] >= corte) & (mon["ts"] <= fim)]
        gg = g[g["ts"] >= corte]
        dur = (gg["ts"].max() - gg["ts"].min()).total_seconds() or 1
        pub = (gg["publicadas_total"].max() - gg["publicadas_total"].min()) / dur
        d = {"degrau": passo, "sondas": int(g["sondas"].iloc[0]), "oferta": float(g["oferta_msg_s"].iloc[0]),
             "publicado": pub, "consumo": m["consumo_msg_s"].mean(), "fila_max": int(m["fila_msgs"].max())}
        for c in CONT:
            d[c + "_cpu"] = m[f"{c}_cpu_pct"].mean()
            d[c + "_mem"] = m[f"{c}_mem_mib"].mean()
        d["bytes_msg"] = (m["db_bytes"].iloc[-1] - m["db_bytes"].iloc[0]) / max(pub * (m["ts"].iloc[-1] - m["ts"].iloc[0]).total_seconds(), 1)
        linhas.append(d)
    dg = pd.DataFrame(linhas)

    # ---------------- modo máximo sem confirmação: drenagem ----------------
    cap = None
    p_rap = os.path.join(a.pasta, "maximo_rapido_log.csv")
    if os.path.exists(p_rap):
        r = ler(p_rap)
        janela = mon[mon["ts"] >= r["ts"].min() - pd.Timedelta("1min")]
        i_pico = janela["fila_msgs"].idxmax()
        t_pico, pico = mon.loc[i_pico, "ts"], int(mon.loc[i_pico, "fila_msgs"])
        depois = mon.loc[i_pico:]
        zero = depois[depois["fila_msgs"] == 0]
        t_zero = zero["ts"].iloc[0] if len(zero) else depois["ts"].iloc[-1]
        dren = mon[(mon["ts"] > t_pico) & (mon["ts"] < t_zero)]
        pubw = mon[(mon["ts"] >= r["ts"].min()) & (mon["ts"] <= r["ts"].max())]
        total_pub = int(r["publicadas_total"].max())
        taxa_pub = total_pub / max((r["ts"].max() - r["ts"].min()).total_seconds(), 1)
        cap = dren["consumo_msg_s"].median()
        bytes_dren = (dren["db_bytes"].iloc[-1] - janela["db_bytes"].iloc[0]) / total_pub
        resumo += [
            f"Modo máximo sem confirmação: {total_pub} mensagens publicadas em 2 min ({n(taxa_pub, 0)} msg/s); "
            f"o RabbitMQ registrou até {n(pubw['entrada_msg_s'].max(), 0)} msg/s de entrada, com CPU média de "
            f"{n(pubw['ufsm-rabbitmq_cpu_pct'].mean(), 0)}% de um núcleo e até {n(pubw['ufsm-rabbitmq_mem_mib'].max(), 0)} MiB de memória.",
            f"Fila máxima de {pico} mensagens, esvaziada em {n((t_zero - t_pico).total_seconds() / 60, 0)} min.",
            f"Capacidade da ingestão durante a drenagem: mediana {n(cap, 1)} msg/s, média {n(dren['consumo_msg_s'].mean(), 1)} "
            f"(desvio {n(dren['consumo_msg_s'].std(), 1)}).",
            f"CPU média durante a drenagem (em % de um núcleo): ingestão {n(dren['ufsm-ingestion_cpu_pct'].mean())}%, "
            f"banco {n(dren['ufsm-timescaledb_cpu_pct'].mean())}%, RabbitMQ {n(dren['ufsm-rabbitmq_cpu_pct'].mean())}%. "
            f"Nenhum componente saturou o processador, o que indica que o limite vem da gravação de uma mensagem por "
            f"transação num único consumidor.",
            f"Atraso máximo de ingestão na drenagem: {n(dren['atraso_ingestao_s'].max() / 60, 0)} min.",
            f"Crescimento do banco: {n(bytes_dren, 0)} bytes por mensagem.",
        ]
        # figura da drenagem
        seg = mon[(mon["ts"] >= r["ts"].min() - pd.Timedelta("3min")) & (mon["ts"] <= t_zero + pd.Timedelta("3min"))]
        fig, ax = plt.subplots(figsize=(LARGURA, 2.4))
        tl = seg["ts"].dt.tz_convert(TZ)
        ax.plot(tl, seg["fila_msgs"] / 1000, color="#3d85c6", lw=1.2, label="Mensagens na fila (mil)")
        ax.set_ylabel("Mensagens na fila (mil)")
        ax.yaxis.set_major_formatter(VIRG)
        ax2 = ax.twinx()
        ax2.plot(tl, seg["consumo_msg_s"].rolling(6, min_periods=1).mean(), color="#cc4125", lw=0.9,
                 label="Gravação pela ingestão (msg/s)")
        ax2.set_ylabel("Gravação (msg/s)")
        ax2.grid(False)
        ax2.spines["right"].set_visible(True)
        ax2.set_ylim(0, max(150, seg["consumo_msg_s"].max() * 1.1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=TZ))
        ax.set_xlabel("Horário")
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, frameon=False, loc="upper right")
        salvar_fig(fig, a.saida, "escalabilidade_drenagem")

    p_conf = os.path.join(a.pasta, "maximo_log.csv")
    if os.path.exists(p_conf):
        c = ler(p_conf)
        tot = int(c["publicadas_total"].max())
        resumo.insert(0, f"Modo máximo com confirmação (uma conexão): {tot} mensagens em 2 min "
                         f"({n(tot / max((c['ts'].max() - c['ts'].min()).total_seconds(), 1), 0)} msg/s), limite do "
                         f"gerador, que aguarda a confirmação de cada mensagem.")

    # ---------------- figuras dos degraus ----------------
    fig, ax = plt.subplots(figsize=(LARGURA, 2.5))
    for cnt, (rot, cor) in CONT.items():
        ax.plot(dg["sondas"], dg[cnt + "_cpu"], marker="o", ms=3.5, color=cor, label=rot)
    ax.set_xscale("log")
    ax.set_xticks(dg["sondas"])
    ax.set_xticklabels([str(x) for x in dg["sondas"]])
    ax.set_xlabel("Sondas simuladas")
    ax.set_ylabel("CPU média (% de um núcleo)")
    ax.yaxis.set_major_formatter(VIRG)
    ax.legend(frameon=False, loc="upper left")
    salvar_fig(fig, a.saida, "escalabilidade_cpu")

    fig, ax = plt.subplots(figsize=(LARGURA, 2.5))
    ax.plot(dg["sondas"], dg["oferta"], marker="o", ms=3.5, color="#999999", label="Carga gerada")
    ax.plot(dg["sondas"], dg["consumo"], marker="s", ms=3.5, color="#cc4125", label="Gravação pela ingestão")
    if cap:
        ax.axhline(cap, color="#cc4125", ls="--", lw=0.9)
        ax.text(dg["sondas"].min(), cap * 1.03, f"capacidade medida da ingestão ({n(cap, 0)} msg/s)",
                fontsize=7, color="#cc4125")
        xs = np.geomspace(dg["sondas"].max(), 2000, 100)
        ax.plot(xs, xs * PERFIL_MSG_S, color="#999999", lw=0.9, ls=":", label="Carga projetada")
        lim = cap / PERFIL_MSG_S
        ax.axvline(lim, color="#777777", ls=":", lw=0.8)
        ax.text(lim * 1.03, cap * 0.35, f"cerca de\n{n(lim, 0)} sondas", fontsize=7, color="#555555")
        ax.set_ylim(0, cap * 1.2)
        ax.set_xlim(8, 2200)
    ax.set_xscale("log")
    ax.set_xticks(list(dg["sondas"]) + [2000])
    ax.set_xticklabels([str(x) for x in dg["sondas"]] + ["2000"])
    ax.minorticks_off()
    ax.set_xlabel("Sondas (simuladas até 1000)")
    ax.set_ylabel("Mensagens por segundo")
    ax.yaxis.set_major_formatter(VIRG)
    ax.legend(frameon=False, loc="center left")
    salvar_fig(fig, a.saida, "escalabilidade_vazao")

    # ---------------- tabelas ----------------
    t = pd.DataFrame({
        "Sondas": dg["sondas"],
        "Carga (msg/s)": [n(x, 1) for x in dg["oferta"]],
        "Gravação (msg/s)": [n(x, 1) for x in dg["consumo"]],
        "Fila máx.": dg["fila_max"],
        "CPU ingestão": [n(x, 1) + "%" for x in dg["ufsm-ingestion_cpu"]],
        "CPU banco": [n(x, 1) + "%" for x in dg["ufsm-timescaledb_cpu"]],
        "CPU RabbitMQ": [n(x, 1) + "%" for x in dg["ufsm-rabbitmq_cpu"]],
        "Mem. banco (MiB)": [n(x, 0) for x in dg["ufsm-timescaledb_mem"]],
    })
    salvar_tab(t, a.saida, "escalabilidade_degraus", "r" * len(t.columns))
    bytes_msg = float(np.median(dg["bytes_msg"][dg["sondas"] >= 50]))
    por_sonda_dia = bytes_msg * PERFIL_MSG_S * 86400 / 1e6
    resumo += [
        f"Degraus: com 1000 sondas simuladas ({n(dg['oferta'].iloc[-1])} msg/s), a fila máxima foi de "
        f"{dg['fila_max'].iloc[-1]} mensagens e a CPU média foi de {n(dg['ufsm-ingestion_cpu'].iloc[-1])}% na ingestão, "
        f"{n(dg['ufsm-timescaledb_cpu'].iloc[-1])}% no banco e {n(dg['ufsm-rabbitmq_cpu'].iloc[-1])}% no RabbitMQ (por núcleo).",
        f"No degrau de 1000 sondas o gerador publicou {n(dg['publicado'].iloc[-1])} msg/s dos {n(dg['oferta'].iloc[-1])} "
        f"previstos, perto do limite de uma conexão com confirmação.",
        f"Armazenamento: cerca de {n(bytes_msg, 0)} bytes por mensagem, ou {n(por_sonda_dia, 1)} MB por sonda por dia "
        f"com os planos usados ({n(por_sonda_dia * 1000 / 1000, 1)} GB por dia para 1000 sondas, sem compressão).",
    ]
    if cap:
        resumo.append(f"Capacidade estimada: {n(cap, 0)} msg/s equivalem a cerca de {n(cap / PERFIL_MSG_S, 0)} sondas "
                      f"com o perfil de {n(PERFIL_MSG_S * 60, 2)} mensagens por minuto.")
    with open(os.path.join(a.saida, "resumo.md"), "w", encoding="utf-8") as f:
        f.write("# Teste de escalabilidade\n\n" + "\n".join(f"- {x}" for x in resumo) + "\n")
    print("\n".join(resumo))
    print(f"\nsaída em {a.saida}/")


if __name__ == "__main__":
    main()
