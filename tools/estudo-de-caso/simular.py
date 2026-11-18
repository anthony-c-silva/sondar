#!/usr/bin/env python3
"""Gera dados simulados no mesmo formato do exportar.sh, para testar a análise.

Os números não são medições reais. O comportamento imita a hipótese do estudo:
o uplink de 100 Mb/s do anexo C congestiona em dias úteis, no horário de uso.

Uso: python3 simular.py dados_simulados/
"""
import json
import os
import sys
import uuid

import numpy as np
import pandas as pd

TZ = "America/Sao_Paulo"
rng = np.random.default_rng(42)
INI = pd.Timestamp("2026-11-05 10:42", tz=TZ)
FIM = pd.Timestamp("2026-11-17 08:00", tz=TZ)
MUDANCA_CT01 = pd.Timestamp("2026-11-10 14:09", tz=TZ)
SAIDA_CT01 = pd.Timestamp("2026-11-10 13:53", tz=TZ)
INICIO_CT02 = pd.Timestamp("2026-11-12 11:00", tz=TZ)
VLAN_OK_CT02 = pd.Timestamp("2026-11-13 16:30", tz=TZ)
FERIADOS = {pd.Timestamp("2026-11-15").date()}
END = {"probe-srv-01": "192.168.129.200", "probe-ct-01": "192.168.129.201", "probe-ct-02": "192.168.129.227"}
INFRA = ["200.18.33.23", "200.18.33.169", "200.132.39.132", "45.168.147.19"]
EXTERNO = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
ROTA_EVENTOS = [(pd.Timestamp("2026-11-11 16:58", tz=TZ), 17), (pd.Timestamp("2026-11-11 17:35", tz=TZ), 12),
                (pd.Timestamp("2026-11-14 03:10", tz=TZ), 40)]
TLS_PICO = pd.Timestamp("2026-11-12 13:45", tz=TZ)


def util(t):
    return (t.dayofweek < 5) & ~pd.Series(t.date, index=t).isin(FERIADOS).values


def congest_anexo_c(t):
    """Fator 0..1 de ocupação do uplink do anexo C."""
    h = t.hour + t.minute / 60
    pico = np.exp(-((h - 10.5) / 1.3) ** 2) + 0.9 * np.exp(-((h - 15.5) / 1.6) ** 2)
    c = np.clip(pico * 0.95 + rng.normal(0, 0.08, len(t)), 0, 1)
    return np.where(util(t), c, np.clip(rng.normal(0.05, 0.03, len(t)), 0, 0.2))


def aulas_anexo_a(t):
    h = t.hour + t.minute / 60
    dow = t.dayofweek
    em_aula = (((dow == 0) | (dow == 2)) & (h >= 8) & (h < 12)) | (((dow == 1) | (dow == 3)) & (h >= 13.5) & (h < 17.5)) \
        | ((dow == 4) & (h >= 8) & (h < 10))
    return np.where(util(t) & em_aula, np.clip(rng.normal(0.55, 0.15, len(t)), 0, 1), 0.03)


def ativo(pid, t):
    if pid == "probe-ct-01":
        return (t < SAIDA_CT01) | (t >= MUDANCA_CT01)
    if pid == "probe-ct-02":
        return t >= INICIO_CT02
    return np.ones(len(t), bool)


def fator(pid, t):
    if pid == "probe-ct-01":
        return np.where(t >= MUDANCA_CT01, congest_anexo_c(t), 0.02)
    if pid == "probe-ct-02":
        return aulas_anexo_a(t)
    return np.zeros(len(t))


def rota_extra(t):
    extra = np.zeros(len(t))
    for ini, mins in ROTA_EVENTOS:
        extra += ((t >= ini) & (t < ini + pd.Timedelta(minutes=mins))) * 6.2
    return extra


def utc(t):
    return t.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S.%f+00")


def main(out):
    os.makedirs(out, exist_ok=True)
    pids = list(END)
    execs = []

    # ICMP (a cada 2 min para manter o arquivo pequeno)
    t_all = pd.date_range(INI, FIM, freq="2min")
    rows = []
    for pid in pids:
        t = t_all[ativo(pid, t_all)]
        f = fator(pid, t)
        base_local = {"probe-ct-01": np.where(t >= MUDANCA_CT01, 0.95, 0.55), "probe-ct-02": 0.75, "probe-srv-01": 0.45}[pid]
        destinos = INFRA + EXTERNO + [END[p] for p in pids if p != pid]
        for alvo in destinos:
            if alvo in EXTERNO:
                base = 20.8 + base_local + rota_extra(t) * (alvo == "1.1.1.1")
            else:
                base = base_local + (0.4 if alvo in INFRA else 0.3)
            ganho = 9.0 if pid == "probe-ct-01" else 2.2
            rtt = base + ganho * f ** 2 + rng.gamma(1.2, 0.08, len(t))
            perda = np.where(rng.random(len(t)) < np.clip((f - 0.65) * 1.2, 0, 1) * (pid == "probe-ct-01"),
                             rng.choice([10, 20, 30], len(t)), 0.0)
            falha = np.zeros(len(t), bool)
            if alvo == END["probe-ct-02"]:
                falha = t < VLAN_OK_CT02
            if pid == "probe-ct-02" and alvo in (END["probe-ct-01"], END["probe-srv-01"]):
                falha = np.zeros(len(t), bool)
            ts = utc(t)
            for i in range(len(t)):
                st = "failure" if falha[i] else "success"
                execs.append((t[i], pid, "icmp", alvo, "", "malha-ufsm", "icmp", st, "100% de perda" if falha[i] else ""))
                if falha[i]:
                    continue
                rows.append((ts[i], pid, alvo, 10, int(10 - perda[i] / 10), perda[i], rtt[i] * 0.85,
                             rtt[i], rtt[i] * 1.6, rtt[i] * 0.15, rtt[i] * 1.4))
    pd.DataFrame(rows, columns=["observed_at", "probe_id", "target", "packets_sent", "packets_received", "loss_pct",
                                "rtt_min_ms", "rtt_avg_ms", "rtt_max_ms", "jitter_ms", "rtt_p95_ms"]).to_csv(f"{out}/icmp.csv", index=False)

    # HTTP
    rows = []
    for pid in pids:
        for alvo, per in (("https://www.ufsm.br", "5min"), ("https://portal.ufsm.br", "5min"),
                          ("http://192.168.129.200:8090/", "2min"), ("http://192.168.129.201:8080/", "2min"),
                          ("http://192.168.129.227:8080/", "2min")):
            if alvo.split("//")[1].split(":")[0] == END[pid]:
                continue
            t = pd.date_range(INI, FIM, freq=per)
            t = t[ativo(pid, t)]
            if "227" in alvo:
                t = t[t >= VLAN_OK_CT02]
            f = fator(pid, t)
            ganho = 9.0 if pid == "probe-ct-01" else 2.2
            rtt = 0.8 + ganho * f ** 2 + rng.gamma(1.2, 0.1, len(t))
            https = alvo.startswith("https")
            dns = rng.gamma(2, 1.2, len(t)) if https else np.zeros(len(t))
            tls = (2 * rtt + rng.normal(13, 2, len(t))) if https else np.zeros(len(t))
            espera = rng.gamma(4, 10 if https else 0.3, len(t))
            if https and "www" in alvo:
                pico = np.abs((t - TLS_PICO).total_seconds()) < 150
                tls = np.where(pico, 230, tls)
            ttfb = dns + rtt + tls + espera + rtt
            tamanho = 180_000 if https else 300
            vazao = (94 if pid == "probe-ct-01" else 900) * (1 - 0.7 * f) * 1e6 / 8
            transf = tamanho / vazao * 1000
            ts = utc(t)
            for i in range(len(t)):
                execs.append((t[i], pid, "http", alvo, "", "malha-ufsm", "http", "success", ""))
                rows.append((ts[i], pid, alvo, 200, dns[i], rtt[i], tls[i], ttfb[i], ttfb[i] + transf[i], tamanho))
    pd.DataFrame(rows, columns=["observed_at", "probe_id", "target", "http_status", "dns_ms", "tcp_connect_ms",
                                "tls_handshake_ms", "ttfb_ms", "total_ms", "response_bytes"]).to_csv(f"{out}/http.csv", index=False)

    # Vazão (malha a cada hora, depois de 10/11 15h; antes, a cada 15 min)
    rows = []
    t_v = pd.date_range(INI.ceil("15min"), FIM, freq="15min")
    t_v = t_v[(t_v < pd.Timestamp("2026-11-10 15:00", tz=TZ)) | (t_v.minute == 0)]
    for k, t0 in enumerate(t_v):
        pares = [(a, b) for a in pids for b in pids if a != b]
        for j, (a, b) in enumerate(pares):
            t = t0 + pd.Timedelta(seconds=15 * j)
            ta = pd.DatetimeIndex([t])
            if not (ativo(a, ta)[0] and ativo(b, ta)[0]):
                continue
            if "probe-ct-02" in (a, b) and t < VLAN_OK_CT02 and b == "probe-ct-02":
                execs.append((t, a, "iperf3", END[b], b, "malha-vazao", "iperf3-malha", "failure", "unable to connect"))
                continue
            cap = 930.0
            for p in (a, b):
                if p == "probe-ct-01" and t >= MUDANCA_CT01:
                    cap = min(cap, 94 * (1 - 0.75 * fator(p, ta)[0]))
                elif p == "probe-ct-02":
                    cap = min(cap, 930 * (1 - 0.35 * fator(p, ta)[0]))
            mbps = max(cap * rng.uniform(0.93, 1.0), 2)
            execs.append((t, a, "iperf3", END[b], b, "malha-vazao", "iperf3-malha", "success", ""))
            rows.append((utc(ta)[0], a, END[b], b, "source_to_target", 10, int(mbps * 1e6 / 8 * 10), mbps * 1e6,
                         int(rng.poisson(5 + 60 * (cap < 60)))))
    pd.DataFrame(rows, columns=["observed_at", "probe_id", "target", "target_probe", "direction", "duration_seconds",
                                "bytes_transferred", "throughput_bps", "retransmits"]).to_csv(f"{out}/iperf.csv", index=False)

    # DNS
    rows = []
    for pid in pids:
        t = pd.date_range(INI, FIM, freq="5min")
        t = t[ativo(pid, t)]
        f = fator(pid, t)
        for res, base in (("200.18.33.23", 1.8), ("1.1.1.1", 22.0)):
            el = base + (9.0 if pid == "probe-ct-01" else 2.2) * f ** 2 + rng.gamma(1.5, 0.6, len(t))
            ts = utc(t)
            for i in range(len(t)):
                execs.append((t[i], pid, "dns", "www.ufsm.br", "", "malha-ufsm", "dns", "success", ""))
                rows.append((ts[i], pid, "www.ufsm.br", res, "A", "NOERROR", 2, el[i]))
    pd.DataFrame(rows, columns=["observed_at", "probe_id", "target", "resolver", "qtype", "rcode", "answer_count",
                                "elapsed_ms"]).to_csv(f"{out}/dns.csv", index=False)

    # Traceroute
    rows = []
    for pid in pids:
        t = pd.date_range(INI, FIM, freq="15min")
        t = t[ativo(pid, t)]
        for alvo in ("200.18.33.23", "1.1.1.1"):
            for ti in t:
                gw = "192.168.129.1"
                hops = [gw, "200.18.45.1", "200.18.33.1"] + (["200.143.255.141", "200.143.252.2", alvo] if alvo == "1.1.1.1" else [alvo])
                if alvo == "1.1.1.1" and any(ini <= ti < ini + pd.Timedelta(minutes=m) for ini, m in ROTA_EVENTOS):
                    hops = hops[:3] + ["200.143.255.149", "200.143.253.10", "189.1.1.1", alvo]
                hj = json.dumps([{"ttl": i + 1, "address": h, "rtt_avg_ms": 0.5 + i * 3, "loss_pct": 0} for i, h in enumerate(hops)])
                execs.append((ti, pid, "traceroute", alvo, "", "malha-ufsm", "traceroute", "success", ""))
                rows.append((utc(pd.DatetimeIndex([ti]))[0], pid, alvo, len(hops), hj))
    pd.DataFrame(rows, columns=["observed_at", "probe_id", "target", "hop_count", "hops"]).to_csv(f"{out}/traceroute.csv", index=False)

    # Saúde
    rows = []
    for pid in pids:
        t = pd.date_range(INI, FIM, freq="5min")
        t = t[ativo(pid, t)]
        h = t.hour.values
        temp0 = {"probe-ct-01": 54, "probe-ct-02": 37, "probe-srv-01": 44}[pid]
        temp = temp0 + 3 * np.sin((h - 9) / 24 * 2 * np.pi) + rng.normal(0, 0.6, len(t))
        link = np.where((pid == "probe-ct-01") & (t >= MUDANCA_CT01), 100, 1000)
        ts = utc(t)
        for i in range(len(t)):
            rows.append((ts[i], pid, temp[i], max(rng.normal(3, 1.2), 0.2), max(rng.normal(1.1, 0.5), 0.1),
                         rng.normal(21500, 400), 3882436, rng.normal(3300000, 30000), link[i], 0, END[pid]))
    pd.DataFrame(rows, columns=["observed_at", "probe_id", "cpu_temp_c", "cpu_usage_pct", "agent_cpu_pct", "agent_rss_kb",
                                "mem_total_kb", "mem_available_kb", "link_speed_mbps", "throttled_now",
                                "ip_address"]).to_csv(f"{out}/saude.csv", index=False)

    ex = pd.DataFrame(execs, columns=["t", "probe_id", "measurement_type", "target", "target_probe", "plan_id", "job_id",
                                      "status", "error_message"]).sort_values("t")
    ex.insert(0, "observed_at", utc(pd.DatetimeIndex(ex.pop("t"))))
    ex.to_csv(f"{out}/execucoes.csv", index=False)

    pd.DataFrame([
        ("ufsm-ns3", "external", "200.18.33.23"), ("ufsm-ns4", "external", "200.18.33.169"),
        ("rnp-rs", "external", "200.132.39.132"), ("ufsm-borda", "external", "45.168.147.19"),
        ("cloudflare-dns", "external", "1.1.1.1"), ("google-dns", "external", "8.8.8.8"), ("quad9-dns", "external", "9.9.9.9"),
        ("ufsm-web", "external", "https://www.ufsm.br"), ("ufsm-portal", "external", "https://portal.ufsm.br"),
        ("srv-health", "external", "http://192.168.129.200:8090/"), ("pi-health", "external", "http://192.168.129.201:8080/"),
        ("pi2-health", "external", "http://192.168.129.227:8080/"), ("www.ufsm.br", "external", "www.ufsm.br"),
    ], columns=["name", "kind", "address"]).to_csv(f"{out}/destinos.csv", index=False)
    pd.DataFrame([(p, a, "") for p, a in END.items()], columns=["probe_id", "address", "deployment"]).to_csv(f"{out}/sondas.csv", index=False)
    print("dados simulados em", out)
    _ = uuid


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dados_simulados")
